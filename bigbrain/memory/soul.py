"""The soul — consolidated long-term identity memory.

openclaw's "soul" was extremely effective but expensive because it ran
on every turn. BigBrain's soul is consolidated in BATCH: every N user
turns (env ``BIGBRAIN_SOUL_TURNS``, default 50) the recent transcript is
distilled ONCE by the LLM into a compact summary (3-6 lines) stored at
``memory/soul.json`` (env ``BIGBRAIN_SOUL_FILE``). Each turn then just
injects those few lines into the system prompt — the per-turn cost is a
handful of tokens, and the consolidation itself costs one LLM call per
N turns. Kill switch: ``BIGBRAIN_SOUL=0``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

SOUL_PROMPT = """You maintain the long-term memory ("soul") of a personal AI assistant.
You receive the previous soul summary and a transcript excerpt of recent
conversations with the user. Produce the UPDATED soul: 3 to 6 short lines
that capture who the user is, what they are working on, their preferences,
habits and lessons learned.

Rules:
- Factual only: never invent anything not visible in the inputs
- Same language as the user's messages
- Keep what still matters from the previous soul, drop what is stale
- Respond with ONLY the soul summary, no preamble, no markdown
"""


class SoulStore:
    """File-backed soul (atomic writes; runs offline of ChromaDB)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.environ.get("BIGBRAIN_SOUL_FILE",
                                                "memory/soul.json"))
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"summary": "", "updated_at": 0.0}

    @property
    def summary(self) -> str:
        return str(self.data.get("summary") or "")

    @property
    def updated_at(self) -> float:
        return float(self.data.get("updated_at") or 0.0)

    def save(self, summary: str) -> None:
        # Cap the soul so the per-turn injection stays tiny.
        lines = [line for line in summary.strip().splitlines() if line.strip()]
        summary = "\n".join(lines[:6])[:900]
        self.data = {"summary": summary, "updated_at": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)


def collect_recent_transcript(since: float,
                              limit: int = 100) -> List[Tuple[str, str, float]]:
    """(role, text, timestamp) of every persisted session message newer
    than ``since``, chronological, capped to the most recent ``limit``."""
    from ..web.sessions import SessionStore

    store = SessionStore()
    collected: List[Tuple[str, str, float]] = []
    for session in store.list():
        data = store.get(session["id"]) or {}
        for message in data.get("messages") or []:
            ts = float(message.get("timestamp") or 0)
            if ts > since:
                collected.append((str(message.get("role") or "user"),
                                  str(message.get("text") or ""), ts))
    collected.sort(key=lambda item: item[2])
    return collected[-limit:]


def soul_enabled() -> bool:
    return os.environ.get("BIGBRAIN_SOUL", "1") != "0"


def soul_turn_interval() -> int:
    try:
        return max(1, int(os.environ.get("BIGBRAIN_SOUL_TURNS", "50")))
    except ValueError:
        return 50
