#!/usr/bin/env python3
"""Regenerate every EvidenceEnvelope fixture deterministically.

Golden, negative, and conflict fixtures are all produced by the Observer
reading through the catalog source. Existing on-disk content is overwritten.

Usage:
    python scripts/generate_fixtures.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nextone_interop.fixturegen import (  # noqa: E402
    CATALOG_PATH,
    FIXTURES_DIR,
    FIXTURE_SPECS,
    build_envelope,
    render_envelope,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="path to the local catalog fixture")
    parser.add_argument("--fixtures-dir", default=str(FIXTURES_DIR), help="fixture output root")
    args = parser.parse_args(argv)

    out_root = Path(args.fixtures_dir)
    for spec in FIXTURE_SPECS:
        envelope = build_envelope(args.catalog, spec)
        target = out_root / spec.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_envelope(envelope), encoding="utf-8")
        print(f"wrote:  {target}")
        print(f"digest: {envelope['integrity']['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
