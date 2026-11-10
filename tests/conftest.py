"""Test session setup: isolate the audit ledger and make the app importable."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Never let the test suite touch the developer's real audit chain.
os.environ["HV_AUDIT_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hv-audit-test-"), "chain.jsonl"
)
