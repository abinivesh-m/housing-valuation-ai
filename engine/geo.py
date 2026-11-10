"""
Live geospatial enrichment via OpenStreetMap Overpass.

This is the one genuinely *real* external dataset in the prototype: at
valuation time the engine asks Overpass how many schools, hospitals,
pharmacies, metro/rail stations, malls, supermarkets, parks, banks and bus
stops exist inside a 1.5 km walk of the property, and derives an
infrastructure-density index from the counts.

Design constraints:
  * serverless functions must never hang, so the request has a hard timeout;
  * Overpass is a volunteer service — results are cached per ~110 m grid cell
    and every failure degrades to `available: false` rather than inventing
    numbers.

Production equivalent: a nightly pre-computed POI-density feature store
(see docs/DATA_STRATEGY.md), not a live third-party call per valuation.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://overpass-api.de/api/interpreter"
RADIUS_M = 1500
TIMEOUT_S = 7.0

_CACHE: dict[tuple[float, float], dict] = {}

QUERY = """
[out:json][timeout:{timeout}];
(
  node(around:{radius},{lat},{lon})[amenity~"^(school|college|university|hospital|clinic|pharmacy|bank|kindergarten)$"];
  node(around:{radius},{lat},{lon})[railway~"^(station|halt|subway_entrance|tram_stop)$"];
  node(around:{radius},{lat},{lon})[shop~"^(mall|supermarket|department_store)$"];
  node(around:{radius},{lat},{lon})[leisure~"^(park|garden|playground)$"];
  node(around:{radius},{lat},{lon})[highway=bus_stop];
);
out tags;
"""

CATEGORY_MAP = {
    "school": ("school", "education"),
    "kindergarten": ("school", "education"),
    "college": ("school", "education"),
    "university": ("school", "education"),
    "hospital": ("hospital", "healthcare"),
    "clinic": ("hospital", "healthcare"),
    "pharmacy": ("pharmacy", "healthcare"),
    "bank": ("bank", "services"),
    "station": ("transit", "mobility"),
    "halt": ("transit", "mobility"),
    "subway_entrance": ("transit", "mobility"),
    "tram_stop": ("transit", "mobility"),
    "bus_stop": ("bus_stop", "mobility"),
    "mall": ("retail", "retail"),
    "supermarket": ("retail", "retail"),
    "department_store": ("retail", "retail"),
    "park": ("park", "recreation"),
    "garden": ("park", "recreation"),
    "playground": ("park", "recreation"),
}

# weight of each category in the density index (0-100)
WEIGHTS = {
    "transit": 26.0,
    "school": 18.0,
    "hospital": 16.0,
    "retail": 12.0,
    "pharmacy": 8.0,
    "bank": 8.0,
    "park": 7.0,
    "bus_stop": 5.0,
}

SATURATION = {
    "transit": 6, "school": 10, "hospital": 6, "retail": 6,
    "pharmacy": 8, "bank": 8, "park": 6, "bus_stop": 12,
}


def _classify(tags: dict) -> str | None:
    for key in ("amenity", "railway", "shop", "leisure", "highway"):
        value = tags.get(key)
        if value and value in CATEGORY_MAP:
            return CATEGORY_MAP[value][0]
    return None


def _query(lat: float, lon: float) -> dict:
    body = QUERY.format(timeout=int(TIMEOUT_S), radius=RADIUS_M, lat=lat, lon=lon)
    data = urllib.parse.urlencode({"data": body}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={
            "User-Agent": "HousingValuationAI/2.0 (hackathon prototype)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    counts: dict[str, int] = {k: 0 for k in WEIGHTS}
    for element in payload.get("elements", []):
        cat = _classify(element.get("tags") or {})
        if cat:
            counts[cat] += 1

    score = 0.0
    for cat, weight in WEIGHTS.items():
        share = min(counts[cat] / SATURATION[cat], 1.0)
        score += weight * share

    return {
        "available": True,
        "source": "OpenStreetMap / Overpass API",
        "radius_m": RADIUS_M,
        "counts": counts,
        "density_index": round(score, 1),
        "poi_total": int(sum(counts.values())),
    }


def enrich(lat: float, lon: float) -> dict:
    """POI density near a coordinate. Never raises."""
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {"available": False, "reason": "invalid coordinates"}

    key = (round(lat, 3), round(lon, 3))
    if key in _CACHE:
        return _CACHE[key]

    try:
        result = _query(lat, lon)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        result = {
            "available": False,
            "reason": f"geo lookup unavailable ({type(exc).__name__}); distances from the application form were used instead",
            "source": "OpenStreetMap / Overpass API",
        }
    except Exception as exc:  # pragma: no cover - defensive
        result = {"available": False, "reason": f"geo lookup failed ({type(exc).__name__})"}

    _CACHE[key] = result
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
