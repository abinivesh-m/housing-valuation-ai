"""Assemble the uploadable skill zip.

The marketplace expects SKILL.md at the root of the archive, with the code it
needs alongside it. This script pulls the engine and artifacts out of the
repository so the skill ships one copy of each and the repository stays the
single source of truth.

    python skill/build_zip.py

Writes skill/dist/housing-valuation-india.zip and prints its contents.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "housing-valuation-india"
DIST = ROOT / "skill" / "dist"
OUT = DIST / "housing-valuation-india.zip"

LIMIT_MB = 50

INCLUDE = [
    (SKILL / "SKILL.md", "SKILL.md"),
    (SKILL / "scripts" / "valuate.py", "scripts/valuate.py"),
    (ROOT / "ingest.py", "ingest.py"),
    (ROOT / "mcp_server.py", "mcp_server.py"),
    (ROOT / "engine" / "__init__.py", "engine/__init__.py"),
    (ROOT / "engine" / "model.py", "engine/model.py"),
    (ROOT / "engine" / "valuation.py", "engine/valuation.py"),
    (ROOT / "engine" / "lending.py", "engine/lending.py"),
    (ROOT / "engine" / "geo.py", "engine/geo.py"),
    (ROOT / "engine" / "ready_reckoner.py", "engine/ready_reckoner.py"),
    (ROOT / "artifacts" / "model.json", "artifacts/model.json"),
    (ROOT / "artifacts" / "comps.json", "artifacts/comps.json"),
    (ROOT / "artifacts" / "locality_stats.json", "artifacts/locality_stats.json"),
    (ROOT / "artifacts" / "coverage.json", "artifacts/coverage.json"),
    (ROOT / "LICENSE", "LICENSE"),
]


def main() -> None:
    missing = [str(src) for src, _ in INCLUDE if not src.exists()]
    if missing:
        raise SystemExit("missing inputs:\n  " + "\n  ".join(missing))

    DIST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, arcname in INCLUDE:
            zf.write(src, arcname)
        zf.writestr(
            "requirements.txt",
            "# Runtime dependency for the skill. Nothing else is needed.\nnumpy>=1.26\n",
        )

    size_mb = OUT.stat().st_size / (1024 * 1024)
    if size_mb > LIMIT_MB:
        raise SystemExit(f"zip is {size_mb:.1f} MB, over the {LIMIT_MB} MB marketplace limit")

    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
    print(f"wrote {OUT.relative_to(ROOT)}  ({size_mb:.2f} MB, {len(names)} files)")
    for name in names:
        print(f"  {name}")


if __name__ == "__main__":
    main()
