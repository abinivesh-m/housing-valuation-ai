"""
Tamper-evident audit ledger.

Every valuation and every lending decision appends an entry:

    hash = sha256(prev_hash | seq | ts | kind | ref | payload_digest)

so altering any historical entry breaks every hash after it, and
`verify()` recomputes the whole chain and reports the first broken link.

Storage is an append-only JSONL file on the instance disk. That is enough to
demonstrate the mechanism and to survive a warm serverless instance, but it is
not durable: production replaces the file with DynamoDB, S3 Object Lock or an
append-only Postgres table. docs/ARCHITECTURE.md states this gap explicitly
rather than implying the demo is a system of record.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone

GENESIS = "0" * 64
_START = time.monotonic()


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    """Append-only hash chain backed by a JSONL file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        # (last_seq, head_hash, file_size) — lets append() avoid re-parsing the
        # whole ledger on every write. The size check catches a writer from
        # another process; a same-size rewrite is caught by verify().
        self._state: tuple[int, str, int] | None = None

    # -- internals ---------------------------------------------------------
    def _read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        entries: list[dict] = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    @staticmethod
    def _material(prev: str, e: dict) -> str:
        return f"{prev}|{e['seq']}|{e['ts']}|{e['kind']}|{e['ref']}|{e['payload_digest']}"

    def _head(self) -> tuple[int, str]:
        """Last sequence number and head hash, cached against the file size."""
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        if self._state is not None and self._state[2] == size:
            return self._state[0], self._state[1]
        entries = self._read()
        self._state = (
            entries[-1]["seq"] if entries else 0,
            entries[-1]["hash"] if entries else GENESIS,
            size,
        )
        return self._state[0], self._state[1]

    # -- public ------------------------------------------------------------
    def append(self, kind: str, ref: str, payload: dict) -> dict:
        with self._lock:
            last_seq, prev = self._head()
            seq = last_seq + 1
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            payload_digest = _digest(payload)
            entry = {
                "seq": seq,
                "ts": ts,
                "kind": kind,
                "ref": ref,
                "payload_digest": payload_digest,
                "prev_hash": prev,
                "detail": payload,
            }
            entry["hash"] = hashlib.sha256(self._material(prev, entry).encode("utf-8")).hexdigest()
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")
            self._state = (seq, entry["hash"], os.path.getsize(self.path))
            return entry

    def tail(self, limit: int = 25) -> list[dict]:
        return self._read()[-limit:][::-1]

    def verify(self) -> dict:
        entries = self._read()
        if not entries:
            return {"valid": True, "entries": 0, "detail": "ledger is empty", "checked_at": _now()}

        prev = GENESIS
        for expected, entry in enumerate(entries, start=1):
            recomputed = hashlib.sha256(self._material(prev, entry).encode("utf-8")).hexdigest()
            payload_intact = _digest(entry.get("detail", {})) == entry["payload_digest"]
            if (
                entry["seq"] != expected
                or entry["prev_hash"] != prev
                or recomputed != entry["hash"]
                or not payload_intact
            ):
                return {
                    "valid": False,
                    "entries": len(entries),
                    "broken_at_seq": entry.get("seq"),
                    "detail": (
                        "payload does not match its digest"
                        if not payload_intact
                        else "hash chain broken — an entry was modified or reordered"
                    ),
                    "checked_at": _now(),
                }
            prev = entry["hash"]

        return {
            "valid": True,
            "entries": len(entries),
            "head_hash": entries[-1]["hash"],
            "detail": "every entry re-hashes to the next link; chain intact",
            "checked_at": _now(),
        }

    def stats(self) -> dict:
        entries = self._read()
        kinds: dict[str, int] = {}
        for e in entries:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return {
            "entries": len(entries),
            "by_kind": kinds,
            "head_hash": entries[-1]["hash"] if entries else GENESIS,
            "storage": "append-only JSONL on instance disk (ephemeral, not durable)",
            "uptime_s": round(time.monotonic() - _START, 1),
        }


DEFAULT_PATH = os.environ.get(
    "HV_AUDIT_PATH", os.path.join(tempfile.gettempdir(), "hv_audit_chain.jsonl")
)
ledger = Ledger(DEFAULT_PATH)

# module-level convenience wrappers used by the API layer
append = ledger.append
tail = ledger.tail
verify = ledger.verify
stats = ledger.stats
