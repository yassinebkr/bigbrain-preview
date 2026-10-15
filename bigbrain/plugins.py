"""Brain plugins — step 1 of docs/BRAIN-PLUGINS.md.

A plugin is a brain declared through a manifest. Step 1 ships the two
built-in brains (python, researcher) as manifest-backed plugins with real
enable/disable; premium/paid plugins and the remote registry come later.
Enabled state persists to ``data/plugins.json`` and is applied by the
system hook (PLUGINS_CHANGE_HOOK): the researcher brain registers/
unregisters live; the python pool applies at restart (pool sizing is a
startup decision).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGINS_FILE = _REPO_ROOT / "data" / "plugins.json"


@dataclass(frozen=True)
class PluginManifest:
    """Declarative brain plugin (see docs/BRAIN-PLUGINS.md)."""

    id: str
    name: str
    version: str
    description: str
    category: str
    capabilities: List[str] = field(default_factory=list)
    price: str = "free"  # free | one_time | subscription


BUILTIN_PLUGINS: List[PluginManifest] = [
    PluginManifest(
        id="python-brain",
        name="Python Brain",
        version="0.1.0",
        description="Generates and executes Python code, scripts, "
                    "simulations and multi-file projects in the workspace.",
        category="code",
        capabilities=["code_exec", "file_write", "workspace.write"],
    ),
    PluginManifest(
        id="researcher",
        name="Researcher",
        version="0.1.0",
        description="Web research via Brave Search with source "
                    "triangulation and LLM summarization.",
        category="research",
        capabilities=["web_search"],
    ),
]


def _enabled_ids() -> set:
    """Persisted enabled plugin ids (all built-ins enabled by default)."""
    try:
        data = json.loads(_PLUGINS_FILE.read_text(encoding="utf-8"))
        enabled = data.get("enabled")
        if isinstance(enabled, list):
            valid = {p.id for p in BUILTIN_PLUGINS}
            return set(enabled) & valid
    except (OSError, ValueError):
        pass
    return {p.id for p in BUILTIN_PLUGINS}


def _persist(enabled: set) -> None:
    _PLUGINS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PLUGINS_FILE.write_text(
        json.dumps({"enabled": sorted(enabled)}, indent=2), encoding="utf-8"
    )


def list_plugins() -> Dict[str, Any]:
    """Catalog with live enabled state (no secrets)."""
    enabled = _enabled_ids()
    return {
        "plugins": [
            {
                "id": p.id,
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "category": p.category,
                "capabilities": list(p.capabilities),
                "price": p.price,
                "enabled": p.id in enabled,
            }
            for p in BUILTIN_PLUGINS
        ]
    }


def set_enabled(plugin_id: str, enabled: bool) -> Dict[str, Any]:
    """Enable/disable a plugin; persists and returns the apply note.

    The system hook (PLUGINS_CHANGE_HOOK) applies the change at runtime
    where feasible; the python pool applies at restart.
    """
    manifest = next((p for p in BUILTIN_PLUGINS if p.id == plugin_id), None)
    if manifest is None:
        raise ValueError(f"unknown plugin '{plugin_id}'")
    current = _enabled_ids()
    if enabled:
        current.add(plugin_id)
    else:
        if plugin_id == "python-brain":
            raise ValueError(
                "the python brain cannot be disabled (core plugin)"
            )
        current.discard(plugin_id)
    _persist(current)
    applies = "live" if plugin_id == "researcher" else "restart"
    logger.info("plugin '%s' %s (applies: %s)", plugin_id,
                "enabled" if enabled else "disabled", applies)
    return {"ok": True, "id": plugin_id, "enabled": enabled, "applies": applies}
