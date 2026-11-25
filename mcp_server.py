#!/usr/bin/env python3
"""MCP server for HousingValuation AI.

Exposes the engine as tools that any MCP client (Claude Desktop, Claude Code,
Cursor, Codex, Zed, ...) can call directly. stdlib only, so it ships inside the
skill zip with no install step beyond Python and numpy.

Run:
    python mcp_server.py            # stdio transport (default for MCP clients)

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "housing-valuation-india": {
          "command": "python",
          "args": ["/path/to/skill/mcp_server.py"]
        }
      }
    }

Every tool returns JSON. Nothing leaves the machine: the model, comps and
policy all run locally.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import lending, ready_reckoner  # noqa: E402
from engine.model import load_model  # noqa: E402
from engine.valuation import valuate  # noqa: E402

MODEL = load_model()
COVERAGE = json.loads((ROOT / "artifacts" / "coverage.json").read_text(encoding="utf-8"))
LOCALITY_INDEX = {(c["city"], c["locality"]): c for c in COVERAGE["localities"]}

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
}


def _coordinates(city: str, locality: str) -> tuple[float, float]:
    row = LOCALITY_INDEX.get((city, locality))
    if row:
        return float(row["lat"]), float(row["lon"])
    city_row = next((c for c in COVERAGE["cities"] if c["city"] == city), None)
    if city_row:
        return float(city_row["lat"]), float(city_row["lon"])
    return 20.5937, 78.9629


def _run_one(payload: dict) -> dict:
    merged = {**DEFAULTS, **payload}
    city = merged["city"]
    locality = merged["locality"]
    if city not in COVERAGE["city_names"]:
        raise ValueError(f"City '{city}' is outside the covered market: {', '.join(COVERAGE['city_names'])}")
    if locality not in COVERAGE["localities_by_city"].get(city, []):
        raise ValueError(f"Locality '{locality}' is not covered in {city}.")
    area = merged.get("area_sqft")
    if not isinstance(area, (int, float)) or not 150 <= area <= 40000:
        raise ValueError("area_sqft is required and must be between 150 and 40000.")

    lat, lon = _coordinates(city, locality)
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
    result["input"] = {k: v for k, v in merged.items() if k not in {"lat", "lon"}}
    result["coordinates"] = {"lat": lat, "lon": lon}
    result["ready_reckoner"] = ready_reckoner.rate(city, locality, merged.get("property_type", "Apartment"))
    return result


# --------------------------------------------------------------------------- #
# MCP protocol (JSON-RPC 2.0 over stdio)
# --------------------------------------------------------------------------- #

SERVER_INFO = {"name": "housing-valuation-india", "version": "2.1.0"}
PROTOCOL_VERSION = "2024-11-05"

PROPERTY_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string", "description": "Covered city (see get_coverage)."},
        "locality": {"type": "string", "description": "Micro-market inside the city."},
        "property_type": {"type": "string", "enum": COVERAGE["property_types"]},
        "furnishing": {"type": "string", "enum": COVERAGE["furnishing"]},
        "occupancy": {"type": "string", "enum": COVERAGE["occupancy"]},
        "tenure": {"type": "string", "enum": COVERAGE["tenure"]},
        "area_sqft": {"type": "number", "description": "Built-up area in sq ft (150-40000)."},
        "bedrooms": {"type": "integer"},
        "bathrooms": {"type": "integer"},
        "floor": {"type": "integer"},
        "total_floors": {"type": "integer"},
        "age_years": {"type": "integer"},
        "parking": {"type": "integer"},
        "lift": {"type": "integer", "enum": [0, 1]},
        "balcony": {"type": "integer"},
        "metro_distance_km": {"type": "number"},
        "school_distance_km": {"type": "number"},
        "hospital_distance_km": {"type": "number"},
        "highway_distance_km": {"type": "number"},
        "crime_index": {"type": "number", "description": "1 (safe) to 10 (high crime)."},
        "requested_loan_inr": {"type": "integer", "description": "Loan amount requested, in INR. 0 = reference LTV."},
    },
    "required": ["city", "locality", "area_sqft"],
}

TOOLS = [
    {
        "name": "valuate_property",
        "description": (
            "Value one Indian property. Returns point estimate, conformal p10-p90 interval, "
            "rupee attribution per driver group, comparable sales, confidence, and an RBI/NHB "
            "lending policy position with reason codes and a recommended max loan sized on the p10. "
            "Runs locally; no network call, no API key."
        ),
        "inputSchema": PROPERTY_SCHEMA,
    },
    {
        "name": "batch_valuate",
        "description": "Value up to 40 properties in one call. Returns per-row value, interval, confidence, decision and risk grade, plus the automated share.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "properties": {"type": "array", "items": PROPERTY_SCHEMA, "maxItems": 40},
            },
            "required": ["properties"],
        },
    },
    {
        "name": "check_loan",
        "description": "Evaluate a requested loan against a property's collateral value. Returns LTV, effective cap, risk grade, reason codes and max loan recommended.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "property": PROPERTY_SCHEMA,
                "requested_loan_inr": {"type": "integer", "description": "Loan amount in INR."},
            },
            "required": ["property", "requested_loan_inr"],
        },
    },
    {
        "name": "get_coverage",
        "description": "List covered cities, localities, property types and allowed categorical values. Call this before valuing anything.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_ready_reckoner_rate",
        "description": "Look up the government ready-reckoner / circle rate (or model-derived fallback) for a micro-market, in ₹/sqft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "locality": {"type": "string"},
                "property_type": {"type": "string"},
            },
            "required": ["city", "locality"],
        },
    },
    {
        "name": "get_model_metrics",
        "description": "Return the engine's measured holdout metrics, interval coverage, grouped CV and benchmark comparison.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _tool_result(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}


def _handle_tool(name: str, args: dict) -> dict:
    if name == "valuate_property":
        return _tool_result(_run_one(args))
    if name == "batch_valuate":
        items = args.get("properties", [])
        if not isinstance(items, list) or not items:
            raise ValueError("properties must be a non-empty array")
        if len(items) > 40:
            raise ValueError("batch limit is 40 properties")
        rows = []
        errors = []
        for i, item in enumerate(items):
            try:
                r = _run_one(item)
                decision = r["lending"]
                rows.append({
                    "locality": r["input"]["locality"],
                    "property_type": r["input"]["property_type"],
                    "area_sqft": r["input"]["area_sqft"],
                    "value": r["value"],
                    "value_low": r["value_low"],
                    "value_high": r["value_high"],
                    "confidence": r["confidence"],
                    "decision": decision["decision"],
                    "decision_label": decision["decision_label"],
                    "risk_grade": decision["risk_grade"],
                    "flags": r["flags"],
                })
            except ValueError as exc:
                errors.append({"index": i, "error": str(exc)})
        return _tool_result({"count": len(rows), "rows": rows, "errors": errors})
    if name == "check_loan":
        property_payload = args["property"]
        result = _run_one({**property_payload, "requested_loan_inr": args["requested_loan_inr"]})
        return _tool_result({
            "valuation": {
                "value": result["value"],
                "value_low": result["value_low"],
                "value_high": result["value_high"],
                "confidence": result["confidence"],
            },
            "lending": result["lending"],
        })
    if name == "get_coverage":
        return _tool_result({
            "cities": COVERAGE["city_names"],
            "localities_by_city": COVERAGE["localities_by_city"],
            "property_types": COVERAGE["property_types"],
            "furnishing": COVERAGE["furnishing"],
            "occupancy": COVERAGE["occupancy"],
            "tenure": COVERAGE["tenure"],
        })
    if name == "get_ready_reckoner_rate":
        return _tool_result(ready_reckoner.rate(
            args["city"], args["locality"], args.get("property_type", "Apartment")
        ))
    if name == "get_model_metrics":
        meta = json.loads(Path(ROOT / "artifacts" / "model.json").read_text(encoding="utf-8")) if False else None
        # Load metrics from the artifact via the app's meta shape is not available here;
        # read the raw artifact metrics block.
        artifact = json.loads((ROOT / "artifacts" / "model.json").read_text(encoding="utf-8"))
        return _tool_result({
            "corpus": artifact.get("corpus"),
            "holdout": artifact["metrics"]["holdout"],
            "interval": artifact["metrics"]["interval"],
            "grouped_cv": artifact["metrics"]["grouped_cv"],
            "benchmarks": artifact["metrics"]["benchmarks"],
        })
    raise ValueError(f"unknown tool: {name}")


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> None:
    # Keep stdout clean for the protocol; send diagnostics to stderr.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method")
        rid = request.get("id")
        params = request.get("params") or {}

        # Notifications have no id and expect no response.
        if rid is None and method and method.startswith("notifications/"):
            continue

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments") or {}
                result = _handle_tool(tool_name, tool_args)
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "prompts/list":
                result = {"prompts": []}
            elif method == "ping":
                result = {}
            else:
                raise ValueError(f"method not found: {method}")
            _write({"jsonrpc": "2.0", "id": rid, "result": result})
        except Exception as exc:  # noqa: BLE001 - protocol must not crash on bad input
            _write({"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32000, "message": str(exc)}})


if __name__ == "__main__":
    main()
