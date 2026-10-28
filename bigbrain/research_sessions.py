"""Conversation-scoped research checkpoints, leases and explicit continuations.

Snapshots retain observations and attempt history under the evidence root.
Advisory leases prevent concurrent continuations and release on process exit.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID


class ResearchSessions:
    def __init__(self, workspace, session_id):
        from .research_acquisition import repository
        if not workspace or not session_id:
            raise ValueError("Research persistence requires a workspace and conversation")
        self.owner = {"workspace": workspace, "session_id": session_id}
        scope = hashlib.sha256(json.dumps(self.owner, sort_keys=True).encode()).hexdigest()
        self.root = repository().root / "research" / scope

    def path(self, research_id):
        if str(UUID(research_id)) != research_id:
            raise ValueError("Invalid research identity")
        return self.root / f"{research_id}.json"

    @contextmanager
    def lease(self, research_id):
        path = self.path(research_id).with_suffix(".lock")
        self.root.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("This research already has an active attempt") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def save(self, runtime):
        """Atomically publish a checkpoint before sending its UI snapshot."""
        path = self.path(runtime.research_id)
        self.root.mkdir(parents=True, exist_ok=True)
        frame = {"version": 1, "owner": self.owner, "revision": runtime.revision,
                 "updated_at": datetime.now(timezone.utc).isoformat(),
                 "state": runtime.state.model_dump(mode="json")}
        data = json.dumps(frame, ensure_ascii=False).encode()
        if len(data) > 16_000_000:
            raise ValueError("Research checkpoint exceeds persistence limit")
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix=".checkpoint-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, research_id):
        path = self.path(research_id)
        if path.stat().st_size > 16_000_000:
            raise ValueError("Research checkpoint exceeds persistence limit")
        frame = json.loads(path.read_text())
        if frame.get("version") != 1 or frame.get("owner") != self.owner:
            raise ValueError("Research checkpoint ownership/version mismatch")
        from .research import ResearchState
        state = ResearchState.model_validate(frame["state"])
        if state.research_id != research_id:
            raise ValueError("Research checkpoint identity mismatch")
        return state, frame["revision"]

    def summaries(self, limit=5):
        """Small front-brain index; no pages or sub-brain transcripts injected."""
        if not self.root.exists():
            return []
        output = []
        for path in sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                state, _ = self.load(path.stem)
                output.append({"research_id": path.stem, "objective": state.objective[:800],
                               "objective_truncated": len(state.objective) > 800,
                               "status": state.status, "answer_status": state.answer_status,
                               "reason": state.reason[:300] if state.reason else None,
                               "coverage": [{"question_id": q["question_id"], "status": q["status"],
                                   "missing_evidence": [str(gap)[:160] for gap in q["missing_evidence"][:2]]}
                                   for q in state.question_coverage]})
            except (ValueError, OSError, KeyError):
                continue
        return output


def prepare_continuation(state, *, max_age_seconds=None):
    """Retain verified archived captures and enforce explicit freshness bounds."""
    now = datetime.now(timezone.utc)
    stale = set()
    from .research_acquisition import repository
    for source in state.sources:
        if source.status != "read":
            continue
        stamp = source.acquisition.get("captured_at") or source.consulted_at
        try:
            age = (now - datetime.fromisoformat(stamp)).total_seconds()
        except (TypeError, ValueError):
            age = float("inf")
        missing_artifact = False
        for key in ("raw_artifact", "rendered_artifact", "blocks_artifact"):
            ref = source.acquisition.get(key)
            if ref:
                body = repository().get_artifact(ref["sha256"])
                if body is None or hashlib.sha256(body).hexdigest() != ref["sha256"]:
                    missing_artifact = True
        capture = source.acquisition.get('rendered_artifact') or source.acquisition.get('raw_artifact')
        archived = bool(capture and source.acquisition.get('blocks_artifact')
                        and source.content_sha256 == capture['sha256'])
        age_limit = max_age_seconds if max_age_seconds is not None else (None if archived else 300)
        if age < 0 or (age_limit is not None and age > age_limit) or missing_artifact:
            stale.add(source.id)
            source.status, source.error = "discovered", "Retained snapshot expired or unavailable; read again before citing"
    if stale:
        state.passages = [p for p in state.passages if p.source_id not in stale]
        state.claims = []
        state.assessments = []
        state.question_coverage, state.answer_status = [], "unassessed"
    return stale
