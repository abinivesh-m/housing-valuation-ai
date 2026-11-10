"""HousingValuation AI — automated valuation engine (FastAPI)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import audit, geo, lending
from engine.model import ARTIFACT_DIR, load_model
from engine.valuation import valuate

__version__ = "2.0.0"
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(
    title="HousingValuation AI",
    version=__version__,
    description="Explainable automated valuation engine with a risk-based lending layer.",
)

model = load_model()
COVERAGE: dict[str, Any] = json.loads((ARTIFACT_DIR / "coverage.json").read_text(encoding="utf-8"))
LOCALITY_INDEX = {
    (c["city"], c["locality"]): c for c in COVERAGE["localities"]
}


class ValuationRequest(BaseModel):
    city: str = Field(..., examples=["Bangalore"])
    locality: str = Field(..., examples=["Koramangala"])
    property_type: str = Field("Apartment")
    furnishing: str = Field("Semi-Furnished")
    occupancy: str = Field("Self-Occupied")
    tenure: str = Field("Freehold")
    area_sqft: int = Field(..., ge=150, le=40000)
    bedrooms: int = Field(2, ge=0, le=10)
    bathrooms: int = Field(2, ge=0, le=10)
    floor: int = Field(3, ge=0, le=80)
    total_floors: int = Field(12, ge=1, le=80)
    age_years: int = Field(4, ge=0, le=60)
    parking: int = Field(1, ge=0, le=10)
    lift: int = Field(1, ge=0, le=1)
    balcony: int = Field(1, ge=0, le=5)
    metro_distance_km: float = Field(2.0, ge=0, le=25)
    school_distance_km: float = Field(1.0, ge=0, le=15)
    hospital_distance_km: float = Field(1.5, ge=0, le=15)
    highway_distance_km: float = Field(3.0, ge=0, le=30)
    crime_index: float = Field(5.0, ge=1, le=10)
    lat: float | None = None
    lon: float | None = None
    requested_loan_inr: int = Field(0, ge=0)


class BatchItem(ValuationRequest):
    pass


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "model_schema": model.artifact["schema_version"],
        "trained_at": model.trained_at,
        "holdout_mape": model.metrics["holdout"]["mape"],
        "holdout_r2": model.metrics["holdout"]["r2"],
        "cities": len(COVERAGE["cities"]),
        "localities": len(COVERAGE["localities"]),
        "corpus": model.corpus,
    }


@app.get("/api/meta")
def meta() -> dict:
    return {
        "version": __version__,
        "trained_at": model.trained_at,
        "target": model.target,
        "corpus": model.corpus,
        "metrics": model.metrics,
        "coverage": {
            "cities": COVERAGE["cities"],
            "localities": COVERAGE["localities"],
            "property_types": COVERAGE["property_types"],
            "furnishing": COVERAGE["furnishing"],
            "occupancy": COVERAGE["occupancy"],
            "tenure": COVERAGE["tenure"],
        },
        "samples": COVERAGE["samples"],
        "policy": {
            "ltv_bands": lending.LTV_BANDS,
            "haircuts": [
                {"min_confidence": 0.85, "haircut": 1.00},
                {"min_confidence": 0.70, "haircut": 0.95},
                {"min_confidence": 0.55, "haircut": 0.88},
                {"min_confidence": 0.00, "haircut": 0.80},
            ],
        },
        "audit": audit.stats(),
    }


@app.get("/api/options")
def options() -> dict:
    return {
        "cities": COVERAGE["cities"],
        "city_names": COVERAGE["city_names"],
        "localities": COVERAGE["localities"],
        "localities_by_city": COVERAGE["localities_by_city"],
        "property_types": COVERAGE["property_types"],
        "furnishing": COVERAGE["furnishing"],
        "occupancy": COVERAGE["occupancy"],
        "tenure": COVERAGE["tenure"],
        "samples": COVERAGE["samples"],
    }


def _resolve_coords(req: ValuationRequest) -> tuple[float, float]:
    if req.lat is not None and req.lon is not None:
        return float(req.lat), float(req.lon)
    geo_row = LOCALITY_INDEX.get((req.city, req.locality))
    if geo_row:
        return float(geo_row["lat"]), float(geo_row["lon"])
    city_row = next((c for c in COVERAGE["cities"] if c["city"] == req.city), None)
    return (float(city_row["lat"]), float(city_row["lon"])) if city_row else (20.5937, 78.9629)


def _resolve_loan(requested: int, value: float) -> tuple[int, bool]:
    """Loan amount to test the policy against.

    A submitted amount always wins. When the caller does not submit one (the UI
    sends 0 for "not entered"), the policy is evaluated at a 60% reference LTV
    instead of the ceiling, and the response says so. Testing every property at
    the ceiling would grade every valuation as maximum risk and make the grade
    meaningless.
    """
    if requested > 0:
        return int(requested), False
    return int(round(value * 0.60, -3)), True


@app.post("/api/valuate")
def valuate_endpoint(req: ValuationRequest) -> JSONResponse:
    payload = req.model_dump()
    lat, lon = _resolve_coords(req)
    payload["lat"], payload["lon"] = lat, lon

    if req.city not in COVERAGE["city_names"]:
        raise HTTPException(status_code=422, detail=f"city '{req.city}' is outside the covered market")
    if req.locality not in COVERAGE["localities_by_city"].get(req.city, []):
        raise HTTPException(
            status_code=422,
            detail=f"locality '{req.locality}' is not covered in {req.city}",
        )

    # Geo enrichment is deliberately NOT on the valuation path: a volunteer
    # Overpass endpoint must never add seconds to a lender's turnaround. The
    # client calls /api/geo in parallel and fills the panel when it lands.
    result = valuate(model, payload, None)
    loan, assumed = _resolve_loan(req.requested_loan_inr, result["value"])
    decision = lending.assess(result, loan, payload)
    decision["loan_assumed"] = assumed
    decision["loan_basis"] = (
        "reference LTV — no loan amount entered" if assumed else "submitted loan amount"
    )

    audit.append(
        "VALUATION",
        result["valuation_id"],
        {
            "input_digest": {
                "city": req.city,
                "locality": req.locality,
                "property_type": req.property_type,
                "area_sqft": req.area_sqft,
                "age_years": req.age_years,
            },
            "value": result["value"],
            "value_low": result["value_low"],
            "value_high": result["value_high"],
            "confidence": result["confidence"],
            "decision": decision["decision"],
        },
    )

    return JSONResponse(
        {
            **result,
            "input": payload,
            "coordinates": {"lat": lat, "lon": lon},
            "lending": decision,
            "disclaimer": (
                "Prototype valuation engine. The model was trained on a documented "
                "parametric corpus, not on licensed transaction data, so the output is "
                "not a certified valuation and must not be used for an actual credit decision."
            ),
        }
    )


@app.post("/api/batch")
def batch(items: list[BatchItem]) -> JSONResponse:
    if not items:
        raise HTTPException(status_code=422, detail="empty batch")
    if len(items) > 40:
        raise HTTPException(status_code=422, detail="batch limit is 40 properties")
    rows = []
    for item in items:
        payload = item.model_dump()
        lat, lon = _resolve_coords(item)
        payload["lat"], payload["lon"] = lat, lon
        result = valuate(model, payload, None)
        loan, assumed = _resolve_loan(item.requested_loan_inr, result["value"])
        decision = lending.assess(result, loan, payload)
        rows.append(
            {
                "locality": item.locality,
                "property_type": item.property_type,
                "area_sqft": item.area_sqft,
                "value": result["value"],
                "value_low": result["value_low"],
                "value_high": result["value_high"],
                "confidence": result["confidence"],
                "decision": decision["decision"],
                "decision_label": decision["decision_label"],
                "risk_grade": decision["risk_grade"],
                "ltv": decision["requested_ltv"],
                "loan_assumed": assumed,
                "flags": result["flags"],
            }
        )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    return JSONResponse(
        {
            "count": len(rows),
            "rows": rows,
            "decisions": counts,
            "automated_share": round(
                sum(v for k, v in counts.items() if k in {"AUTO_APPROVE_DESKTOP", "APPROVE_WITH_CONDITIONS"})
                / len(rows),
                3,
            ),
            "median_confidence": round(sorted(r["confidence"] for r in rows)[len(rows) // 2], 3),
        }
    )


@app.get("/api/geo")
def geo_endpoint(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict:
    return geo.enrich(lat, lon)


@app.get("/api/audit")
def audit_tail(limit: int = Query(20, ge=1, le=100)) -> dict:
    return {"entries": audit.tail(limit), "stats": audit.stats()}


@app.get("/api/audit/verify")
def audit_verify() -> dict:
    return audit.verify()


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": COVERAGE["samples"]}


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(str(STATIC / "favicon.svg"))
