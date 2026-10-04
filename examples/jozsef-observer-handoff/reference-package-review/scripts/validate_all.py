#!/usr/bin/env python3
"""Run the full local validation workflow.

Steps:
  1. Validate every EvidenceEnvelope fixture against the JSON Schema.
  2. Recompute and verify every integrity digest.
  3. Scan every fixture for forbidden authorization semantics.
  4. Regenerate every fixture in memory and require byte-identical output
     (determinism, AT-15).
  5. Verify EGA authorization context separation (AT-13).
  6. Run the pytest suite (AT-18) and propagate its exit code.

Usage:
    python scripts/validate_all.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nextone_interop.canonical import verify_integrity  # noqa: E402
from nextone_interop.evidence import forbidden_semantics_present  # noqa: E402
from nextone_interop.fixturegen import (  # noqa: E402
    CATALOG_PATH,
    FIXTURES_DIR,
    FIXTURE_SPECS,
    build_envelope,
    render_envelope,
)
from nextone_interop.validation import validate_envelope  # noqa: E402

EGA_CONTEXT_DIR = ROOT / "tests" / "ega_context"
OBSERVER_PACKAGE_DIR = ROOT / "src" / "nextone_interop"

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    status = "ok  " if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def envelope_fixtures() -> list[Path]:
    paths = []
    for spec in FIXTURE_SPECS:
        path = FIXTURES_DIR / spec.relative_path
        paths.append(path)
    return paths


def step_fixtures() -> None:
    print("== fixture validation ==")
    for path in envelope_fixtures():
        label = path.relative_to(ROOT)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        try:
            validate_envelope(envelope)
            check(True, f"{label}: schema valid")
        except Exception as exc:  # noqa: BLE001 - report and continue
            check(False, f"{label}: schema valid ({exc})")
            continue
        check(verify_integrity(envelope), f"{label}: integrity digest verifies")
        check(
            not forbidden_semantics_present(envelope),
            f"{label}: no forbidden authorization semantics",
        )


def step_determinism() -> None:
    print("== determinism (AT-15) ==")
    for spec in FIXTURE_SPECS:
        path = FIXTURES_DIR / spec.relative_path
        on_disk = path.read_text(encoding="utf-8")
        regenerated = render_envelope(build_envelope(CATALOG_PATH, spec))
        check(
            on_disk == regenerated,
            f"{path.relative_to(ROOT)}: byte-identical regeneration",
        )


def step_ega_context_separation() -> None:
    print("== EGA authorization context separation (AT-13) ==")
    check(EGA_CONTEXT_DIR.is_dir(), "tests/ega_context exists outside fixtures/")
    for path in sorted(EGA_CONTEXT_DIR.glob("*.json")):
        check(True, f"{path.relative_to(ROOT)}: outside Observer evidence tree")
    hits = []
    for py_file in sorted(OBSERVER_PACKAGE_DIR.rglob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        if "ega_context" in text or "authorized_price_2500" in text:
            hits.append(py_file.name)
    check(not hits, f"Observer package never references EGA authorization context (hits={hits})")


def step_pytest() -> int:
    print("== pytest suite (AT-18) ==")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
    )
    return result.returncode


def main() -> int:
    step_fixtures()
    step_determinism()
    step_ega_context_separation()
    pytest_rc = step_pytest()

    print("== summary ==")
    if FAILURES:
        print(f"{len(FAILURES)} validation failure(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    if pytest_rc != 0:
        print(f"pytest exited with {pytest_rc}")
        return pytest_rc
    print("all validations passed; pytest green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
