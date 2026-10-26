"""Per-role model lineup for the BigBrain UI.

BigBrain routes models per role (front / planner / code / subagent), not one
global model — the UI dropdown shows the lineup. Choices are persisted to
``data/model_roles.json`` (survives restarts) and mirrored into the
``BIGBRAIN_*_MODEL`` env vars so providers built after the change pick them
up without a restart for new instances.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from ..llm.model_registry import get_model, role_default_key

logger = logging.getLogger(__name__)

ROLES = ("front", "planner", "code", "web", "research", "subagent")

_ENV_VAR_BY_ROLE = {
    "front": "BIGBRAIN_FRONT_MODEL",
    "planner": "BIGBRAIN_PLANNER_MODEL",
    "code": "BIGBRAIN_CODE_MODEL",
    "web": "BIGBRAIN_WEB_MODEL",
    "subagent": "BIGBRAIN_SUBAGENT_MODEL",
    "research": "BIGBRAIN_RESEARCH_MODEL",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLES_FILE = _REPO_ROOT / "data" / "model_roles.json"


def _persisted() -> Dict[str, str]:
    try:
        data = json.loads(_ROLES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k in ROLES and isinstance(v, str)}
    except (OSError, ValueError):
        pass
    return {}


def _persist(mapping: Dict[str, str]) -> None:
    _ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _ROLES_FILE.with_name(".model_roles.json.tmp")
    tmp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    os.replace(tmp, _ROLES_FILE)


def current_lineup() -> Dict[str, Any]:
    """Roles → current registry key, model id and display name."""
    persisted = _persisted()
    lineup: Dict[str, Any] = {}
    for role in ROLES:
        key = persisted.get(role) or role_default_key(role)
        try:
            entry = get_model(key)
            model_id, display = entry.model_id, entry.display_name
        except KeyError:
            model_id, display = None, key
        lineup[role] = {
            "key": key,
            "model_id": model_id,
            "display_name": display,
            "reasoning_effort": entry.reasoning_effort_default if model_id else None,
        }
    return lineup


def configured_key(role: str) -> str | None:
    """Explicit registry assignment; absent roles keep legacy provider selection."""
    return _persisted().get(role) or os.environ.get(f"BIGBRAIN_{role.upper()}_MODEL_KEY") or None


def set_role(role: str, registry_key: str) -> Dict[str, Any]:
    """Assign a registry key to a role; persists and mirrors into env."""
    if role not in ROLES:
        raise ValueError(f"unknown role '{role}' (known: {list(ROLES)})")
    entry = get_model(registry_key)  # KeyError on unknown key
    persisted = _persisted()
    persisted[role] = registry_key
    _persist(persisted)
    # Mirror into env so providers/config built from here on pick it up.
    os.environ[_ENV_VAR_BY_ROLE[role]] = entry.model_id
    logger.info("model role '%s' set to '%s' (%s)", role, registry_key, entry.model_id)
    return {"ok": True, "role": role, "key": registry_key, "model_id": entry.model_id}
