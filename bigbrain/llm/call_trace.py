"""Correlated inference lifecycle records without prompts or response bodies."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import sys
import time
from uuid import uuid4

from .conversation import current_conversation

_active_trace = ContextVar("inference_trace", default=None)


def trace_stage(stage, **metadata):
    """Record transport milestones using a deliberately narrow metadata set."""
    trace = _active_trace.get()
    if trace is not None:
        trace.write(stage, **{k: v for k, v in metadata.items() if k in {
            "status_code", "request_id", "native_thread_id", "native_turn_id",
            "request_bytes", "response_bytes", "automatic_retries", "attempt",
            "remaining_tokens", "decision_reserve", "review_reserve", "closing",
            "message_phase", "message_id"}})


class CallTrace:
    def __init__(self, provider, phase, correlation, deadline_seconds, records):
        from ..verification.evidence import default_repository
        self.started = time.monotonic()
        self.deadline = deadline_seconds
        self.records = records
        self.call_id = uuid4().hex
        self.path = default_repository().root / "inference" / (self.call_id + ".jsonl")
        scope = current_conversation.get()
        entry = getattr(provider, "entry", None)
        self.metadata = {
            "schema_version": "inference-trace/1.0", "call_id": self.call_id,
            "session_id": scope[0] if scope else None, "role": scope[1] if scope else None,
            "phase": phase, "provider": type(provider).__name__,
            "registry_key": getattr(provider, "registry_key", None),
            "model": getattr(provider, "default_model", None) or getattr(entry, "model_id", None),
            "effort": getattr(provider, "reasoning_effort", None) or getattr(entry, "reasoning_effort_default", None),
            "deadline_seconds": deadline_seconds, "attempt": 1,
            **{k: v for k, v in correlation.items() if k in {
                "session_id", "turn_id", "task_id", "subtask_id", "research_id"}},
        }
        self.metadata = {k: (v[:256] if isinstance(v, str) else v if type(v) in
                            (int, float, bool, type(None)) else None) for k, v in self.metadata.items()}

    def write(self, event, **fields):
        record = {**self.metadata, "event": event,
                  "timestamp": datetime.now(timezone.utc).isoformat(),
                  "elapsed_ms": round((time.monotonic() - self.started) * 1000, 2), **fields}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Disk errors must be visible but cannot replace the model outcome.
            print("Inference trace write failed", file=sys.stderr)


@contextmanager
def trace_call(provider, phase, *, correlation=None, deadline_seconds=None, records=None):
    """Record exactly one local terminal outcome, including task cancellation."""
    trace = CallTrace(provider, phase, correlation or {}, deadline_seconds, records if records is not None else [])
    token = _active_trace.set(trace)
    trace.write("call.started")
    outcome, chain = "completed", []
    try:
        yield trace
    except BaseException as exc:
        elapsed = time.monotonic() - trace.started
        outcome = ("deadline" if isinstance(exc, TimeoutError) or (
            isinstance(exc, asyncio.CancelledError) and deadline_seconds is not None and elapsed >= deadline_seconds)
            else "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed")
        seen = set()
        error = exc
        while error is not None and id(error) not in seen and len(chain) < 6:
            seen.add(id(error))
            chain.append(type(error).__name__)
            error = error.__cause__ or error.__context__
        raise
    finally:
        usage = [{k: getattr(r, k) for k in (
            "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "total_tokens", "cost_usd")}
            for r in trace.records]
        trace.write("call.finished", outcome=outcome, exception_types=chain,
                    usage=usage, usage_known=bool(usage) and any(r["total_tokens"] > 0 for r in usage))
        _active_trace.reset(token)
