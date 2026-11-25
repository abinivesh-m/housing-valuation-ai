"""Fetch / assemble the published market-index series.

RBI and NHB do not offer a stable machine-readable endpoint we can rely on, so
this script is a documented template rather than a silent scraper. It shows the
exact shape `data/market_indices.json` must have and validates a hand-filled
file. To populate:

  1. Download the latest RBI HPI release (RBI Bulletin, monthly) and the NHB
     Residex release. Both are free PDFs/Excel on the RBI and NHB websites.
  2. Transcribe the city-level index values into a CSV with columns:
        index,city,quarter,value
     e.g.  rbi_hpi,Mumbai,2025Q3,198.4
  3. Run:  python scripts/fetch_market_indices.py input.csv --source "RBI HPI Q3 2025"
  4. The engine picks up data/market_indices.json on the next run.

Do not fabricate values. An empty file with honest nulls is worth more than a
confident-looking invented series.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "market_indices.json"

import pandas as pd  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build market_indices.json from a transcribed CSV.")
    parser.add_argument("source", type=Path, help="CSV with columns: index,city,quarter,value")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--source-name", default="published index")
    args = parser.parse_args()

    raw = pd.read_csv(args.source)
    required = {"index", "city", "quarter", "value"}
    if not required.issubset(set(raw.columns)):
        raise SystemExit(f"CSV must contain columns: {sorted(required)}")

    indices: dict = {}
    for _, row in raw.iterrows():
        idx = str(row["index"]).strip().lower()
        city = str(row["city"]).strip()
        quarter = str(row["quarter"]).strip()
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        indices.setdefault(idx, {"cities": {}})["cities"].setdefault(city, {})[quarter] = round(value, 2)

    # Preserve base/frequency metadata from an existing file if present.
    existing = {}
    if args.out.exists():
        try:
            existing = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    payload = {
        "version": 1,
        "source": args.source_name,
        "captured_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
        "notes": "City-level published indices transcribed from official releases. "
                 "Verify against the source before any production use.",
        "indices": {},
    }
    for idx, block in indices.items():
        meta = existing.get("indices", {}).get(idx, {})
        payload["indices"][idx] = {
            "base": meta.get("base", "see source"),
            "frequency": meta.get("frequency", "quarterly"),
            "cities": block["cities"],
        }
    # Ensure both known indices exist even if only one was supplied.
    for idx in ("rbi_hpi", "nhb_residex"):
        payload["indices"].setdefault(idx, existing.get("indices", {}).get(idx, {
            "base": "see source", "frequency": "quarterly", "cities": {}
        }))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(b["cities"]) for b in payload["indices"].values())
    print(f"wrote {args.out}  ({total} city series)")


if __name__ == "__main__":
    main()
