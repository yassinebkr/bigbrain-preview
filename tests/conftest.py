"""Shared test fixtures.

Every test gets an isolated evidence root by default: any code path that
records through the deterministic gate (PythonBrain's Honk loop, the
manual-run API) writes to a throwaway directory instead of polluting the
developer's real ``data/evidence/`` registry — a full pytest run used to
inject ~150 mock-LLM manifests into it.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("BIGBRAIN_SESSIONS_DIR", str(tmp_path / "sessions"))
