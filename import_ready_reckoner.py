"""Convert a state's published ready-reckoner / circle-rate table into the
canonical JSON the engine reads.

Expected input CSV columns (header names are flexible, see ingest.py aliases):
    city, locality, property_type, rate_inr_per_sqft

    python import_ready_reckoner.py rates.csv --source "Maharashtra IGR, 2025" \\
        --url "https://igrmaharashtra.gov.in/..." --out data/ready_reckoner.json

The output replaces data/ready_reckoner.json; the engine picks it up on the
next valuation with no code change. Rows missing a property_type become the
locality default (average across types).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ingest  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "ready_reckoner.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a ready-reckoner table.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source", dest="source_name", default="published ready-reckoner")
    parser.add_argument("--url", default=None)
    parser.add_argument("--captured", default=None)
    args = parser.parse_args()

    raw = ingest.load_table(args.source)
    mapping, unmapped, missing = ingest.map_columns(list(raw.columns))
    # rate column is not in the standard aliases; accept common names.
    rate_col = None
    for candidate in ("rate_inr_per_sqft", "rate", "ready_reckoner_rate",
                      "circle_rate", "rr_rate", "value"):
        for col in raw.columns:
            if ingest.normalise_header(col) == candidate or ingest.normalise_header(col).startswith("rate"):
                rate_col = col
                break
        if rate_col:
            break
    if rate_col is None:
        raise SystemExit("could not find a rate column (rate / circle_rate / rr_rate / value)")

    if "city" not in mapping or "locality" not in mapping:
        raise SystemExit("city and locality columns are required")

    renamed = raw.rename(columns={src: dst for dst, src in mapping.items()})
    renamed["__rate__"] = renamed[rate_col].map(ingest.parse_number)

    table: dict = {}
    for _, row in renamed.iterrows():
        city = str(row["city"]).strip()
        locality = str(row["locality"]).strip()
        ptype = str(row.get("property_type", "")).strip() if "property_type" in renamed.columns else ""
        rate = row["__rate__"]
        if pd.isna(rate) or rate <= 0:
            continue
        table.setdefault(city, {}).setdefault(locality, {})
        if ptype and ptype.lower() not in {"", "nan", "none"}:
            table[city][locality][ptype] = int(round(float(rate)))
        else:
            table[city][locality].setdefault("_all", []).append(float(rate))

    # Collapse locality-level aggregates into a single default rate.
    for city in table:
        for locality in table[city]:
            block = table[city][locality]
            if "_all" in block:
                block["Apartment"] = int(round(sum(block.pop("_all")) / len(block["_all"]))) if "_all" else None
                # keep the aggregate under a neutral key as well
            # remove empty
            if not block:
                del table[city][locality]

    payload = {
        "version": 1,
        "source": args.source_name,
        "url": args.url,
        "captured_at": args.captured,
        "units": "INR per sq ft built-up (ready-reckoner basis)",
        "rates": table,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}  ({sum(len(v) for v in table.values())} localities)")


if __name__ == "__main__":
    main()
