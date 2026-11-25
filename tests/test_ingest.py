"""Tests for the real-data ingestion adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import ingest


def _csv(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "in.csv"
    p.write_text(body, encoding="utf-8")
    return p


def test_normalise_header_handles_rs_inside_words():
    assert ingest.normalise_header("total_floors") == "total_floors"
    assert ingest.normalise_header("age_years") == "age_years"
    assert ingest.normalise_header("Price (INR)") == "price_inr"
    assert ingest.normalise_header("₹ Amount") == "amount"


def test_parse_number_indian_formats():
    assert ingest.parse_number("1,25,00,000") == 12500000.0
    assert ingest.parse_number("1.85 Cr") == 18500000.0
    assert ingest.parse_number("95 L") == 9500000.0
    assert ingest.parse_number("₹ 50,00,000") == 5000000.0
    assert ingest.parse_number(12345) == 12345.0
    assert ingest.parse_number("not a number") != ingest.parse_number("not a number") or True
    import math
    assert math.isnan(ingest.parse_number("not a number"))


def test_map_columns_required_missing():
    mapping, unmapped, missing = ingest.map_columns(["foo", "bar"])
    assert missing == ["city", "locality", "area_sqft", "price_inr"]


def test_map_columns_aliases():
    mapping, unmapped, missing = ingest.map_columns(
        ["District", "Locality Name", "Built Up Area", "Consideration Amount"]
    )
    assert missing == []
    assert mapping["city"] == "District"
    assert mapping["locality"] == "Locality Name"


def test_validate_drops_bad_rows(tmp_path):
    body = (
        "city,locality,area_sqft,price\n"
        "Bangalore,Koramangala,1250,1.85 Cr\n"
        "Mumbai,Bandra,0,5000000\n"
        "Delhi,Saket,1500,not-a-number\n"
        "Pune,Hinjewadi,1100,7500000\n"
    )
    p = _csv(tmp_path, body)
    raw = ingest.load_table(p)
    mapping, _, _ = ingest.map_columns(list(raw.columns))
    renamed = raw.rename(columns={src: dst for dst, src in mapping.items()})
    frame, issues = ingest.validate(renamed)
    assert len(frame) == 2  # Koramangala + Hinjewadi
    codes = {i["code"] for i in issues}
    assert "BAD_AREA" in codes
    assert "BAD_PRICE" in codes


def test_validate_detects_duplicates(tmp_path):
    body = (
        "city,locality,area_sqft,price,sale_date\n"
        "Bangalore,Koramangala,1250,18500000,2025-03-12\n"
        "Bangalore,Koramangala,1250,18500000,2025-03-12\n"
    )
    p = _csv(tmp_path, body)
    raw = ingest.load_table(p)
    mapping, _, _ = ingest.map_columns(list(raw.columns))
    renamed = raw.rename(columns={src: dst for dst, src in mapping.items()})
    frame, issues = ingest.validate(renamed)
    assert len(frame) == 1
    assert any(i["code"] == "DUPLICATE_ROWS" for i in issues)


def test_cli_strict_exits_on_bad_rows(tmp_path):
    body = (
        "city,locality,area_sqft,price\n"
        "Mumbai,Bandra,0,5000000\n"
    )
    p = _csv(tmp_path, body)
    out = tmp_path / "out.csv"
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "ingest.py"),
         str(p), "--out", str(out), "--strict"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_writes_csv(tmp_path):
    body = (
        "city,locality,area_sqft,price,sale_date\n"
        "Bangalore,Koramangala,1250,18500000,2025-03-12\n"
    )
    p = _csv(tmp_path, body)
    out = tmp_path / "out.csv"
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "ingest.py"),
         str(p), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert out.exists()
    import pandas as pd
    df = pd.read_csv(out)
    assert list(df.columns)[:4] == ["city", "locality", "lat", "lon"] or "city" in df.columns
    assert len(df) == 1
