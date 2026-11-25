#!/usr/bin/env python3
"""Local valuation runner for the housing-valuation-india skill.

Runs entirely on this machine: no API key, no network call, no quota. The
model artifacts and the inference code ship with the skill.

    python scripts/valuate.py valuate --json '{"city":"Bangalore","locality":"Koramangala","area_sqft":1250}'
    python scripts/valuate.py valuate --file property.json
    python scripts/valuate.py batch --file portfolio.json
    python scripts/valuate.py options
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import lending  # noqa: E402
from engine.model import load_model  # noqa: E402
from engine.valuation import valuate  # noqa: E402

DEFAULTS = {
    "property_type": "Apartment",
    "furnishing": "Semi-Furnished",
    "occupancy": "Self-Occupied",
    "tenure": "Freehold",
    "bedrooms": 2,
    "bathrooms": 2,
    "floor": 3,
    "total_floors": 12,
    "age_years": 4,
    "parking": 1,
    "lift": 1,
    "balcony": 1,
    "metro_distance_km": 2.0,
    "school_distance_km": 1.0,
    "hospital_distance_km": 1.5,
    "highway_distance_km": 3.0,
    "crime_index": 5.0,
    "requested_loan_inr": 0,
}

COVERAGE = json.loads((ROOT / "artifacts" / "coverage.json").read_text(encoding="utf-8"))
LOCALITY_INDEX = {(c["city"], c["locality"]): c for c in COVERAGE["localities"]}
MODEL = load_model()


def inr(amount: float | int) -> str:
    value = float(amount)
    if abs(value) >= 1e7:
        return f"₹{value / 1e7:.2f} cr"
    if abs(value) >= 1e5:
        return f"₹{value / 1e5:.2f} L"
    return f"₹{value:,.0f}"


def coordinates(city: str, locality: str) -> tuple[float, float]:
    row = LOCALITY_INDEX.get((city, locality))
    if row:
        return float(row["lat"]), float(row["lon"])
    city_row = next((c for c in COVERAGE["cities"] if c["city"] == city), None)
    if city_row:
        return float(city_row["lat"]), float(city_row["lon"])
    return 20.5937, 78.9629


def validate(payload: dict) -> None:
    city = payload.get("city")
    locality = payload.get("locality")
    if city not in COVERAGE["city_names"]:
        raise ValueError(
            f"City '{city}' is outside the covered market. Covered: {', '.join(COVERAGE['city_names'])}"
        )
    covered = COVERAGE["localities_by_city"].get(city, [])
    if locality not in covered:
        raise ValueError(
            f"Locality '{locality}' is not covered in {city}. Covered there: {', '.join(covered)}"
        )
    area = payload.get("area_sqft")
    if not isinstance(area, (int, float)) or not 150 <= area <= 40000:
        raise ValueError("area_sqft is required and must be between 150 and 40000.")


def run_one(payload: dict) -> tuple[dict, dict]:
    merged = {**DEFAULTS, **payload}
    validate(merged)
    lat, lon = coordinates(merged["city"], merged["locality"])
    merged["lat"], merged["lon"] = lat, lon

    result = valuate(MODEL, merged, None)
    requested = int(merged.get("requested_loan_inr") or 0)
    assumed = requested <= 0
    loan = requested if not assumed else int(round(result["value"] * 0.60, -3))
    decision = lending.assess(result, loan, merged)
    decision["loan_assumed"] = assumed
    decision["loan_basis"] = (
        "reference LTV — no loan amount entered" if assumed else "submitted loan amount"
    )
    result["lending"] = decision
    result["input"] = merged
    result["coordinates"] = {"lat": lat, "lon": lon}
    return result, decision


def print_one(result: dict) -> None:
    decision = result["lending"]
    print(f"Value      {inr(result['value'])}   (p10 {inr(result['value_low'])} – p90 {inr(result['value_high'])})")
    print(f"Confidence {result['confidence'] * 100:.1f}%   band width {result['interval_width_pct'] * 100:.1f}%"
          f"   {inr(result['rate_per_sqft'])}/sqft")
    market = result.get("market") or {}
    if market.get("locality_median_rate"):
        premium = market.get("premium_vs_locality_pct")
        tail = f"   {premium:+.1f}% vs locality" if premium is not None else ""
        print(f"Baseline   {inr(market['locality_median_rate'])}/sqft locality median{tail}")
    print(f"Decision   {decision['decision_label']}   grade {decision['risk_grade']}")
    print(f"Max loan   {inr(decision['max_loan_recommended'])} at {decision['effective_cap'] * 100:.0f}% LTV on p10")
    if decision["reason_codes"]:
        print(f"Reasons    {', '.join(decision['reason_codes'])}")
    print("Drivers")
    for group in result["drivers"]:
        if group["impact_inr"] == 0:
            continue
        print(f"  {group['group']:<24} {inr(group['impact_inr']):>12}")
    residual = result["attribution"]["residual_log"]
    print(f"  {'interaction residual':<24} {residual:>12.4f} log")
    if result["flags"]:
        print(f"Flags      {', '.join(result['flags'])}")
    if result["comps_value"]:
        print(f"Comps      {inr(result['comps_value'])} from {len(result['comparables'])} sales"
              f"   divergence {result['comps_divergence_pct']:.1f}%")


def print_batch(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"{'Locality':<20}{'Type':<14}{'Sqft':>7}{'Value':>14}{'Conf':>7}  Decision")
    for row in rows:
        print(
            f"{row['locality'][:19]:<20}{row['property_type'][:13]:<14}"
            f"{row['area_sqft']:>7}{inr(row['value']):>14}{row['confidence'] * 100:>6.1f}%  "
            f"{row['decision_label']}"
        )
    automated = sum(1 for r in rows if r["decision"] in {"AUTO_APPROVE_DESKTOP", "APPROVE_WITH_CONDITIONS"})
    print(f"\n{len(rows)} properties · automated share {automated / len(rows) * 100:.1f}%")


def read_payload(args):
    if args.file:
        # utf-8-sig: Windows editors and PowerShell write a BOM, which
        # json.loads rejects with a confusing message.
        with open(args.file, encoding="utf-8-sig") as handle:
            return json.load(handle)
    if args.json:
        return json.loads(args.json)
    if not sys.stdin.isatty():
        return json.loads(sys.stdin.read().lstrip("\ufeff"))
    sys.exit("Provide --json, --file, or pipe the payload on stdin.")


def main() -> None:
    # Windows consoles default to cp1252 and cannot encode ₹. Reconfigure the
    # streams rather than dropping the symbol from every output line.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="HousingValuation AI — local runner")
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("valuate", help="value one property")
    single.add_argument("--json")
    single.add_argument("--file")
    single.add_argument("--raw", action="store_true", help="print the full JSON result")

    book = sub.add_parser("batch", help="value a list of properties")
    book.add_argument("--json")
    book.add_argument("--file")
    book.add_argument("--raw", action="store_true", help="print the full JSON result")

    sub.add_parser("options", help="list covered cities, localities and property types")

    args = parser.parse_args()

    if args.command == "options":
        print(json.dumps(
            {
                "cities": COVERAGE["city_names"],
                "localities_by_city": COVERAGE["localities_by_city"],
                "property_types": COVERAGE["property_types"],
                "furnishing": COVERAGE["furnishing"],
                "occupancy": COVERAGE["occupancy"],
                "tenure": COVERAGE["tenure"],
            },
            indent=2,
        ))
        return

    payload = read_payload(args)

    if args.command == "valuate":
        if not isinstance(payload, dict):
            sys.exit("valuate expects a single JSON object.")
        try:
            result, _ = run_one(payload)
        except ValueError as exc:
            sys.exit(str(exc))
        if args.raw:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_one(result)
        return

    if not isinstance(payload, list) or not payload:
        sys.exit("batch expects a non-empty JSON array.")
    if len(payload) > 40:
        sys.exit("batch limit is 40 properties per call.")

    rows: list[dict] = []
    errors: list[dict] = []
    for index, item in enumerate(payload):
        try:
            result, decision = run_one(item)
        except ValueError as exc:
            # One uncovered locality must not discard the rest of the book.
            errors.append({"index": index, "error": str(exc)})
            continue
        rows.append(
            {
                "locality": result["input"]["locality"],
                "property_type": result["input"]["property_type"],
                "area_sqft": result["input"]["area_sqft"],
                "value": result["value"],
                "value_low": result["value_low"],
                "value_high": result["value_high"],
                "confidence": result["confidence"],
                "decision": decision["decision"],
                "decision_label": decision["decision_label"],
                "risk_grade": decision["risk_grade"],
                "ltv": decision["requested_ltv"],
                "flags": result["flags"],
            }
        )

    if args.raw:
        print(json.dumps({"count": len(rows), "rows": rows, "errors": errors}, indent=2, ensure_ascii=False))
    else:
        print_batch(rows)
        for error in errors:
            print(f"row {error['index']} failed: {error['error']}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
