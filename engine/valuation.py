"""
Valuation service: point estimate, learned interval, local attribution,
comparable-sales triangulation and a calibrated confidence score.

Everything here is deterministic. There is no `np.random` in the serving
path — the same property always produces the same value, band and drivers,
which is a hard requirement for an auditable AVM.
"""
from __future__ import annotations

import math
import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone

import numpy as np

from .geo import haversine_km
from .model import ValuationModel, load_comps, load_locality_stats

FEATURE_GROUPS: dict[str, list[str]] = {
    "Location": ["city", "locality"],
    "Size & layout": ["area_sqft", "bedrooms", "bathrooms"],
    "Property profile": ["property_type", "furnishing", "occupancy", "tenure"],
    "Age & condition": ["age_years"],
    "Building & amenities": ["floor_ratio", "parking", "lift", "balcony"],
    "Connectivity": ["metro_distance_km", "school_distance_km", "hospital_distance_km", "highway_distance_km"],
    "Neighbourhood safety": ["crime_index"],
}

# Adjustment-grid coefficients used by the comparable-sales engine.
# Hand-set, documented in docs/MODEL_CARD.md, and deliberately *not* fitted on
# the valuation model so that comps remain an independent cross-check.
ADJ_AGE_PER_YEAR = 0.009
ADJ_FLOOR_RATIO = 0.06
ADJ_FURNISHING = {"Unfurnished": 0.000, "Semi-Furnished": 0.035, "Fully Furnished": 0.075}
ADJ_AREA_ELASTICITY = -0.18
MARKET_DRIFT_PER_MONTH = 0.004
RECENCY_HALFLIFE_MONTHS = 18.0

NUMERIC_FEATURES = {
    "area_sqft", "bedrooms", "bathrooms", "floor_ratio", "age_years", "parking",
    "lift", "balcony", "metro_distance_km", "school_distance_km",
    "hospital_distance_km", "highway_distance_km", "crime_index",
}

_POOL = None
_BASELINES: dict[tuple[str, str, str], dict] = {}
_BY_CITY: dict[str, list[dict]] = {}


def _pool() -> list[dict]:
    global _POOL
    if _POOL is None:
        _POOL = load_comps()
    return _POOL


def _pool_by_city(city: str) -> list[dict]:
    if not _BY_CITY:
        for row in _pool():
            _BY_CITY.setdefault(row["city"], []).append(row)
    return _BY_CITY.get(city, [])


def _mode(values) -> object:
    return Counter(values).most_common(1)[0][0]


def _baseline(city: str, locality: str, property_type: str) -> dict:
    """Typical property in the same micro-market, used as the attribution base."""
    key = (city, locality, property_type)
    cached = _BASELINES.get(key)
    if cached is not None:
        return cached

    pool = _pool()
    tiers = [
        [r for r in pool if r["city"] == city and r["locality"] == locality and r["property_type"] == property_type],
        [r for r in pool if r["city"] == city and r["locality"] == locality],
        [r for r in pool if r["city"] == city and r["property_type"] == property_type],
        pool,
    ]
    sample = next((t for t in tiers if len(t) >= 8), pool)
    base: dict = {}
    for name in ("city", "locality", "property_type", "furnishing", "occupancy", "tenure"):
        base[name] = _mode([r[name] for r in sample]) if name not in ("city", "locality") else (
            city if name == "city" else locality
        )
    for name in (
        "area_sqft", "bedrooms", "bathrooms", "floor", "total_floors", "age_years",
        "parking", "lift", "balcony", "metro_distance_km", "school_distance_km",
        "hospital_distance_km", "highway_distance_km", "crime_index",
    ):
        base[name] = statistics.median([float(r[name]) for r in sample])
    _BASELINES[key] = base
    return base


def _months_ago(sale_date: str) -> float:
    try:
        d = datetime.strptime(str(sale_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 12.0
    delta = datetime.now(timezone.utc) - d
    return max(delta.days / 30.44, 0.0)


def _weighted_median(pairs: list[tuple[float, float]]) -> float:
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= total / 2:
            return value
    return pairs[-1][0]


def _comparables(req: dict, subject_area: float, subject_fr: float) -> tuple[list[dict], float | None]:
    subj_furn = ADJ_FURNISHING.get(req["furnishing"], 0.0)
    candidates = []
    for row in _pool_by_city(req["city"]):
        dist = haversine_km(req["lat"], req["lon"], float(row["lat"]), float(row["lon"]))
        if dist > 12.0:
            continue
        type_penalty = 0.0 if row["property_type"] == req["property_type"] else 1.0
        area_ratio = float(row["area_sqft"]) / subject_area if subject_area else 1.0
        area_penalty = abs(math.log(area_ratio)) if area_ratio > 0 else 1.0
        age_penalty = abs(float(row["age_years"]) - float(req["age_years"])) / 25.0
        score = dist / 4.0 + type_penalty * 0.9 + area_penalty * 0.8 + age_penalty * 0.35
        candidates.append((score, dist, row))

    candidates.sort(key=lambda t: t[0])
    selected = candidates[:8]
    if not selected:
        return [], None

    adjusted = []
    for _, dist, row in selected:
        comp_rate = float(row["price_inr"]) / max(float(row["area_sqft"]), 1.0)
        months = _months_ago(row["sale_date"])
        row_fr = min(max(float(row["floor"]) / max(float(row["total_floors"]), 1.0), 0.0), 1.0)
        adj = (
            (1.0 + ADJ_AGE_PER_YEAR * (float(row["age_years"]) - float(req["age_years"])))
            * (1.0 + ADJ_FLOOR_RATIO * (subject_fr - row_fr))
            * (1.0 + subj_furn - ADJ_FURNISHING.get(row["furnishing"], 0.0))
            * (1.0 + ADJ_AREA_ELASTICITY * math.log(subject_area / max(float(row["area_sqft"]), 1.0)))
            * (1.0 + MARKET_DRIFT_PER_MONTH * months)
        )
        adj_rate = comp_rate * adj
        adj_value = adj_rate * subject_area
        weight = math.exp(-math.log(2) * months / RECENCY_HALFLIFE_MONTHS) / (1.0 + dist / 3.0)
        adjusted.append(
            {
                "locality": row["locality"],
                "property_type": row["property_type"],
                "area_sqft": int(row["area_sqft"]),
                "age_years": int(row["age_years"]),
                "floor": int(row["floor"]),
                "total_floors": int(row["total_floors"]),
                "sale_date": str(row["sale_date"])[:10],
                "distance_km": round(dist, 2),
                "sale_price": int(row["price_inr"]),
                "sale_rate": int(round(comp_rate)),
                "adjusted_rate": int(round(adj_rate)),
                "adjustment_pct": round((adj - 1.0) * 100, 1),
                "weight": round(weight, 3),
                "indicated_value": int(round(adj_value, -3)),
                "_raw_rate": adj_rate,
                "_weight": weight,
            }
        )

    comps_value = _weighted_median([(c["_raw_rate"], c["_weight"]) for c in adjusted]) * subject_area
    return adjusted, comps_value


def valuate(model: ValuationModel, req: dict, geo: dict | None = None) -> dict:
    area = max(float(req["area_sqft"]), 1.0)
    floors = max(float(req.get("total_floors", 1) or 1), 1.0)
    subject_fr = min(max(float(req.get("floor", 0)) / floors, 0.0), 1.0)
    req = {**req, "floor_ratio": subject_fr}

    X = model.encode_many([req])
    p_med, p_lo, p_hi = model.predict_price(X, req["property_type"])
    value = float(p_med[0])
    low = float(p_lo[0])
    high = float(p_hi[0])

    # ---- attribution (exact baseline-substitution / occlusion) -------------
    # One batched prediction instead of 21 single-row calls: same numbers,
    # roughly 20x less numpy dispatch overhead (~600 ms -> ~30 ms).
    base_rec = _baseline(req["city"], req["locality"], req["property_type"])
    base_rec["floor_ratio"] = min(max(float(base_rec["floor"]) / max(float(base_rec["total_floors"]), 1.0), 0.0), 1.0)

    swaps: list[tuple[str, dict]] = []
    for feature in model.feature_order:
        rec = dict(base_rec)
        if feature in NUMERIC_FEATURES:
            rec[feature] = float(req[feature])
        elif feature in ("city", "locality", "property_type", "furnishing", "occupancy", "tenure"):
            rec[feature] = req[feature]
        else:
            continue
        swaps.append((feature, rec))

    batch = [req, base_rec] + [rec for _, rec in swaps]
    log_preds = model.predict_log(model.encode_many(batch))
    base_log = float(log_preds[1])
    feature_effects = {
        feature: float(log_preds[2 + i]) - base_log for i, (feature, _) in enumerate(swaps)
    }

    groups = []
    for group, features in FEATURE_GROUPS.items():
        delta_log = sum(feature_effects.get(f, 0.0) for f in features)
        groups.append(
            {
                "group": group,
                "impact_inr": int(round(value * (math.exp(delta_log) - 1.0), -3)),
                "impact_log": delta_log,
                "features": [
                    {
                        "feature": f,
                        "impact_inr": int(round(value * (math.exp(feature_effects.get(f, 0.0)) - 1.0), -3)),
                    }
                    for f in features
                    if abs(feature_effects.get(f, 0.0)) > 1e-6
                ],
            }
        )
    groups.sort(key=lambda g: -abs(g["impact_inr"]))
    explained_log = sum(feature_effects.values())

    # ---- comparable sales --------------------------------------------------
    comps, comps_value = _comparables(req, area, subject_fr)
    comps_n = len(comps)
    divergence = None
    if comps_value:
        divergence = abs(math.log(value / comps_value))

    # ---- confidence (deterministic, documented) ---------------------------
    band_pct = (high - low) / value
    # 25% band -> 1.0 ; 65% band -> 0.0
    f_band = min(max(1.0 - (band_pct - 0.25) / 0.40, 0.0), 1.0)
    f_comps = min(max(comps_n / 8.0, 0.25), 1.0)
    f_agreement = min(max(1.0 - (divergence if divergence is not None else 0.25) / 0.30, 0.0), 1.0)
    confidence = 0.45 * f_band + 0.25 * f_comps + 0.30 * f_agreement

    stats = load_locality_stats()
    seen = (req["city"], req["locality"], req["property_type"]) in stats
    flags: list[str] = []
    if not seen:
        confidence *= 0.85
        flags.append("UNSEEN_MICROMARKET")
    if comps_n < 4:
        flags.append("THIN_COMPARABLES")
    if band_pct > 0.55:
        flags.append("WIDE_INTERVAL")
    if divergence is not None and divergence > 0.18:
        flags.append("MODEL_COMPS_DIVERGENCE")
    confidence = round(min(max(confidence, 0.05), 0.97), 3)

    # ---- market context ----------------------------------------------------
    nearby = [r for r in _pool_by_city(req["city"]) if r["locality"] == req["locality"]]
    locality_rate = statistics.median([r["rate"] for r in nearby]) if nearby else None
    city_rows = _pool_by_city(req["city"])
    city_rate = statistics.median([r["rate"] for r in city_rows]) if city_rows else None
    subject_rate = value / area

    return {
        "valuation_id": uuid.uuid4().hex[:12],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "value": int(round(value, -3)),
        "value_low": int(round(low, -3)),
        "value_high": int(round(high, -3)),
        "interval_width_pct": round(band_pct, 4),
        "rate_per_sqft": int(round(subject_rate)),
        "rate_low": int(round(low / area)),
        "rate_high": int(round(high / area)),
        "confidence": confidence,
        "confidence_parts": {
            "interval": round(f_band, 3),
            "comparables": round(f_comps, 3),
            "agreement": round(f_agreement, 3),
        },
        "flags": flags,
        "drivers": groups,
        "attribution": {
            "method": "baseline substitution (exact, model-agnostic)",
            "explained_log": round(explained_log, 6),
            "residual_log": round(math.log(value) - base_log - explained_log, 6),
        },
        "comparables": [{k: v for k, v in c.items() if not k.startswith("_")} for c in comps],
        "comps_value": int(round(comps_value, -3)) if comps_value else None,
        "comps_divergence_pct": round(divergence * 100, 2) if divergence is not None else None,
        "market": {
            "locality_median_rate": int(round(locality_rate)) if locality_rate else None,
            "city_median_rate": int(round(city_rate)) if city_rate else None,
            "premium_vs_locality_pct": round((subject_rate / locality_rate - 1.0) * 100, 1) if locality_rate else None,
        },
        "geo": geo,
        "model": {
            "schema_version": model.artifact["schema_version"],
            "trained_at": model.trained_at,
            "target": model.target,
        },
    }
