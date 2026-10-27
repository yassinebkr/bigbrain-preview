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
    # Memory phase: persistent memory must never touch the real
    # ~/.bigbrain store from a test.
    monkeypatch.setenv("BIGBRAIN_MEMORY_DIR", str(tmp_path / "memory-chroma"))
    monkeypatch.setenv("BIGBRAIN_SOUL_FILE", str(tmp_path / "soul.json"))
    monkeypatch.setenv("BIGBRAIN_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    monkeypatch.setenv("BIGBRAIN_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
    from bigbrain.web import fs_api
    monkeypatch.setattr(fs_api, "_CURRENT_PROJECT_FILE", tmp_path / "navigation.json")
    from bigbrain.web import model_roles
    monkeypatch.setattr(model_roles, "_ROLES_FILE", tmp_path / "model_roles.json")
