"""Versioned run evidence and durable storage for BigBrain code runs.

Port of the fpga backend's evidence layer (``../fpga/backend/evidence.py``),
adapted to Python code generation. The agent's chat history is useful for
interaction, but it is not a source of truth for what a run did. This
module defines the small, versioned records that make a run auditable:

* :class:`DesignSpec` describes what was ASKED, independently of the code
  the LLM happened to produce (natural-language request + contracts).
* :class:`StageResult` records one deterministic verification stage
  (syntax, compile, run, tests, contracts) and its artifacts.
* :class:`RunManifest` records the exact inputs, tools, stages and
  verdict of one execution attempt, hash-linked to its spec.
* :class:`EvidenceRepository` persists manifests and content-addressed
  artifacts (sha256) with atomic writes; a run that reached a terminal
  status (completed / failed / cancelled) is IMMUTABLE — rewriting it
  with different content raises :class:`ImmutableRunError`.

Deliberate departures from the fpga original: no FPGA domain types, no
YAML support, and no derived human-facing report yet (phase 4 of the
harness plan will add it next to the UI surface).

JSON is the canonical wire/storage format.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "bigbrain-evidence/1.0"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

T = TypeVar("T", bound=BaseModel)


class EvidenceError(ValueError):
    """Base error for invalid evidence records or persistence operations."""


class ImmutableRunError(EvidenceError):
    """Raised when a persisted terminal run is changed."""


# ── canonical serialization & hashing ──────────────────────────────────────


def canonical_data(value: Any) -> Any:
    """JSON-safe canonical data (pydantic models → mode='json' dicts)."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def canonical_json(value: Any) -> str:
    """Deterministic JSON — same record, same bytes, same hash."""
    return json.dumps(canonical_data(value), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_record(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _parse_model(model_type: type[T], data: Mapping[str, Any]) -> T:
    if isinstance(data, model_type):
        return data
    return model_type.model_validate(dict(data))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class _Model(BaseModel):
    """Strict base for evidence records — unknown keys are errors."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ── records ────────────────────────────────────────────────────────────────


class DesignSpec(_Model):
    """What was asked of the agent — independent of the produced code.

    ``contracts`` are the checkable claims attached to the request, e.g.
    "the file hello.py exists in the working project". The deterministic
    stages of phase 2 verify contracts mechanically; the spec hash links
    every manifest back to the exact request it answers.
    """

    schema_version: str = SCHEMA_VERSION
    design_id: str
    revision: int = Field(default=1, ge=1)
    name: str
    user_request: str
    contracts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("design_id", "name", "user_request")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported evidence schema version: {value}")
        return value

    def content_sha256(self) -> str:
        """Semantic hash of the spec itself (not of a manifest)."""
        return sha256_record(self)


class ArtifactRef(_Model):
    """Content-addressed artifact: bytes stored once, referenced by digest."""

    sha256: str
    name: str
    media_type: str = "application/octet-stream"
    size_bytes: int = Field(ge=0)
    locator: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must be a lowercase 64-character digest")
        return value


class StageResult(_Model):
    """One deterministic verification stage and its outcome.

    ``inconclusive`` (tool unavailable, timeout before evidence) is a
    first-class status: the gate treats it like a failure for mandatory
    stages, never like a pass.
    """

    name: str
    status: str = "pending"  # pending|running|passed|failed|inconclusive|skipped|not_applicable
    mandatory: bool = True
    tool: str | None = None
    tool_version: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    artifact_hashes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        allowed = {"pending", "running", "passed", "failed",
                   "inconclusive", "skipped", "not_applicable"}
        if value not in allowed:
            raise ValueError(f"unknown stage status: {value}")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def valid_artifact_hash(cls, values: list[str]) -> list[str]:
        for value in values:
            if not _SHA256.fullmatch(value):
                raise ValueError("stage artifact references must be SHA-256 digests")
        return values

    @property
    def terminal(self) -> bool:
        return self.status in {"passed", "failed", "inconclusive",
                               "skipped", "not_applicable"}


class RunManifest(_Model):
    """The auditable record of one execution attempt.

    Terminal statuses (completed / failed / cancelled) are immutable once
    persisted: the repository refuses to rewrite them with different
    content. Stage artifact references must resolve to declared
    artifacts — a manifest cannot point at evidence it does not carry.
    """

    schema_version: str = SCHEMA_VERSION
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex}")
    design_id: str
    design_revision: int = Field(ge=1)
    spec_sha256: str
    parent_run_id: str | None = None
    status: str = "planned"  # planned|running|completed|failed|cancelled|inconclusive
    created_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None
    # What executed: python version, brain, provider/model, attempt index.
    toolchain: dict[str, str] = Field(default_factory=dict)
    stages: list[StageResult] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def supported_manifest_version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(f"unsupported evidence schema version: {value}")
        return value

    @field_validator("spec_sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("spec_sha256 must be a lowercase SHA-256 digest")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        allowed = {"planned", "running", "completed", "failed",
                   "cancelled", "inconclusive"}
        if value not in allowed:
            raise ValueError(f"unknown run status: {value}")
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> "RunManifest":
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("completed runs require completed_at")
        declared = {artifact.sha256 for artifact in self.artifacts}
        referenced = {digest for stage in self.stages
                      for digest in stage.artifact_hashes}
        missing = sorted(referenced - declared)
        if missing:
            raise ValueError(
                "manifest references artifacts not present in artifacts: "
                + ", ".join(missing))
        return self

    @property
    def verdict(self) -> str:
        """Derived, conservative: the worst mandatory outcome wins."""
        mandatory = [s for s in self.stages if s.mandatory]
        if not mandatory:
            return "inconclusive"
        if any(s.status == "failed" for s in mandatory):
            return "failed"
        if any(s.status in ("inconclusive", "pending", "running") for s in mandatory):
            return "inconclusive"
        return "passed"

    @property
    def terminal(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}


# ── repository ──────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2] / "data" / "evidence"


class EvidenceRepository:
    """Atomic storage for specs, manifests and content-addressed artifacts.

    Layout::

        <root>/specs/<design_id>/r<revision>.json
        <root>/runs/<run_id>.json
        <root>/artifacts/sha256/<aa>/<digest>   (deduplicated by content)

    Writes are atomic (temp file + fsync + rename). A manifest that
    reached a terminal status cannot be rewritten with different bytes.
    """

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).absolute()
        self.specs = self.root / "specs"
        self.runs = self.root / "runs"
        self.artifacts = self.root / "artifacts" / "sha256"

    # -- helpers ----------------------------------------------------------

    def _safe_component(self, value: str, label: str) -> str:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise EvidenceError(f"invalid {label}")
        return value

    def _atomic_bytes(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.",
                suffix=".tmp", delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def _save_json(self, path: Path, value: BaseModel, *, immutable: bool = False) -> str:
        content = canonical_json(value).encode("utf-8")
        if immutable and path.exists():
            old = path.read_bytes()
            if old != content:
                raise ImmutableRunError(f"completed run is immutable: {path.stem}")
            return sha256_bytes(content)
        self._atomic_bytes(path, content)
        return sha256_bytes(content)

    # -- specs -------------------------------------------------------------

    def save_spec(self, spec: DesignSpec) -> str:
        path = self.specs / self._safe_component(spec.design_id, "design_id") \
            / f"r{spec.revision}.json"
        if path.exists() and path.read_bytes() != canonical_json(spec).encode("utf-8"):
            raise ImmutableRunError(
                f"spec revision is immutable: {spec.design_id}/r{spec.revision}")
        return self._save_json(path, spec, immutable=True)

    def load_spec(self, design_id: str, revision: int) -> DesignSpec | None:
        path = self.specs / self._safe_component(design_id, "design_id") / f"r{revision}.json"
        if not path.exists():
            return None
        return _parse_model(DesignSpec, json.loads(path.read_text(encoding="utf-8")))

    def load_latest_spec(self, design_id: str) -> DesignSpec | None:
        """The highest saved revision of a design (None if never saved)."""
        folder = self.specs / self._safe_component(design_id, "design_id")
        if not folder.is_dir():
            return None
        revisions = sorted(
            (int(m.group(1)) for p in folder.glob("r*.json")
             if (m := re.fullmatch(r"r(\d+)\.json", p.name))),
        )
        if not revisions:
            return None
        return self.load_spec(design_id, revisions[-1])

    def approve_spec(self, design_id: str, *, by: str = "user",
                     plan_id: str | None = None,
                     decision: str = "approved") -> DesignSpec | None:
        """Stamp the user's approval on a design as a NEW revision.

        Revisions are immutable, so the approval is recorded as
        ``metadata["approval"]`` on a fresh revision — the original
        proposal is preserved and the trail stays auditable.
        """
        latest = self.load_latest_spec(design_id)
        if latest is None:
            return None
        approved = latest.model_copy(update={
            "revision": latest.revision + 1,
            "metadata": {
                **latest.metadata,
                "approval": {
                    "decision": decision,
                    "by": by,
                    "at": _now_iso(),
                    "plan_id": plan_id,
                },
            },
        })
        self.save_spec(approved)
        return approved

    # -- manifests ----------------------------------------------------------

    def save_manifest(self, manifest: RunManifest) -> str:
        path = self.runs / f"{self._safe_component(manifest.run_id, 'run_id')}.json"
        immutable = False
        if path.exists():
            existing = _parse_model(
                RunManifest, json.loads(path.read_text(encoding="utf-8")))
            immutable = existing.terminal
        return self._save_json(path, manifest, immutable=immutable)

    def load_manifest(self, run_id: str) -> RunManifest | None:
        path = self.runs / f"{self._safe_component(run_id, 'run_id')}.json"
        if not path.exists():
            return None
        return _parse_model(RunManifest, json.loads(path.read_text(encoding="utf-8")))

    def iter_manifests(self) -> Iterator[RunManifest]:
        if not self.runs.is_dir():
            return
        for path in sorted(self.runs.glob("run-*.json")):
            try:
                yield _parse_model(RunManifest, json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue

    # -- artifacts -----------------------------------------------------------

    def put_artifact(self, content: bytes, *, name: str,
                      media_type: str = "application/octet-stream",
                      metadata: Mapping[str, Any] | None = None) -> ArtifactRef:
        digest = sha256_bytes(content)
        path = self.artifacts / digest[:2] / digest
        if path.exists() and path.read_bytes() != content:
            raise EvidenceError("content-addressed artifact collision")
        if not path.exists():
            self._atomic_bytes(path, content)
        return ArtifactRef(
            sha256=digest,
            name=name,
            media_type=media_type,
            size_bytes=len(content),
            locator=str(path.relative_to(self.root)),
            metadata=dict(metadata or {}),
        )

    def get_artifact(self, digest: str) -> bytes | None:
        if not _SHA256.fullmatch(digest):
            raise EvidenceError("invalid artifact digest")
        path = self.artifacts / digest[:2] / digest
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None


def default_repository() -> EvidenceRepository:
    """The shared repository: ``data/evidence/`` (BIGBRAIN_EVIDENCE_ROOT to move)."""
    return EvidenceRepository(
        os.environ.get("BIGBRAIN_EVIDENCE_ROOT") or _REPO_ROOT
    )
