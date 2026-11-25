"""Commercial access layer: API keys and per-key call quotas.

The public demo endpoints in ``app.py`` stay open and unmetered on purpose: they
are the product tour, and a visitor should be able to load the console without a
key. This module guards only the ``/api/v1`` surface that paying customers call.

Configuration is entirely by environment variable, so the module is inert
until a deployment opts in:

    HVA_API_KEYS=key:plan:quota,key:plan:quota

Quota counters are kept in Upstash Redis when configured, and fall back to a
per-process dict otherwise (fine for local runs, wrong for serverless -- a
cold start resets it, so production must set the Upstash pair):

    UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
    UPSTASH_REDIS_REST_TOKEN=...

Billing policy decisions worth stating out loud:

* If the counter backend is unreachable we allow the call and log a warning.
  Failing closed would take a paying customer's product down because Redis
  hiccuped; the reconciliation cost of the occasional free call is lower.
* Keys are compared with ``secrets.compare_digest`` so a wrong key cannot be
  recovered by timing.
* Quota resets on the calendar month, keyed into the Redis key name rather
  than by a sweep, so there is no job to forget to run.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger("hva.metering")

DEFAULT_QUOTA = 500
_MEMORY: dict[str, int] = {}


@dataclass(frozen=True)
class Principal:
    plan: str
    quota: int
    key_id: str
    used: int = 0
    remaining: int = 0
    reset_at: str = ""
    backend: str = field(default="memory")

    def headers(self) -> dict[str, str]:
        return {
            "X-Quota-Limit": str(self.quota),
            "X-Quota-Used": str(self.used),
            "X-Quota-Remaining": str(max(self.remaining, 0)),
            "X-Quota-Reset": self.reset_at,
            "X-Plan": self.plan,
        }


class AuthError(Exception):
    """Missing or unrecognised key."""


class QuotaExceeded(Exception):
    def __init__(self, principal: Principal) -> None:
        self.principal = principal
        super().__init__("monthly quota exhausted")


def _configured_keys() -> dict[str, tuple[str, int]]:
    raw = os.environ.get("HVA_API_KEYS", "").strip()
    keys: dict[str, tuple[str, int]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        key = parts[0]
        plan = parts[1] if len(parts) > 1 and parts[1] else "starter"
        try:
            quota = int(parts[2]) if len(parts) > 2 and parts[2] else DEFAULT_QUOTA
        except ValueError:
            quota = DEFAULT_QUOTA
        if key:
            keys[key] = (plan, quota)
    return keys


def enabled() -> bool:
    return bool(_configured_keys())


def _period() -> tuple[str, str]:
    """Current billing period as (key suffix, ISO date the quota resets)."""
    now = time.gmtime()
    suffix = f"{now.tm_year}{now.tm_mon:02d}"
    year, month = (now.tm_year + 1, 1) if now.tm_mon == 12 else (now.tm_year, now.tm_mon + 1)
    return suffix, f"{year}-{month:02d}-01T00:00:00Z"


def _key_id(key: str) -> str:
    """Stable, non-reversible identifier for logs and counters."""
    import hashlib

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _upstash() -> tuple[str, str] | None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    return (url, token) if url and token else None


def _redis_incr(redis_key: str, ttl_seconds: int = 40 * 24 * 3600) -> int | None:
    """INCR + EXPIRE in one pipeline round trip. None when unavailable."""
    cfg = _upstash()
    if cfg is None:
        return None
    url, token = cfg
    body = json.dumps(
        [["INCR", redis_key], ["EXPIRE", redis_key, str(ttl_seconds)]]
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/pipeline",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        first = payload[0] if isinstance(payload, list) and payload else {}
        result = first.get("result") if isinstance(first, dict) else None
        return int(result) if result is not None else None
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError) as exc:
        log.warning("upstash unavailable, counting in memory: %s", exc)
        return None


def _match(api_key: str | None) -> tuple[str, str, int]:
    keys = _configured_keys()
    if not keys:
        raise AuthError("commercial API is not configured on this deployment")
    if not api_key:
        raise AuthError("missing X-API-Key header")

    matched: str | None = None
    for candidate in keys:
        if secrets.compare_digest(candidate, api_key):
            matched = candidate
            break
    if matched is None:
        raise AuthError("unrecognised API key")
    plan, quota = keys[matched]
    return matched, plan, quota


def _redis_get(redis_key: str) -> int | None:
    cfg = _upstash()
    if cfg is None:
        return None
    url, token = cfg
    body = json.dumps(["GET", redis_key]).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/pipeline",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        first = payload[0] if isinstance(payload, list) and payload else {}
        result = first.get("result") if isinstance(first, dict) else None
        return int(result) if result is not None else 0
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError) as exc:
        log.warning("upstash unavailable, reading memory: %s", exc)
        return None


def authorise(api_key: str | None, *, count: bool = True) -> Principal:
    """Validate a key and, unless ``count`` is false, consume one call.

    Callers that must not charge for a rejected request check with
    ``count=False`` first, do the work, then consume. Worst case in a race is
    one unmetered call, which is cheaper than billing for a 422.
    """
    matched, plan, quota = _match(api_key)
    suffix, reset_at = _period()
    key_id = _key_id(matched)
    redis_key = f"hva:usage:{key_id}:{suffix}"

    if count:
        used = _redis_incr(redis_key)
        backend = "upstash"
        if used is None:
            backend = "memory"
            _MEMORY[redis_key] = _MEMORY.get(redis_key, 0) + 1
            used = _MEMORY[redis_key]
    else:
        used = _redis_get(redis_key)
        backend = "upstash"
        if used is None:
            backend = "memory"
            used = _MEMORY.get(redis_key, 0)

    principal = Principal(
        plan=plan,
        quota=quota,
        key_id=key_id,
        used=used,
        remaining=quota - used,
        reset_at=reset_at,
        backend=backend,
    )
    if count and used > quota:
        raise QuotaExceeded(principal)
    return principal


def usage(api_key: str | None) -> Principal:
    """Read remaining quota without consuming a call."""
    return authorise(api_key, count=False)
