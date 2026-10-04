#!/usr/bin/env python3
"""Build MANIFEST.sha256 over all project deliverables.

Deterministic: sorted relative paths, UTF-8, LF line endings. The manifest
covers every file in the project except itself, cache/build artifacts, and
version-control metadata.

Usage:
    python scripts/build_manifest.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "MANIFEST.sha256"

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {MANIFEST_NAME}


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deliverables() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDED_FILES:
            continue
        files.append(rel)
    return sorted(files, key=lambda rel: rel.as_posix())


def main() -> int:
    lines = [f"{sha256_hex(ROOT / rel)}  {rel.as_posix()}" for rel in deliverables()]
    manifest = "\n".join(lines) + "\n"
    (ROOT / MANIFEST_NAME).write_text(manifest, encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST_NAME} with {len(lines)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
