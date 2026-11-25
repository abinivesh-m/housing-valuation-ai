"""Commercial surface: key auth, quota accounting, and the open demo.

The public demo must stay usable without a key, a rejected request must not
consume quota, and a key must stop working exactly when its monthly allowance
is gone. Those three properties are what a paying integration depends on.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app as application
import metering

SAMPLE = {
    "city": "Bangalore",
    "locality": "Koramangala",
    "property_type": "Apartment",
    "area_sqft": 1250,
    "bedrooms": 3,
    "bathrooms": 2,
}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("HVA_API_KEYS", "test_key:starter:3")
    monkeypatch.setenv("HV_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    metering._MEMORY.clear()
    return TestClient(application.app)


def test_public_demo_needs_no_key(client):
    response = client.post("/api/valuate", json=SAMPLE)
    assert response.status_code == 200
    assert response.json()["value"] > 0


def test_missing_key_is_rejected(client):
    response = client.post("/api/v1/valuate", json=SAMPLE)
    assert response.status_code == 401
    assert "X-API-Key" in response.text or "missing" in response.text.lower()


def test_wrong_key_is_rejected(client):
    response = client.post(
        "/api/v1/valuate", json=SAMPLE, headers={"X-API-Key": "not_a_key"}
    )
    assert response.status_code == 401


def test_valid_key_returns_metered_payload(client):
    response = client.post(
        "/api/v1/valuate", json=SAMPLE, headers={"X-API-Key": "test_key"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metered"] == {
        "plan": "starter",
        "used": 1,
        "limit": 3,
        "resets_at": body["metered"]["resets_at"],
    }
    assert response.headers["X-Quota-Limit"] == "3"
    assert response.headers["X-Quota-Used"] == "1"
    assert response.headers["X-Quota-Remaining"] == "2"
    assert response.headers["Cache-Control"] == "no-store"
    assert body["lending"]["decision"]


def test_quota_is_enforced(client):
    for expected in (1, 2, 3):
        response = client.post(
            "/api/v1/valuate", json=SAMPLE, headers={"X-API-Key": "test_key"}
        )
        assert response.status_code == 200
        assert response.json()["metered"]["used"] == expected

    blocked = client.post(
        "/api/v1/valuate", json=SAMPLE, headers={"X-API-Key": "test_key"}
    )
    assert blocked.status_code == 429
    assert blocked.headers["X-Quota-Remaining"] == "0"


def test_rejected_request_does_not_consume_quota(client):
    bad = dict(SAMPLE, city="Atlantis")
    response = client.post(
        "/api/v1/valuate", json=bad, headers={"X-API-Key": "test_key"}
    )
    assert response.status_code == 422

    usage = client.get("/api/v1/usage", headers={"X-API-Key": "test_key"})
    assert usage.status_code == 200
    assert usage.json()["used"] == 0
    assert usage.json()["remaining"] == 3


def test_usage_endpoint_does_not_consume(client):
    first = client.get("/api/v1/usage", headers={"X-API-Key": "test_key"})
    second = client.get("/api/v1/usage", headers={"X-API-Key": "test_key"})
    assert first.json()["used"] == second.json()["used"] == 0


def test_batch_is_metered_once_per_call(client):
    response = client.post(
        "/api/v1/batch",
        json=[SAMPLE, dict(SAMPLE, locality="Indiranagar", area_sqft=1600)],
        headers={"X-API-Key": "test_key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["metered"]["used"] == 1


def test_unconfigured_deployment_refuses_commercial_calls(monkeypatch, tmp_path):
    monkeypatch.delenv("HVA_API_KEYS", raising=False)
    monkeypatch.setenv("HV_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    metering._MEMORY.clear()
    local = TestClient(application.app)
    response = local.post(
        "/api/v1/valuate", json=SAMPLE, headers={"X-API-Key": "anything"}
    )
    assert response.status_code == 401
    assert "not configured" in response.text
