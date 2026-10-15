"""Evidence core (harness P1) — versioned manifests, immutability,
content-addressed artifacts. See docs/HARNESS-DETERMINISTE.md."""

import json

import pytest

from bigbrain.verification.evidence import (
    DesignSpec,
    EvidenceError,
    EvidenceRepository,
    ImmutableRunError,
    RunManifest,
    StageResult,
    canonical_json,
    default_repository,
    sha256_bytes,
)


@pytest.fixture
def repo(tmp_path):
    return EvidenceRepository(tmp_path / "evidence")


def make_spec(**overrides) -> DesignSpec:
    base = dict(
        design_id="hello-script",
        name="Hello script",
        user_request="crée un script hello.py qui affiche Hello, World!",
        contracts=["file hello.py exists in the working project"],
    )
    base.update(overrides)
    return DesignSpec(**base)


def make_manifest(spec: DesignSpec, **overrides) -> RunManifest:
    base = dict(
        design_id=spec.design_id,
        design_revision=spec.revision,
        spec_sha256=spec.content_sha256(),
        toolchain={"python": "3.13", "brain": "python_brain_0"},
    )
    base.update(overrides)
    return RunManifest(**base)


class TestCanonicalJson:
    def test_same_record_same_bytes(self):
        a = make_spec()
        b = make_spec()
        assert canonical_json(a) == canonical_json(b)

    def test_key_order_is_sorted(self):
        text = canonical_json(make_spec())
        assert text.index('"design_id"') < text.index('"name"')


class TestDesignSpec:
    def test_content_hash_stable_and_changing(self):
        assert make_spec().content_sha256() == make_spec().content_sha256()
        other = make_spec(user_request="different request")
        assert other.content_sha256() != make_spec().content_sha256()

    def test_rejects_empty_fields(self):
        with pytest.raises(ValueError):
            DesignSpec(design_id="", name="x", user_request="y")
        with pytest.raises(ValueError):
            DesignSpec(design_id="a", name=" ", user_request="y")

    def test_rejects_unknown_schema_version(self):
        with pytest.raises(ValueError):
            make_spec(schema_version="bigbrain-evidence/0.9")

    def test_roundtrip_through_repository(self, repo):
        spec = make_spec()
        repo.save_spec(spec)
        loaded = repo.load_spec("hello-script", 1)
        assert loaded == spec

    def test_spec_revision_is_immutable(self, repo):
        spec = make_spec()
        repo.save_spec(spec)
        with pytest.raises(ImmutableRunError):
            repo.save_spec(make_spec(user_request="changed"))


class TestStageResult:
    def test_bad_status_rejected(self):
        with pytest.raises(ValueError):
            StageResult(name="syntax", status="green")

    def test_inconclusive_is_terminal(self):
        stage = StageResult(name="tests", status="inconclusive")
        assert stage.terminal is True


class TestRunManifest:
    def test_completed_requires_timestamp(self, repo):
        spec = make_spec()
        with pytest.raises(ValueError):
            make_manifest(spec, status="completed")

    def test_manifest_roundtrip(self, repo):
        spec = make_spec()
        repo.save_spec(spec)
        code_artifact = repo.put_artifact(
            b"print('Hello, World!')", name="hello.py", media_type="text/x-python")
        manifest = make_manifest(
            spec,
            status="failed",
            completed_at="2026-10-26T00:00:00Z",
            stages=[StageResult(
                name="syntax", status="passed", tool="ast.parse",
                artifact_hashes=[code_artifact.sha256],
                details={"exit_code": 0},
            )],
            artifacts=[code_artifact],
        )
        repo.save_manifest(manifest)

        loaded = repo.load_manifest(manifest.run_id)
        assert loaded == manifest
        assert loaded.verdict == "passed"  # stage itself passed; run failed for other reasons

    def test_stage_artifact_must_be_declared(self, repo):
        spec = make_spec()
        orphan = repo.put_artifact(b"not declared", name="orphan.txt")
        with pytest.raises(ValueError, match="not present in artifacts"):
            make_manifest(spec, stages=[StageResult(
                name="syntax", status="passed",
                artifact_hashes=[orphan.sha256],
            )])

    def test_verdict_conservative(self, repo):
        spec = make_spec()
        # Mandatory failure dominates a pass.
        m = make_manifest(spec, stages=[
            StageResult(name="syntax", status="passed"),
            StageResult(name="run", status="failed"),
        ])
        assert m.verdict == "failed"
        # Inconclusive mandatory stage is never a pass.
        m = make_manifest(spec, stages=[
            StageResult(name="syntax", status="passed"),
            StageResult(name="tests", status="inconclusive"),
        ])
        assert m.verdict == "inconclusive"
        # Non-mandatory stages don't block.
        m = make_manifest(spec, stages=[
            StageResult(name="syntax", status="passed"),
            StageResult(name="mypy", status="failed", mandatory=False),
        ])
        assert m.verdict == "passed"
        # No mandatory stages → inconclusive, never a free pass.
        assert make_manifest(spec).verdict == "inconclusive"

    def test_terminal_manifest_is_immutable(self, repo):
        spec = make_spec()
        manifest = make_manifest(spec, status="failed",
                                 completed_at="2026-10-26T00:00:00Z")
        repo.save_manifest(manifest)
        # Same bytes: idempotent save is allowed.
        repo.save_manifest(manifest)
        # Different content, SAME run_id: refused.
        changed = make_manifest(spec, run_id=manifest.run_id, status="failed",
                                completed_at="2026-10-26T00:00:00Z",
                                warnings=["different"])
        with pytest.raises(ImmutableRunError):
            repo.save_manifest(changed)

    def test_running_manifest_can_be_updated(self, repo):
        spec = make_spec()
        repo.save_spec(spec)
        manifest = make_manifest(spec, status="running")
        repo.save_manifest(manifest)
        # validate_assignment re-runs the model validator on mutation, so
        # update through a full re-validation (completed_at before status).
        updated = RunManifest.model_validate({
            **manifest.model_dump(mode="json"),
            "status": "completed",
            "completed_at": "2026-10-26T00:00:00Z",
        })
        repo.save_manifest(updated)
        loaded = repo.load_manifest(manifest.run_id)
        assert loaded.status == "completed"


class TestArtifacts:
    def test_content_addressed_roundtrip(self, repo):
        ref = repo.put_artifact(b"print('hi')", name="hi.py", media_type="text/x-python")
        assert repo.get_artifact(ref.sha256) == b"print('hi')"
        assert ref.size_bytes == len(b"print('hi')")

    def test_identical_content_deduplicates(self, repo):
        a = repo.put_artifact(b"same", name="a.txt")
        b = repo.put_artifact(b"same", name="b.txt")
        assert a.sha256 == b.sha256

    def test_digest_verifies_content(self, repo):
        ref = repo.put_artifact(b"payload", name="x.bin")
        assert sha256_bytes(b"payload") == ref.sha256

    def test_missing_artifact_returns_none(self, repo):
        assert repo.get_artifact("0" * 64) is None

    def test_invalid_digest_rejected(self, repo):
        with pytest.raises(EvidenceError):
            repo.get_artifact("not-a-digest")


class TestRepositoryLayout:
    def test_iter_manifests_skips_corrupt_files(self, repo, tmp_path):
        spec = make_spec()
        manifest = make_manifest(spec, status="running")
        repo.save_manifest(manifest)
        (repo.runs / "run-corrupt.json").write_text("{not json", encoding="utf-8")
        ids = [m.run_id for m in repo.iter_manifests()]
        assert manifest.run_id in ids
        assert "run-corrupt" not in "".join(ids)

    def test_safe_component_rejects_traversal(self, repo):
        with pytest.raises(EvidenceError):
            repo._safe_component("../escape", "run_id")

    def test_json_is_the_storage_format(self, repo):
        spec = make_spec()
        manifest = make_manifest(spec, status="running")
        repo.save_manifest(manifest)
        raw = json.loads((repo.runs / f"{manifest.run_id}.json").read_text(encoding="utf-8"))
        assert raw["run_id"] == manifest.run_id
        assert raw["schema_version"] == "bigbrain-evidence/1.0"


def test_default_repository_points_at_data_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    repo = default_repository()
    assert repo.root == (tmp_path / "ev").absolute()
