"""Bring your own transaction data.

The engine ships with a synthetic corpus. That is reproducible and inspectable,
but it is not evidence about the Indian housing market, and no lender will pay
for a number whose accuracy was measured against a formula we wrote ourselves.

This module is the bridge out of that trap. It takes a transaction file with
whatever column names the source uses, validates it, reports what is wrong, and
writes a training-ready CSV in the schema `train.py` expects.

    python ingest.py my_deeds.csv --report reports/ingest.json
    python ingest.py my_deeds.csv --out data/properties.csv
    python train.py --data data/properties.csv --label "Karnataka registry, 2019-2025"

Nothing here invents data. Rows that fail a hard check are dropped and counted;
soft problems are reported and left for the operator to decide on. The point of
the report is that you can show a reviewer exactly what you did to their file.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

# Canonical schema: the columns train.py and the serving engine read.
CANONICAL = [
    "city", "locality", "lat", "lon", "property_type", "furnishing", "occupancy",
    "tenure", "area_sqft", "bedrooms", "bathrooms", "floor", "total_floors",
    "age_years", "parking", "lift", "balcony", "metro_distance_km",
    "school_distance_km", "hospital_distance_km", "highway_distance_km",
    "crime_index", "sale_date", "price_inr",
]

REQUIRED = ["city", "locality", "area_sqft", "price_inr"]

# Source headers vary wildly between registrars, portals and spreadsheets. Each
# canonical name accepts a set of normalised aliases; matching is exact after
# normalisation, never fuzzy, so a column is never mapped by accident.
ALIASES: dict[str, list[str]] = {
    "city": ["city", "district", "district_name", "town", "urban_agglomeration"],
    "locality": ["locality", "locality_name", "micro_market", "neighbourhood",
                 "neighborhood", "area_name", "sub_locality", "village", "ward"],
    "lat": ["lat", "latitude", "y", "lat_deg"],
    "lon": ["lon", "lng", "long", "longitude", "x", "lon_deg"],
    "property_type": ["property_type", "property", "type", "asset_type",
                      "unit_type", "dwelling_type"],
    "furnishing": ["furnishing", "furnished", "furnishing_status", "furnish"],
    "occupancy": ["occupancy", "occupancy_status", "occupied", "status"],
    "tenure": ["tenure", "ownership", "ownership_type", "title_type"],
    "area_sqft": ["area_sqft", "area", "built_up_area", "carpet_area", "super_area",
                  "sqft", "area_sq_ft", "size_sqft", "builtup_area"],
    "bedrooms": ["bedrooms", "beds", "bhk", "bedroom_count", "no_of_bedrooms"],
    "bathrooms": ["bathrooms", "baths", "bathroom_count", "no_of_bathrooms"],
    "floor": ["floor", "floor_no", "floor_number", "unit_floor"],
    "total_floors": ["total_floors", "floors", "building_floors", "total_floor"],
    "age_years": ["age_years", "age", "property_age", "age_of_property"],
    "parking": ["parking", "parking_count", "car_park", "parking_slots"],
    "lift": ["lift", "elevator", "has_lift"],
    "balcony": ["balcony", "balconies", "balcony_count"],
    "metro_distance_km": ["metro_distance_km", "metro_km", "distance_to_metro",
                          "metro_distance"],
    "school_distance_km": ["school_distance_km", "school_km", "distance_to_school",
                           "school_distance"],
    "hospital_distance_km": ["hospital_distance_km", "hospital_km",
                             "distance_to_hospital", "hospital_distance"],
    "highway_distance_km": ["highway_distance_km", "highway_km",
                            "distance_to_highway", "highway_distance"],
    "crime_index": ["crime_index", "crime_rate", "safety_index", "crime_score"],
    "sale_date": ["sale_date", "date", "registration_date", "transaction_date",
                  "deed_date", "sold_on"],
    "price_inr": ["price_inr", "price", "sale_price", "consideration",
                  "consideration_amount", "transaction_value", "amount_inr",
                  "value_inr", "registration_value"],
}

DEFAULTS: dict[str, object] = {
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
}

AREA_MIN, AREA_MAX = 150.0, 40000.0
PRICE_MIN = 100_000.0


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #

_MONEY_UNITS = {
    "cr": 1e7, "crore": 1e7, "crores": 1e7,
    "l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
    "k": 1e3, "thousand": 1e3,
}


def normalise_header(name: str) -> str:
    """Lowercase, strip currency noise, collapse every run of non-alphanumerics."""
    text = str(name).strip().lower()
    text = re.sub(r"^\s*(₹|rs\.?|inr)\s*", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def parse_number(value) -> float:
    """Parse a number that may be a string with commas, currency or a unit suffix.

    Handles the shapes Indian transaction files actually contain:
        1,25,00,000      ₹1.25 Cr      12500000.0      125 L      12.5L
    Returns NaN when the value cannot be read, so the caller can count it.
    """
    if value is None:
        return math.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value) if not isinstance(value, bool) else math.nan

    text = str(value).strip()
    if not text or text.lower() in {"na", "n/a", "null", "none", "-", "--"}:
        return math.nan

    text = re.sub(r"^\s*(₹|rs\.?|inr)\s*", "", text, flags=re.IGNORECASE)
    text = text.lower()
    text = text.replace(",", "").replace("_", "").strip()

    multiplier = 1.0
    match = re.search(r"(crores?|crore|cr|lakhs?|lacs?|lac|l|thousand|k)\s*$", text)
    if match:
        multiplier = _MONEY_UNITS[match.group(1)]
        text = text[: match.start()].strip()

    try:
        return float(text) * multiplier
    except ValueError:
        return math.nan


def parse_date(value) -> str | None:
    """Return an ISO date, or None. Accepts the usual registrar formats."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"na", "n/a", "null", "none"}:
        return None
    for dayfirst in (True, False):
        try:
            parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="raise")
        except (ValueError, TypeError, OverflowError):
            continue
        if pd.isna(parsed):
            continue
        return parsed.strftime("%Y-%m-%d")
    return None


# --------------------------------------------------------------------------- #
# loading and mapping
# --------------------------------------------------------------------------- #

def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        return pd.read_json(path)
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"could not decode {path} as text; export it as UTF-8 CSV")


def map_columns(columns: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    """Return (canonical -> source, unmapped source columns, missing required)."""
    lookup: dict[str, str] = {}
    for canonical, names in ALIASES.items():
        for name in names:
            lookup.setdefault(name, canonical)

    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    for source in columns:
        canonical = lookup.get(normalise_header(source))
        if canonical and canonical not in mapping:
            mapping[canonical] = source
        elif canonical:
            # Two source columns claim the same canonical slot. Keep the first
            # and surface the collision rather than silently overwriting.
            unmapped.append(f"{source} (duplicate of {mapping[canonical]})")
        else:
            unmapped.append(source)

    missing = [c for c in REQUIRED if c not in mapping]
    return mapping, unmapped, missing


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def _issue(severity: str, code: str, detail: str, count: int | None = None,
           column: str | None = None) -> dict:
    return {
        "severity": severity,
        "code": code,
        "column": column,
        "count": int(count) if count is not None else None,
        "detail": detail,
    }


def _rate_outliers(df: pd.DataFrame, k: float = 3.0, min_group: int = 8) -> pd.Series:
    """Flag rows whose ₹/sqft is far from their own micro-market median.

    Robust (median/MAD) rather than mean/std, because a handful of crore-plus
    deals would otherwise drag the threshold and hide the real outliers.
    """
    rate = df["price_inr"] / df["area_sqft"]
    log_rate = np.log(rate.where(rate > 0))
    grouped = log_rate.groupby([df["city"], df["locality"]])
    median = grouped.transform("median")
    mad = grouped.transform(lambda s: (s - s.median()).abs().median())
    scale = (1.4826 * mad).replace(0, np.nan)
    z = (log_rate - median).abs() / scale
    z = z.fillna(0.0)
    sizes = grouped.transform("size")
    return (z > k) & (sizes >= min_group)


def validate(df: pd.DataFrame, min_per_locality: int = 20) -> tuple[pd.DataFrame, list[dict]]:
    """Coerce, check, and return (usable frame, issues).

    Hard failures drop the row. Soft problems are reported and kept, because
    only the operator knows whether a wide band or a thin locality is expected.
    """
    issues: list[dict] = []
    out = pd.DataFrame(index=df.index)
    out["city"] = df["city"].astype(str).str.strip()
    out["locality"] = df["locality"].astype(str).str.strip()
    out["area_sqft"] = df["area_sqft"].map(parse_number)
    out["price_inr"] = df["price_inr"].map(parse_number)

    # ---- hard checks ------------------------------------------------------
    blank_city = out["city"].isin({"", "nan", "None"})
    blank_locality = out["locality"].isin({"", "nan", "None"})
    bad_area = out["area_sqft"].isna() | (out["area_sqft"] < AREA_MIN) | (out["area_sqft"] > AREA_MAX)
    bad_price = out["price_inr"].isna() | (out["price_inr"] < PRICE_MIN)

    for mask, code, detail in (
        (blank_city, "BLANK_CITY", "city is empty"),
        (blank_locality, "BLANK_LOCALITY", "locality is empty"),
        (bad_area, "BAD_AREA", f"area_sqft missing or outside {AREA_MIN:.0f}-{AREA_MAX:.0f}"),
        (bad_price, "BAD_PRICE", f"price_inr missing or below ₹{PRICE_MIN:,.0f}"),
    ):
        if mask.any():
            issues.append(_issue("error", code, detail, mask.sum()))

    keep = ~(blank_city | blank_locality | bad_area | bad_price)
    dropped = int((~keep).sum())
    out = out[keep]
    source = df.loc[keep]

    # ---- optional columns -------------------------------------------------
    for canonical in CANONICAL:
        if canonical in {"city", "locality", "area_sqft", "price_inr"}:
            continue
        if canonical in source.columns:
            out[canonical] = source[canonical]
        else:
            out[canonical] = DEFAULTS.get(canonical, np.nan)

    # numeric coercions
    numeric_optional = [
        "lat", "lon", "bedrooms", "bathrooms", "floor", "total_floors",
        "age_years", "parking", "lift", "balcony", "metro_distance_km",
        "school_distance_km", "hospital_distance_km", "highway_distance_km",
        "crime_index",
    ]
    for column in numeric_optional:
        out[column] = out[column].map(parse_number)

    # sale_date: parse, then fill with the median date so recency weighting
    # stays meaningful instead of crashing on a missing field.
    out["sale_date"] = out["sale_date"].map(parse_date)
    missing_dates = int(out["sale_date"].isna().sum())
    if missing_dates:
        issues.append(_issue(
            "warning", "MISSING_SALE_DATE",
            f"{missing_dates} rows had no readable date; filled with the file's median date",
            missing_dates, "sale_date",
        ))
        known = pd.to_datetime(out["sale_date"].dropna(), errors="coerce")
        fallback = known.median().strftime("%Y-%m-%d") if len(known) else "2025-01-01"
        out["sale_date"] = out["sale_date"].fillna(fallback)

    # categoricals: normalise whitespace, keep unknown values (the model derives
    # its vocabulary from the data, so a new type is a feature, not an error).
    for column in ("property_type", "furnishing", "occupancy", "tenure"):
        out[column] = out[column].astype(str).str.strip().replace({"nan": ""})
        empty = out[column] == ""
        if empty.any():
            issues.append(_issue(
                "warning", "DEFAULTED_CATEGORY",
                f"{empty.sum()} rows had no {column}; set to '{DEFAULTS[column]}'",
                empty.sum(), column,
            ))
            out.loc[empty, column] = DEFAULTS[column]

    # ---- coordinates ------------------------------------------------------
    # Comparables need coordinates. Fill from the locality median, then the city
    # median, and report it — never fabricate a parcel location.
    for column in ("lat", "lon"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    missing_coords = out["lat"].isna() | out["lon"].isna()
    if missing_coords.any():
        for column in ("lat", "lon"):
            locality_fill = out.groupby(["city", "locality"])[column].transform("median")
            city_fill = out.groupby("city")[column].transform("median")
            out[column] = out[column].fillna(locality_fill).fillna(city_fill)
        still = int((out["lat"].isna() | out["lon"].isna()).sum())
        issues.append(_issue(
            "warning", "FILLED_COORDINATES",
            f"{int(missing_coords.sum())} rows had no coordinates; filled from locality median"
            + (f"; {still} remain unknown and will fall back to the city centre at serve time" if still else ""),
            int(missing_coords.sum()), "lat/lon",
        ))

    # ---- duplicates -------------------------------------------------------
    keys = ["city", "locality", "area_sqft", "price_inr", "sale_date"]
    dup_mask = out.duplicated(subset=keys, keep="first")
    if dup_mask.any():
        issues.append(_issue(
            "warning", "DUPLICATE_ROWS",
            f"{int(dup_mask.sum())} exact duplicates on {', '.join(keys)} removed",
            int(dup_mask.sum()),
        ))
        out = out[~dup_mask]

    # ---- rate outliers ----------------------------------------------------
    outliers = _rate_outliers(out)
    if outliers.any():
        issues.append(_issue(
            "warning", "RATE_OUTLIERS",
            f"{int(outliers.sum())} rows sit more than 3 robust SDs from their own "
            "micro-market ₹/sqft median; kept, because a real luxury sale looks like an outlier",
            int(outliers.sum()),
        ))
    out["rate_outlier"] = outliers.astype(bool)

    # ---- locality depth ---------------------------------------------------
    depth = out.groupby(["city", "locality"]).size()
    thin = depth[depth < min_per_locality]
    if len(thin):
        issues.append(_issue(
            "warning", "THIN_LOCALITIES",
            f"{len(thin)} of {len(depth)} micro-markets have fewer than {min_per_locality} "
            "transactions; the model will fall back to city behaviour there and flag it",
            len(thin),
        ))

    # ---- coverage summary -------------------------------------------------
    issues.append(_issue(
        "info", "COVERAGE",
        f"{len(out)} usable rows across {out['city'].nunique()} cities and "
        f"{depth.size} micro-markets; {dropped} rows dropped",
        len(out),
    ))
    return out, issues


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

def summarise(df: pd.DataFrame, issues: list[dict]) -> dict:
    rate = (df["price_inr"] / df["area_sqft"]).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "rows": int(len(df)),
        "cities": sorted(df["city"].unique().tolist()),
        "localities": int(df.groupby(["city", "locality"]).ngroups),
        "property_types": sorted(df["property_type"].unique().tolist()),
        "price_min_inr": int(df["price_inr"].min()) if len(df) else 0,
        "price_median_inr": int(df["price_inr"].median()) if len(df) else 0,
        "price_max_inr": int(df["price_inr"].max()) if len(df) else 0,
        "rate_median_inr_sqft": int(round(float(rate.median()))) if len(rate) else 0,
        "date_min": str(df["sale_date"].min()) if len(df) else None,
        "date_max": str(df["sale_date"].max()) if len(df) else None,
        "errors": sum(1 for i in issues if i["severity"] == "error"),
        "warnings": sum(1 for i in issues if i["severity"] == "warning"),
    }


def write_training_csv(df: pd.DataFrame, path: Path) -> None:
    columns = CANONICAL + ["rate_outlier"]
    frame = df.copy()
    frame["area_sqft"] = frame["area_sqft"].round(1)
    frame["price_inr"] = frame["price_inr"].round(0).astype("int64")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame[columns].to_csv(path, index=False, encoding="utf-8")
    print(f"wrote {path}  ({len(frame)} rows, {len(columns)} columns)")


def print_report(summary: dict, issues: list[dict], unmapped: list[str]) -> None:
    print("\nIngest summary")
    print(f"  rows          {summary['rows']}")
    print(f"  cities        {len(summary['cities'])}  ({', '.join(summary['cities'][:8])})")
    print(f"  micro-markets {summary['localities']}")
    print(f"  price         ₹{summary['price_min_inr']:,} – ₹{summary['price_max_inr']:,}"
          f"  (median ₹{summary['price_median_inr']:,})")
    print(f"  median rate   ₹{summary['rate_median_inr_sqft']:,}/sqft")
    if summary["date_min"]:
        print(f"  sale dates    {summary['date_min']} → {summary['date_max']}")

    if unmapped:
        print(f"\n  ignored columns ({len(unmapped)}): {', '.join(unmapped[:12])}"
              + (" ..." if len(unmapped) > 12 else ""))

    print("\nFindings")
    order = {"error": 0, "warning": 1, "info": 2}
    for issue in sorted(issues, key=lambda i: order[i["severity"]]):
        tag = issue["severity"].upper().ljust(7)
        count = f" [{issue['count']}]" if issue["count"] is not None else ""
        print(f"  {tag}{count} {issue['detail']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a real transaction file and convert it to the training schema."
    )
    parser.add_argument("source", type=Path, help="CSV, JSON or JSONL of transactions")
    parser.add_argument("--out", type=Path, help="write a training-ready CSV here")
    parser.add_argument("--report", type=Path, help="write the full JSON report here")
    parser.add_argument("--min-per-locality", type=int, default=20,
                        help="warn when a micro-market has fewer transactions (default 20)")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero when any row fails a hard check")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"no such file: {args.source}")

    raw = load_table(args.source)
    if raw.empty:
        raise SystemExit(f"{args.source} has no rows")

    mapping, unmapped, missing = map_columns(list(raw.columns))
    if missing:
        print(f"Could not map required column(s): {', '.join(missing)}", file=sys.stderr)
        print(f"Accepted aliases:\n  " + "\n  ".join(
            f"{c}: {', '.join(ALIASES[c][:6])}" for c in missing
        ), file=sys.stderr)
        raise SystemExit(2)

    renamed = raw.rename(columns={src: dst for dst, src in mapping.items()})
    frame, issues = validate(renamed, min_per_locality=args.min_per_locality)
    summary = summarise(frame, issues)

    print_report(summary, issues, unmapped)

    if args.out and len(frame):
        write_training_csv(frame, args.out)
    elif args.out:
        print("nothing to write: no row passed validation", file=sys.stderr)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source": str(args.source),
                    "column_mapping": mapping,
                    "ignored_columns": unmapped,
                    "summary": summary,
                    "issues": issues,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.report}")

    hard = [i for i in issues if i["severity"] == "error"]
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
