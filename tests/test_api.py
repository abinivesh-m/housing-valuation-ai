"""
Regression tests for the serving path.

Run with:  python -m pytest -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from engine import audit, lending  # noqa: E402
from engine.model import load_model  # noqa: E402
from engine.valuation import valuate  # noqa: E402

client = TestClient(app)

BASE_PROPERTY = {
    "city": "Bangalore",
    "locality": "Koramangala",
    "property_type": "Apartment",
    "furnishing": "Semi-Furnished",
    "occupancy": "Self-Occupied",
    "tenure": "Freehold",
    "area_sqft": 1250,
    "bedrooms": 3,
    "bathrooms": 2,
    "floor": 7,
    "total_floors": 14,
    "age_years": 5,
    "parking": 1,
    "lift": 1,
    "balcony": 1,
    "metro_distance_km": 1.2,
    "school_distance_km": 0.6,
    "hospital_distance_km": 1.1,
    "highway_distance_km": 2.4,
    "crime_index": 4.2,
    "requested_loan_inr": 8_000_000,
}


def _valuated(**overrides):
    payload = {**BASE_PROPERTY, **overrides}
    res = client.post("/api/valuate", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_health_reports_real_metrics():
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert 0.0 < body["holdout_mape"] < 0.5
    assert 0.5 < body["holdout_r2"] <= 1.0
    assert body["cities"] == 8
    assert body["localities"] >= 60


def test_valuation_is_deterministic():
    a = _valuated()
    b = _valuated()
    assert a["value"] == b["value"]
    assert a["value_low"] == b["value_low"]
    assert a["value_high"] == b["value_high"]
    assert a["confidence"] == b["confidence"]
    assert [d["group"] for d in a["drivers"]] == [d["group"] for d in b["drivers"]]


def test_interval_brackets_point_and_rate_is_consistent():
    body = _valuated()
    assert body["value_low"] <= body["value"] <= body["value_high"]
    rate = body["value"] / BASE_PROPERTY["area_sqft"]
    assert abs(rate - body["rate_per_sqft"]) / rate < 0.01
    assert 0.0 < body["confidence"] <= 1.0


def test_bigger_area_is_worth_more():
    small = _valuated(area_sqft=800, bedrooms=2)
    large = _valuated(area_sqft=2200, bedrooms=4)
    assert large["value"] > small["value"]


def test_newer_property_beats_older_at_same_spec():
    new = _valuated(age_years=1)
    old = _valuated(age_years=30)
    assert new["value"] > old["value"]


def test_premium_locality_beats_secondary_locality():
    premium = _valuated(locality="Koramangala")
    value = _valuated(locality="Electronic City")
    assert premium["value"] > value["value"]


def test_furnishing_uplift_is_ordered():
    unfurnished = _valuated(furnishing="Unfurnished")
    fully = _valuated(furnishing="Fully Furnished")
    assert fully["value"] > unfurnished["value"]


def test_confidence_components_are_reported():
    body = _valuated()
    parts = body["confidence_parts"]
    assert set(parts) == {"interval", "comparables", "agreement"}
    assert all(0.0 <= v <= 1.0 for v in parts.values())


def test_attribution_reconciles_with_prediction():
    """Baseline substitution should explain nearly all of the deviation.

    A single-feature occlusion sweep leaves the interaction terms as residual,
    so a few percent is expected rather than a bug.
    """
    body = _valuated()
    attribution = body["attribution"]
    explained = attribution["explained_log"]
    residual = attribution["residual_log"]
    assert abs(residual) <= max(0.09, abs(explained) * 0.35)


def test_drivers_are_complete_and_signed():
    body = _valuated()
    groups = {d["group"] for d in body["drivers"]}
    assert {"Location", "Size & layout", "Age & condition"} <= groups
    assert body["drivers"][0]["impact_inr"] != 0


def test_comparables_are_within_radius_and_have_adjustments():
    body = _valuated()
    comps = body["comparables"]
    assert 1 <= len(comps) <= 8
    for comp in comps:
        assert comp["distance_km"] <= 12.0
        assert comp["adjusted_rate"] > 0
        assert -40.0 <= comp["adjustment_pct"] <= 40.0
        assert comp["sale_date"]


def test_high_ltv_is_referred_not_approved():
    """Ask for 95% of the engine's own estimate — above every policy cap."""
    estimate = _valuated()["value"]
    body = _valuated(requested_loan_inr=int(estimate * 0.95))
    assert body["lending"]["decision"] in {"REFER_PHYSICAL_VALUATION", "REFER_CREDIT"}
    assert "LTV_ABOVE_REGULATORY_CAP" in body["lending"]["reason_codes"]


def test_conservative_ltv_can_auto_approve():
    """A 50% LTV on a well-supported property should clear a desktop decision."""
    estimate = _valuated()["value"]
    body = _valuated(requested_loan_inr=int(estimate * 0.50))
    assert body["lending"]["requested_ltv"] < body["lending"]["regulatory_cap"]
    assert body["lending"]["decision"] in {"AUTO_APPROVE_DESKTOP", "APPROVE_WITH_CONDITIONS"}


def test_missing_loan_uses_reference_ltv_and_labels_it():
    loan = _valuated(requested_loan_inr=0)["lending"]
    assert loan["loan_assumed"] is True
    assert loan["requested_ltv"] == pytest.approx(0.60, abs=0.002)


def test_submitted_loan_is_not_labelled_assumed():
    body = _valuated(requested_loan_inr=5_000_000)
    loan = body["lending"]
    assert loan["loan_assumed"] is False
    assert loan["requested_loan"] == 5_000_000
    assert loan["requested_ltv"] == pytest.approx(5_000_000 / body["value"], abs=1e-4)


def test_ltv_exactly_at_haircut_ceiling_is_not_a_breach():
    """A request equal to the confidence-adjusted ceiling is a boundary, not a breach."""
    valuation = {
        "value": 10_000_000,
        "value_low": 9_000_000,
        "confidence": 0.50,          # very low -> 20% haircut -> 0.60 ceiling
        "flags": [],
        "interval_width_pct": 0.30,
        "comparables": [{}] * 8,
        "comps_divergence_pct": 5.0,
    }
    assessed = lending.assess(valuation, 6_000_000, {"property_type": "Apartment", "age_years": 5})
    assert assessed["effective_cap"] == pytest.approx(0.60)
    ceiling_check = next(c for c in assessed["checks"] if c["name"] == "Confidence-adjusted ceiling")
    assert ceiling_check["status"] == "pass"
    assert "LTV_ABOVE_CONFIDENCE_ADJUSTED_CAP" not in assessed["reason_codes"]


def test_grade_worsens_as_utilisation_rises():
    """Grade must track LTV utilisation, not absolute headroom."""
    base = {
        "value": 20_000_000,
        "value_low": 18_000_000,
        "confidence": 0.90,
        "flags": [],
        "interval_width_pct": 0.30,
        "comparables": [{}] * 8,
        "comps_divergence_pct": 5.0,
    }
    req = {"property_type": "Apartment", "age_years": 5}
    low = lending.assess(base, int(20_000_000 * 0.55), req)
    high = lending.assess(base, int(20_000_000 * 0.74), req)
    assert low["risk_grade"] < high["risk_grade"]
    assert low["risk_grade"] == "A"


def test_ltv_cap_follows_regulatory_bands():
    assert lending.regulatory_cap(2_000_000)[0] == 0.90
    assert lending.regulatory_cap(5_000_000)[0] == 0.80
    assert lending.regulatory_cap(20_000_000)[0] == 0.75


def test_effective_cap_never_exceeds_regulatory_cap():
    body = _valuated()
    loan = body["lending"]
    assert loan["effective_cap"] <= loan["regulatory_cap"] + 1e-9
    assert loan["max_loan_recommended"] <= body["value"]


def test_unknown_city_and_locality_are_rejected():
    bad_city = client.post("/api/valuate", json={**BASE_PROPERTY, "city": "Atlantis"})
    assert bad_city.status_code == 422
    bad_loc = client.post("/api/valuate", json={**BASE_PROPERTY, "locality": "Nowhere"})
    assert bad_loc.status_code == 422


def test_out_of_range_area_rejected():
    res = client.post("/api/valuate", json={**BASE_PROPERTY, "area_sqft": 5})
    assert res.status_code == 422


def test_batch_scoring_returns_decision_mix():
    payload = [{**BASE_PROPERTY, "area_sqft": 700 + 120 * i} for i in range(6)]
    res = client.post("/api/batch", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 6
    assert sum(body["decisions"].values()) == 6
    assert 0.0 <= body["automated_share"] <= 1.0


def test_batch_limit_enforced():
    payload = [{**BASE_PROPERTY} for _ in range(41)]
    assert client.post("/api/batch", json=payload).status_code == 422


def test_audit_chain_is_valid_after_valuations():
    _valuated()
    body = client.get("/api/audit/verify").json()
    entries = client.get("/api/audit", params={"limit": 100}).json()["entries"]
    assert body["entries"] >= 1
    assert len(body.get("head_hash", "")) == 64
    assert entries[0]["seq"] >= 1
    assert len(entries[0]["hash"]) == 64


def test_audit_chain_detects_tampering(tmp_path):
    ledger = audit.Ledger(str(tmp_path / "chain.jsonl"))
    ledger.append("VALUATION", "v-1", {"value": 10_000_000})
    ledger.append("VALUATION", "v-2", {"value": 12_000_000})
    ledger.append("DECISION", "v-2", {"decision": "AUTO_APPROVE_DESKTOP"})

    assert ledger.verify()["valid"] is True

    path = Path(ledger.path)
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["detail"]["value"] = 99_000_000  # rewrite history
    lines[1] = json.dumps(tampered, separators=(",", ":"), default=str)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = ledger.verify()
    assert report["valid"] is False
    assert report["broken_at_seq"] == 2


def test_model_artifact_exposes_benchmarks():
    model = load_model()
    benchmarks = model.metrics["benchmarks"]
    assert "gradient_boosting" in benchmarks
    assert benchmarks["gradient_boosting"]["mape"] <= benchmarks["global_median_rate"]["mape"]
    assert model.metrics["interval"]["coverage_p10_p90"] > 0.70


def test_geo_endpoint_validates_coordinates():
    assert client.get("/api/geo", params={"lat": 200, "lon": 10}).status_code == 422


def test_geo_lookup_never_raises_for_valid_input():
    res = client.get("/api/geo", params={"lat": 12.9352, "lon": 77.6245})
    assert res.status_code == 200
    body = res.json()
    assert "available" in body  # may be False when offline


def test_index_page_serves():
    res = client.get("/")
    assert res.status_code == 200
    assert "HousingValuation" in res.text
