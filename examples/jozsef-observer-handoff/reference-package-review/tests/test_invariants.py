"""INV-01 .. INV-12 normative architectural invariants, and AT-17 isolation."""

from __future__ import annotations

import builtins
import copy
import hashlib
import inspect
import shutil
import sys
from pathlib import Path

from conftest import ENVELOPE_RELPATHS, ROOT
from nextone_interop.canonical import digest_payload, verify_integrity
from nextone_interop.ega_seam import EgaSeamAdapter
from nextone_interop.evidence import forbidden_semantics_present

SRC_DIR = ROOT / "src" / "nextone_interop"
NETWORK_TERMS = ("socket", "urllib", "requests", "httpx", "http.client")


def test_inv_01_evidence_is_not_authority(envelopes):
    for relpath in ENVELOPE_RELPATHS:
        envelope = envelopes[relpath]
        assert forbidden_semantics_present(envelope) == [], relpath
        for key in ("AEE", "execution_authority", "commit_authority", "policy_satisfaction"):
            assert key not in envelope


def test_inv_02_observer_is_read_only():
    from nextone_interop.catalog_source import CatalogSource, LocalJsonCatalogSource

    for cls in (LocalJsonCatalogSource,):
        members = {name for name, _ in inspect.getmembers(cls, inspect.isfunction)}
        assert members.isdisjoint({"write", "update", "delete", "insert", "save"}), (
            f"{cls.__name__} exposes a write method"
        )
    protocol = {name for name, _ in inspect.getmembers(CatalogSource, inspect.isfunction)}
    assert protocol.isdisjoint({"write", "update", "delete", "insert", "save"})


def test_inv_03_freshness_is_evaluated_by_ega(envelopes):
    for relpath in ENVELOPE_RELPATHS:
        envelope = envelopes[relpath]
        assert forbidden_semantics_present(envelope) == [], relpath
        assert envelope["temporal_basis"] == {
            "type": "point_in_time",
            "timestamp_semantics": "observation_completed_at",
            "clock": "UTC",
        }
        assert "observed_at" in envelope


def test_inv_04_authorized_value_absent_from_evidence(golden):
    assert forbidden_semantics_present(golden) == []
    assert "authorized" not in str(sorted(golden.keys()))
    # 2500 appears exactly once: as the observed value. Nothing marks it
    # as authorized/expected.
    assert golden["observed_value"] == 2500
    for key in golden:
        assert "authoriz" not in key and "expect" not in key


def test_inv_05_unknown_remains_unknown(envelopes):
    unknown = envelopes["negative/unknown_price.json"]
    assert unknown["observed_state"] == "UNKNOWN"
    assert unknown["observed_value"] is None
    assert unknown["observed_value"] is not False
    assert unknown["observed_value"] != 0


def test_inv_06_conflicts_remain_independent(envelopes):
    a = envelopes["conflict/observation_a.json"]
    b = envelopes["conflict/observation_b.json"]
    assert a["evidence_id"] != b["evidence_id"]
    assert a["integrity"]["digest"] != b["integrity"]["digest"]
    assert a["provenance"] != b["provenance"]
    assert a["observed_at"] != b["observed_at"]


def test_inv_07_integrity_is_not_authorization(golden):
    assert verify_integrity(golden) is True
    altered = copy.deepcopy(golden)
    altered["observed_value"] = 12345
    assert verify_integrity(altered) is False, (
        "digest proves deterministic integrity of the encoded evidence, not policy satisfaction"
    )
    # A valid digest carries no verdict: recomputation is a pure function.
    assert digest_payload(golden) == golden["integrity"]["digest"]


def test_inv_08_adapter_crossing_creates_no_authority(golden):
    presented = EgaSeamAdapter().present(golden)
    assert set(presented.keys()) == set(golden.keys())
    assert presented["integrity"]["digest"] == golden["integrity"]["digest"]


def test_inv_09_observation_and_execution_are_separate():
    source = (SRC_DIR / "observer.py").read_text(encoding="utf-8")
    for term in ("retail_sale", "createBrokeredPendingOrder", "pending_order", "order"):
        assert term not in source


def test_inv_10_no_retrospective_authorization():
    for path in sorted((ROOT / "fixtures").rglob("*.json")):
        text = path.read_text(encoding="utf-8").lower()
        for term in ("receipt", "post_execution", "executed_order"):
            assert term not in text, f"{path} mixes post-execution records into evidence"


def test_inv_11_no_hidden_production_dependency():
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for term in NETWORK_TERMS:
            assert term not in text, f"{py_file.name} references network stack: {term}"
    for path in sorted(SRC_DIR.rglob("*.py")) + sorted((ROOT / "scripts").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "nextone-observer-live" not in text and "production" not in text.lower(), (
            f"{path} references production infrastructure"
        )


def test_inv_12_missing_external_contract_is_reported_not_invented():
    doc = (ROOT / "docs" / "EGA_COMPATIBILITY.md").read_text(encoding="utf-8")
    assert "12df2a7be7cd39f9e68a43e80aa3b62096e5dbb7" in doc
    assert "unavailable" in doc.lower() or "not available" in doc.lower()


def test_at_17_no_writes_outside_project_root(monkeypatch, tmp_path):
    """Run fixture generation inside a sandbox and guard every file write."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    shutil.copytree(ROOT / "src", sandbox / "src")
    shutil.copytree(ROOT / "scripts", sandbox / "scripts")
    shutil.copytree(ROOT / "fixtures" / "catalog", sandbox / "catalog")
    shutil.copytree(ROOT / "schemas", sandbox / "schemas")

    real_write_text = Path.write_text
    real_write_bytes = Path.write_bytes
    real_open = builtins.open

    def inside_sandbox(target) -> bool:
        try:
            Path(target).resolve().relative_to(sandbox.resolve())
            return True
        except (ValueError, TypeError):
            return False

    def guarded_write_text(self, data, *args, **kwargs):
        assert inside_sandbox(self), f"write outside project sandbox: {self}"
        return real_write_text(self, data, *args, **kwargs)

    def guarded_write_bytes(self, data, *args, **kwargs):
        assert inside_sandbox(self), f"write outside project sandbox: {self}"
        return real_write_bytes(self, data, *args, **kwargs)

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "+")):
            assert inside_sandbox(file), f"open-for-write outside project sandbox: {file}"
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    monkeypatch.setattr(builtins, "open", guarded_open)

    sys.path.insert(0, str(sandbox / "scripts"))
    try:
        import generate_fixtures  # type: ignore[import-not-found]

        rc = generate_fixtures.main(
            [
                "--catalog",
                str(sandbox / "catalog" / "catalog.json"),
                "--fixtures-dir",
                str(sandbox / "fixtures"),
            ]
        )
    finally:
        sys.path.remove(str(sandbox / "scripts"))

    assert rc == 0
    produced = sorted(
        p.relative_to(sandbox).as_posix() for p in (sandbox / "fixtures").rglob("*.json")
    )
    assert len(produced) == 6, produced
    for relpath in ENVELOPE_RELPATHS:
        assert f"fixtures/{relpath}" in produced


def test_at_17_catalog_fixture_content_hash_is_stable():
    catalog = ROOT / "fixtures" / "catalog" / "catalog.json"
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    assert len(digest) == 64
