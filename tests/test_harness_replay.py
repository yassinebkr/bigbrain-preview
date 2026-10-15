"""Harness P3 — replay from manifests and the golden corpus.

See docs/HARNESS-DETERMINISTE.md.
"""

import pytest

from bigbrain.verification.evidence import EvidenceRepository, RunManifest
from bigbrain.verification.gate import RunGate
from bigbrain.verification.golden import GOLDEN_CASES, check_case, run_corpus
from bigbrain.verification.replay import ReplayError, replay_run


DETERMINISTIC = "print('Hello, World!')"
NON_DETERMINISTIC = "import time\nprint(time.time())"


@pytest.fixture
def repo(tmp_path):
    return EvidenceRepository(tmp_path / "evidence")


async def record_run(repo, code, execution=None):
    """Record a terminal run through the real gate and return its id."""
    gate = RunGate(repo)
    execution = execution or {
        "exit_code": 0, "stdout": "Hello, World!\n", "stderr": "",
    }
    manifest, _ = await gate.evaluate_attempt(
        user_request="crée un script hello.py",
        code=code,
        execution=execution,
        work_dir=repo.root,  # contracts: not_applicable (no file check wanted)
        requested_file=None,
    )
    return manifest.run_id


class TestReplay:
    async def test_deterministic_run_replays_identically(self, repo):
        run_id = await record_run(repo, DETERMINISTIC)
        report = await replay_run(run_id, repo)
        assert report["deterministic"] is True
        assert report["mismatches"] == []
        assert report["original_run_id"] == run_id

        # The replay is a chained, terminal manifest.
        replay = repo.load_manifest(report["replay_run_id"])
        assert replay.parent_run_id == run_id
        assert replay.metadata["replay_of"] == run_id
        assert replay.status == "completed"
        stages = {s.name: s.status for s in replay.stages}
        assert stages["replay_compare"] == "passed"

    async def test_time_based_code_is_flagged_non_deterministic(self, repo):
        run_id = await record_run(
            repo, NON_DETERMINISTIC,
            execution={"exit_code": 0, "stdout": "12345.678\n", "stderr": ""})
        report = await replay_run(run_id, repo)
        assert report["deterministic"] is False
        assert "stdout" in report["mismatches"]

        replay = repo.load_manifest(report["replay_run_id"])
        assert replay.status == "failed"
        assert {s.name: s.status for s in replay.stages}["replay_compare"] == "failed"

    async def test_unknown_run_rejected(self, repo):
        with pytest.raises(ReplayError):
            await replay_run("run-doesnotexist", repo)

    async def test_only_terminal_runs_replay(self, repo):
        manifest = RunManifest(
            design_id="task-x", design_revision=1,
            spec_sha256="0" * 64, status="running",
        )
        repo.save_manifest(manifest)
        with pytest.raises(ReplayError, match="terminal"):
            await replay_run(manifest.run_id, repo)

    async def test_replay_of_a_replay_chains_the_history(self, repo):
        run_id = await record_run(repo, DETERMINISTIC)
        first = await replay_run(run_id, repo)
        second = await replay_run(first["replay_run_id"], repo)
        assert second["deterministic"] is True
        chain = repo.load_manifest(second["replay_run_id"])
        assert chain.parent_run_id == first["replay_run_id"]
        assert chain.metadata["replay_of"] == first["replay_run_id"]


class TestGoldenCorpus:
    async def test_every_case_passes(self):
        summary = await run_corpus()
        assert summary["total"] == len(GOLDEN_CASES)
        assert summary["passed"] == summary["total"], summary["results"]

    async def test_checker_catches_a_regression(self):
        from bigbrain.verification.golden import GoldenCase

        bad = GoldenCase(
            case_id="broken",
            user_request="case with a wrong expectation",
            code="print('actual')",
            expected_stdout="expected\n",
        )
        result = await check_case(bad)
        assert result["passed"] is False

    async def test_stdin_reading_code_never_hangs(self):
        from bigbrain.verification.golden import GoldenCase

        reads_stdin = GoldenCase(
            case_id="stdin_eof",
            user_request="code that reads stdin must get EOF, not hang",
            code="try:\n    print(input())\nexcept EOFError:\n    print('eof')",
            expected_stdout="eof\n",
        )
        result = await check_case(reads_stdin, timeout=5.0)
        assert result["passed"] is True, result

    async def test_infinite_loop_times_out(self):
        from bigbrain.verification.golden import GoldenCase

        loop = GoldenCase(
            case_id="timeout",
            user_request="infinite loop must be killed by the timeout",
            code="while True:\n    pass",
            expected_stdout="never\n",
        )
        result = await check_case(loop, timeout=1.0)
        assert result["passed"] is False
        assert result["exit_code"] == -1
