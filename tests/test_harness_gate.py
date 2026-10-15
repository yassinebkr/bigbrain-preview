"""Deterministic harness P2 — executors, gate, and the Honk-loop wiring.

See docs/HARNESS-DETERMINISTE.md.
"""

import json
from pathlib import Path

import pytest

from bigbrain.verification.evidence import (
    EvidenceRepository,
    RunManifest,
    default_repository,
)
from bigbrain.verification.executors import (
    extract_requested_file,
    stage_compile,
    stage_contracts,
    stage_run,
    stage_syntax,
    stage_tests,
)
from bigbrain.verification.gate import RunGate


@pytest.fixture
def repo(tmp_path):
    return EvidenceRepository(tmp_path / "evidence")


GOOD = "print('Hello, World!')"
BAD = "def broken(:\n    pass"


class TestStageSyntax:
    def test_good_code_passes(self):
        stage = stage_syntax(GOOD)
        assert stage.status == "passed"
        assert stage.tool == "ast.parse"

    def test_syntax_error_carries_line(self):
        stage = stage_syntax(BAD)
        assert stage.status == "failed"
        assert stage.details["line"] == 1
        assert "error" in stage.details


class TestStageCompile:
    def test_good_code_passes(self):
        assert stage_compile(GOOD).status == "passed"

    def test_bad_code_fails(self):
        assert stage_compile(BAD).status == "failed"


class TestStageRun:
    def test_exit_zero_passes(self):
        assert stage_run({"exit_code": 0, "stderr": "", "stdout": "ok"}).status == "passed"

    def test_nonzero_exit_fails_with_last_error(self):
        stage = stage_run({"exit_code": 1, "stderr": "Traceback...\nNameError: x", "stdout": ""})
        assert stage.status == "failed"
        assert stage.details["error"] == "NameError: x"

    def test_timeout_fails(self):
        stage = stage_run({"exit_code": -1, "timed_out": True, "stderr": "", "stdout": ""})
        assert stage.status == "failed"
        assert stage.details["error"] == "execution timed out"


class TestStageTests:
    async def test_no_test_files_is_not_applicable(self, tmp_path):
        stage = await stage_tests(tmp_path)
        assert stage.status == "not_applicable"
        assert stage.details["reason"] == "no test files in work_dir"

    async def test_passing_test_file(self, tmp_path):
        (tmp_path / "test_hello.py").write_text(
            "def test_ok():\n    assert 1 + 1 == 2\n")
        stage = await stage_tests(tmp_path)
        assert stage.status == "passed"
        assert stage.details["tests"] == ["test_hello.py"]

    async def test_failing_test_file(self, tmp_path):
        (tmp_path / "test_hello.py").write_text(
            "def test_broken():\n    assert False\n")
        stage = await stage_tests(tmp_path)
        assert stage.status == "failed"
        assert stage.details["returncode"] != 0


class TestStageContracts:
    def test_no_requested_file_is_not_applicable(self, tmp_path):
        stage = stage_contracts(tmp_path, None)
        assert stage.status == "not_applicable"

    def test_missing_requested_file_fails(self, tmp_path):
        stage = stage_contracts(tmp_path, "hello.py")
        assert stage.status == "failed"
        assert stage.details["expected"] == "hello.py"

    def test_existing_requested_file_passes(self, tmp_path):
        (tmp_path / "hello.py").write_text(GOOD)
        stage = stage_contracts(tmp_path, "hello.py", persisted_file="hello.py")
        assert stage.status == "passed"
        assert stage.details["persisted_as"] == "hello.py"


class TestExtractRequestedFile:
    def test_french_request(self):
        assert extract_requested_file("crée un script hello.py qui affiche") == "hello.py"

    def test_no_file(self):
        assert extract_requested_file("écris un poème") is None

    def test_other_extensions(self):
        assert extract_requested_file("génère data.csv puis notes.md") == "data.csv"


class TestRunGate:
    async def test_clean_attempt_verdict_passed_and_persisted(self, repo, tmp_path):
        (tmp_path / "hello.py").write_text(GOOD)
        gate = RunGate(repo)
        manifest, verdict = await gate.evaluate_attempt(
            user_request="crée un script hello.py",
            code=GOOD,
            execution={"exit_code": 0, "stdout": "Hello, World!\n", "stderr": ""},
            work_dir=Path(tmp_path),
            requested_file="hello.py",
            persisted_file="hello.py",
            toolchain={"python": "3.13", "brain": "python_brain_0"},
        )
        assert verdict == "passed"
        assert manifest.status == "completed"
        assert manifest.verdict == "passed"
        assert [s.name for s in manifest.stages] == [
            "syntax", "compile", "run", "contracts", "tests"]

        # Roundtrip + immutability of the terminal manifest.
        loaded = repo.load_manifest(manifest.run_id)
        assert loaded == manifest
        with pytest.raises(Exception):
            repo.save_manifest(RunManifest.model_validate({
                **manifest.model_dump(mode="json"), "warnings": ["tampered"]}))

        # Spec persisted and hash-linked.
        spec = repo.load_spec(manifest.design_id, 1)
        assert spec is not None
        assert spec.content_sha256() == manifest.spec_sha256
        assert "hello.py" in spec.contracts[0]

        # Artifacts retrievable: code + stdout.
        code_sha = manifest.stages[0].artifact_hashes[0]
        assert repo.get_artifact(code_sha) == GOOD.encode("utf-8")

    async def test_broken_code_verdict_failed(self, repo, tmp_path):
        gate = RunGate(repo)
        manifest, verdict = await gate.evaluate_attempt(
            user_request="crée un script hello.py",
            code=BAD,
            execution={"exit_code": 1, "stdout": "", "stderr": "SyntaxError"},
            work_dir=Path(tmp_path),
            requested_file="hello.py",
        )
        assert verdict == "failed"
        assert manifest.status == "failed"
        stages = {s.name: s.status for s in manifest.stages}
        assert stages["syntax"] == "failed"
        assert stages["run"] == "failed"
        assert stages["contracts"] == "failed"  # file never persisted

    async def test_attempts_chain_via_parent_run_id(self, repo, tmp_path):
        gate = RunGate(repo)
        first, _ = await gate.evaluate_attempt(
            user_request="crée hello.py", code=BAD,
            execution={"exit_code": 1, "stdout": "", "stderr": "x"},
            work_dir=Path(tmp_path), attempt=1)
        second, _ = await gate.evaluate_attempt(
            user_request="crée hello.py", code=BAD,
            execution={"exit_code": 1, "stdout": "", "stderr": "x"},
            work_dir=Path(tmp_path), attempt=2, parent_run_id=first.run_id)
        assert second.parent_run_id == first.run_id
        assert second.metadata["attempt"] == 2

    async def test_gate_never_reraises_for_sparse_execution(self, repo, tmp_path):
        """Odd execution payloads are judged, not crashed on."""
        gate = RunGate(repo)
        manifest, verdict = await gate.evaluate_attempt(
            user_request="do something",
            code="",
            execution={},
            work_dir=Path(tmp_path),
        )
        assert verdict == "failed"
        assert {s.name: s.status for s in manifest.stages}["run"] == "failed"


def test_default_repository_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev2"))
    assert default_repository().root == (tmp_path / "ev2").absolute()


# ── PythonBrain integration ────────────────────────────────────────────────

import tempfile
from unittest.mock import AsyncMock, Mock


@pytest.fixture
def temp_work_dir(tmp_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_bus():
    bus = Mock()
    bus.send = AsyncMock()
    bus.send_result = AsyncMock()
    bus.broadcast_event = AsyncMock()
    bus.subscribe = Mock()
    bus.unsubscribe = Mock()
    return bus


class TestHonkLoopIntegration:
    """The PythonBrain records evidence and lets the gate drive retries."""

    @pytest.fixture
    def evidence_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "evidence"))

    @pytest.fixture
    async def brain(self, mock_bus, temp_work_dir):
        from bigbrain.brains.python_brain import PythonBrain

        brain = PythonBrain(
            name="test_python_brain",
            bus=mock_bus,
            workspace="test_workspace",
            timeout=10,
            work_dir=temp_work_dir,
            llm_provider=ScriptedProvider([
                "```python\nprint('Hello, World!')\n```",
            ]),
        )
        yield brain
        if brain.is_running():
            await brain.stop()

    async def test_success_records_passed_verdict(
            self, brain, temp_work_dir, evidence_root):
        result = await brain.handle_task(_task(
            "crée un script hello.py qui affiche Hello, World!"))
        assert result["success"] is True
        assert result["saved_as"] == "hello.py"
        verification = result["verification"]
        assert verification["verdict"] == "passed"
        assert (temp_work_dir / "hello.py").is_file()

        # The manifest is really on disk and hash-links to its spec.
        repo = default_repository()
        manifest = repo.load_manifest(verification["run_id"])
        assert manifest is not None
        assert manifest.verdict == "passed"
        spec = repo.load_spec(manifest.design_id, 1)
        assert "hello.py" in spec.contracts[0]

    async def test_broken_attempt_then_fix_chains_manifests(
            self, brain, temp_work_dir, evidence_root):
        # First reply is syntactically broken (execution fails), the
        # retry fixes it. Both attempts must leave chained manifests.
        brain.llm_provider = ScriptedProvider([
            "```python\ndef broken(:\n    pass\n```",
            "```python\nprint('fixed')\n```",
        ])
        result = await brain.handle_task(_task("affiche fixed"))
        assert result["success"] is True

        repo = default_repository()
        manifests = sorted(repo.iter_manifests(), key=lambda m: m.metadata.get("attempt", 0))
        assert len(manifests) == 2
        first, second = manifests
        assert first.status == "failed"
        assert second.status == "completed"
        assert second.parent_run_id == first.run_id
        assert first.metadata["attempt"] == 1
        assert second.metadata["attempt"] == 2

    async def test_run_file_records_evidence(
            self, brain, temp_work_dir, evidence_root):
        (temp_work_dir / "hello.py").write_text("print('from disk')")
        result = await brain.handle_task(_run_file_task("hello.py"))
        assert result["success"] is True
        verification = result["verification"]
        assert verification["verdict"] in ("passed", "inconclusive")
        stages = {s["name"]: s["status"] for s in verification["stages"]}
        assert stages["contracts"] == "passed"
        assert stages["run"] == "passed"


class ScriptedProvider:
    """Fake LLM: returns the scripted replies in order (complete() is what
    PythonBrain calls for code generation)."""

    def __init__(self, replies):
        self.replies = list(replies)

    async def complete(self, prompt=None, stream=False, **kwargs):
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0]

    async def chat_complete(self, messages=None, **kwargs):
        return await self.complete()


def _task(text):
    from bigbrain.bus.message import BusMessage, MessageType

    return BusMessage(
        type=MessageType.TASK,
        source="orchestrator",
        target="test_python_brain",
        payload={"type": "generate_and_execute", "user_request": text},
    )


def _run_file_task(filename):
    from bigbrain.bus.message import BusMessage, MessageType

    return BusMessage(
        type=MessageType.TASK,
        source="orchestrator",
        target="test_python_brain",
        payload={"type": "run_file", "file": filename},
    )
