"""Published market-index anchor (RBI HPI, NHB Residex).

These indices are the closest thing India has to a free, citable, public
record of housing-price movement. They are city-level (not transaction-level)
and they are published quarterly. They cannot tell you what a flat in
Koramangala is worth, but they can tell you whether your model's city-level
price level is sane, and they are the right anchor for calibrating a
parametric corpus so it stops being a formula we wrote.

The module loads `data/market_indices.json` if it exists. That file is
produced by `scripts/fetch_market_indices.py` (or filled in by hand from the
RBI / NHB publications). If the file is absent, every lookup returns None and
the engine falls back to its own locality medians, exactly as before.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET_INDICES_PATH = ROOT / "data" / "market_indices.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    if MARKET_INDICES_PATH.exists():
        try:
            return json.loads(MARKET_INDICES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def available() -> bool:
    payload = _load()
    for block in payload.get("indices", {}).values():
        if block.get("cities"):
            return True
    return False


def city_index(city: str, index: str = "rbi_hpi", quarter: str | None = None) -> dict:
    """Return {value, base, quarter, source} for a city, or {value: None}.

    `index` is one of 'rbi_hpi' or 'nhb_residex'. `quarter` is like '2025Q3';
    if omitted, the latest available quarter is used.
    """
    payload = _load()
    indices = payload.get("indices", {})
    series = indices.get(index, {}).get("cities", {}).get(city)
    if not series:
        return {"value": None, "source": payload.get("source", "unavailable"),
                "basis": "unavailable"}
    if quarter is None:
        quarter = max(series.keys())
    value = series.get(quarter)
    return {
        "value": value,
        "quarter": quarter,
        "base": indices.get(index, {}).get("base"),
        "source": payload.get("source", "published index"),
        "basis": "exact" if value is not None else "missing-quarter",
    }


def city_growth(city: str, index: str = "rbi_hpi", periods: int = 4) -> float | None:
    """Year-on-year style growth over the last `periods` quarters, in percent."""
    payload = _load()
    series = payload.get("indices", {}).get(index, {}).get("cities", {}).get(city)
    if not series or len(series) < periods + 1:
        return None
    quarters = sorted(series)
    latest = series[quarters[-1]]
    earlier = series[quarters[-(periods + 1)]]
    if not earlier:
        return None
    return round((latest / earlier - 1.0) * 100, 2)


def clear_cache() -> None:
    _load.cache_clear()
