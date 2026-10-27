"""Immutable evidence snapshots shared by research drafting and control.

Canonical serialization retains exact observations and selection limitations.
The digest identifies the complete packet supplied to each inference role.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def canonical_bytes(value):
    """Serialize evidence deterministically across checkpoint reloads."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class EvidenceDossier:
    """Store an immutable serialized revision with a verified content digest."""

    revision: int
    payload: bytes
    sha256: str
    schema_version: str = "1.0"

    @classmethod
    def freeze(cls, state, *, revision=1, byte_limit=24000):
        """Freeze original observations and their bounded inspection ledger."""
        from .research_context import InspectionBudgetExceeded, review_view

        if type(revision) is not int or revision < 1:
            raise ValueError("Dossier revision must be positive")
        candidate = state.model_copy(deep=True)
        # Evidence selection precedes drafting; a draft cannot choose which
        # original observations the independent controller receives.
        candidate.claims = []
        selection_limit = byte_limit
        for _ in range(4):
            packet, extras = review_view(candidate, byte_limit=selection_limit)
            packet.pop("claims", None)
            packet["original_request"] = state.original_request or state.objective
            captures = {s.id: s.content_sha256 for s in state.sources if s.status == "read"}
            for context in packet["passage_contexts"]:
                if (not context["observation_sha256"]
                        or captures.get(context["source_id"]) != context["observation_sha256"]):
                    raise ValueError("Frozen dossier passage requires its current source capture")
            selected = {p["id"] for p in packet["passages"]}
            # Capture identities are shared through passage_contexts. Each
            # passage retains its original block range and original locator.
            packet["anchors"] = {p.id: {"block": p.block_id,
                                       "start": p.block_start, "end": p.block_end,
                                       "locator": p.locator}
                                 for p in [*state.passages, *extras] if p.id in selected}
            packet["access_failures"] = [{"source_id": s.id, "url": s.url, "error": s.error,
                                         "acquisition_status": s.acquisition.get("status")}
                                        for s in state.sources if s.error or s.status == "inaccessible"]
            packet["schema_version"] = "1.0"
            packet["revision"] = revision
            payload = canonical_bytes(packet)
            if len(payload) <= byte_limit:
                return cls(revision, payload, hashlib.sha256(payload).hexdigest()), extras
            # Reserve the measured anchor/ledger overhead before selecting
            # optional sections again. review_view preserves required sections
            # atomically and raises if those sections alone cannot fit.
            selection_limit -= len(payload) - byte_limit + 64
            if selection_limit <= 0:
                break
        raise InspectionBudgetExceeded("Frozen dossier metadata cannot fit its input envelope")

    @classmethod
    def freeze_bounded(cls, state, *, revision=1, minimum=6000, maximum=24000):
        """Choose the smallest admitted envelope retaining required evidence."""
        from .research_context import InspectionBudgetExceeded
        if minimum <= 0 or maximum < minimum:
            raise ValueError('Invalid dossier envelope range')
        for size in [*range(minimum, maximum, 2000), maximum]:
            try:
                return cls.freeze(state, revision=revision, byte_limit=size)
            except InspectionBudgetExceeded:
                if size == maximum:
                    raise

    def view(self):
        """Return an independent decoded view after verifying stored bytes."""
        if hashlib.sha256(self.payload).hexdigest() != self.sha256:
            raise ValueError("Evidence dossier digest mismatch")
        return json.loads(self.payload)

    def checkpoint(self):
        """Produce a JSON checkpoint suitable for the research journal."""
        return {"schema_version": self.schema_version, "revision": self.revision,
                "sha256": self.sha256, "packet": self.view()}

    @classmethod
    def restore(cls, record):
        """Reject modified evidence when restoring a persisted revision."""
        if record["schema_version"] != "1.0":
            raise ValueError("Unsupported evidence dossier version")
        if type(record["revision"]) is not int or record["revision"] < 1:
            raise ValueError("Evidence dossier revision must be positive")
        instance = cls(record["revision"], canonical_bytes(record["packet"]), record["sha256"])
        instance.view()
        if instance.view()["revision"] != instance.revision:
            raise ValueError("Evidence dossier revision mismatch")
        return instance
