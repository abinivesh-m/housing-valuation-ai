"""Ready-reckoner / circle-rate anchor.

A lender never trusts an AVM in isolation. The cheapest, most defensible
second number in the Indian market is the government's own floor rate for the
micro-market — the ready-reckoner (circle) rate published by each state's
registration department. It is free, citable, and it is the number a physical
valuer is measured against.

This module keeps that second number next to every valuation so the output can
say, in one line, "model says X, government floor says Y". It loads a
canonical JSON table if one exists (`data/ready_reckoner.json`); otherwise it
falls back to the model's own learned locality medians and labels them as such,
so the engine never runs without a second number even on a fresh clone.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY_RECKONER_PATH = ROOT / "data" / "ready_reckoner.json"
LOCALITY_STATS_PATH = ROOT / "artifacts" / "locality_stats.json"


@lru_cache(maxsize=1)
def _load() -> tuple[dict, str]:
    """Return (table, source_label). Table: {city: {locality: {property_type: rate}}}."""
    if READY_RECKONER_PATH.exists():
        try:
            payload = json.loads(READY_RECKONER_PATH.read_text(encoding="utf-8"))
            table = payload.get("rates", payload)
            source = payload.get("source", "ready-reckoner")
            return table, f"ready-reckoner ({source})"
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: model-derived locality medians. Honest label, never "government".
    if LOCALITY_STATS_PATH.exists():
        try:
            payload = json.loads(LOCALITY_STATS_PATH.read_text(encoding="utf-8"))
            cols = payload["columns"]
            idx = {name: i for i, name in enumerate(cols)}
            table: dict = {}
            for row in payload["rows"]:
                city, locality, ptype = row[idx["city"]], row[idx["locality"]], row[idx["property_type"]]
                rate = row[idx["median_rate"]]
                table.setdefault(city, {}).setdefault(locality, {})[ptype] = int(rate)
            return table, "model-derived locality median (no ready-reckoner file)"
        except (KeyError, json.JSONDecodeError, OSError):
            pass
    return {}, "unavailable"


def rate(city: str, locality: str, property_type: str = "Apartment") -> dict:
    """Look up the anchor rate for a micro-market.

    Returns a dict with `rate` (₹/sqft or None), `source`, and `basis` (how the
    number was obtained: exact, property-type fallback, locality fallback, or
    city fallback). Never raises.
    """
    table, source = _load()
    city_block = table.get(city) or {}
    locality_block = city_block.get(locality) or {}

    if property_type in locality_block:
        return {"rate": int(locality_block[property_type]), "source": source, "basis": "exact"}
    if locality_block:
        # Property type not in the table; use the locality's median across types.
        rates = [v for v in locality_block.values() if isinstance(v, (int, float))]
        if rates:
            return {"rate": int(round(sum(rates) / len(rates))), "source": source,
                    "basis": "locality-fallback"}
    # City-wide fallback: median across all localities in that city.
    city_rates: list[int] = []
    for loc_block in city_block.values():
        if isinstance(loc_block, dict):
            city_rates.extend(v for v in loc_block.values() if isinstance(v, (int, float)))
    if city_rates:
        return {"rate": int(round(sum(city_rates) / len(city_rates))), "source": source,
                "basis": "city-fallback"}
    return {"rate": None, "source": source, "basis": "unavailable"}


def clear_cache() -> None:
    _load.cache_clear()
