#!/usr/bin/env python3
"""Generate the golden EvidenceEnvelope from the local catalog source.

The observed value is read through the read-only catalog source interface;
nothing is hard-coded (AT-14). With the default fixed observation time the
output bytes and digest are fully deterministic (AT-15).

Usage:
    python scripts/generate_golden_evidence.py
    python scripts/generate_golden_evidence.py --observed-at 2026-10-03T19:00:00Z --output <path>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nextone_interop.fixturegen import (  # noqa: E402
    CATALOG_PATH,
    GOLDEN_SPEC,
    build_envelope,
    render_envelope,
)

DEFAULT_OUTPUT = ROOT / "fixtures" / "golden" / "known_price_2500.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="path to the local catalog fixture")
    parser.add_argument("--observed-at", default=GOLDEN_SPEC.observed_at, help="RFC 3339 UTC observation time")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output file for the golden evidence")
    args = parser.parse_args(argv)

    envelope = build_envelope(args.catalog, GOLDEN_SPEC, observed_at=args.observed_at)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_envelope(envelope), encoding="utf-8")

    print(f"wrote:  {output}")
    print(f"digest: {envelope['integrity']['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
