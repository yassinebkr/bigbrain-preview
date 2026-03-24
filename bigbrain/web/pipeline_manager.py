"""
Server-side Pipeline Manager.

Manages data pipeline lifecycle on the server side.
Validates pipeline definitions, enforces constraints,
and provides an API for the WebAdapter to create/destroy pipelines.

Constraints (from architecture):
  - Max 6 concurrent pipelines per workspace
  - Min 5s poll interval for HTTP sources
  - URL validation (only http/https/ws/wss)
  - No eval, no arbitrary code in transforms
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Allowed URL schemes for pipeline sources
ALLOWED_SCHEMES = {"http", "https", "ws", "wss"}

# Minimum poll interval (seconds) — architecture constraint
MIN_POLL_INTERVAL = 5.0

# Maximum concurrent pipelines per workspace
MAX_PIPELINES_PER_WORKSPACE = 6


class PipelineDefinition:
    """Validated pipeline definition."""

    def __init__(
        self,
        pipeline_id: str,
        source_type: str,
        source_config: Dict[str, Any],
        transform: Optional[Dict[str, str]] = None,
        title: str = "",
        workspace: str = "default",
    ):
        self.id = pipeline_id
        self.source_type = source_type
        self.source_config = source_config
        self.transform = transform or {}
        self.title = title or pipeline_id
        self.workspace = workspace
        self.created_at = time.time()


class ServerPipelineManager:
    """
    Server-side pipeline manager.

    Validates and tracks pipeline definitions.
    The actual data fetching happens client-side (in the browser)
    for HTTP and WebSocket sources. Bus pipelines are handled
    by the WebSocket bridge automatically.

    This manager is primarily for:
    1. Validation before allowing pipeline creation
    2. Lifecycle tracking (what's active, workspace cleanup)
    3. Constraint enforcement (max count, URL safety)
    """

    def __init__(self) -> None:
        self._pipelines: Dict[str, PipelineDefinition] = {}
        self._workspace_counts: Dict[str, int] = {}

    def validate_and_register(
        self,
        pipeline_id: str,
        definition: Dict[str, Any],
        workspace: str = "default",
    ) -> Optional[PipelineDefinition]:
        """
        Validate a pipeline definition and register it.

        Returns PipelineDefinition on success, None on validation failure.

        Args:
            pipeline_id: Unique identifier
            definition: Raw definition dict from agent
            workspace: Workspace this pipeline belongs to

        Returns:
            PipelineDefinition or None
        """
        # Check max pipelines per workspace
        ws_count = self._workspace_counts.get(workspace, 0)
        if ws_count >= MAX_PIPELINES_PER_WORKSPACE:
            logger.warning(
                "Pipeline rejected: workspace '%s' already has %d pipelines (max %d)",
                workspace,
                ws_count,
                MAX_PIPELINES_PER_WORKSPACE,
            )
            return None

        # Check duplicate ID
        if pipeline_id in self._pipelines:
            logger.warning("Pipeline rejected: ID '%s' already exists", pipeline_id)
            return None

        # Extract and validate source
        source = definition.get("source", {})
        source_type = source.get("type")

        if source_type not in ("bus", "http-poll", "websocket"):
            logger.warning(
                "Pipeline rejected: invalid source type '%s'", source_type
            )
            return None

        # URL validation for http/ws sources
        if source_type in ("http-poll", "websocket"):
            url = source.get("url", "")
            if not self._validate_url(url):
                logger.warning(
                    "Pipeline rejected: invalid URL '%s'", url
                )
                return None

        # Poll interval validation
        if source_type == "http-poll":
            interval = source.get("interval", 30000)
            if isinstance(interval, (int, float)):
                interval_sec = interval / 1000 if interval > 100 else interval
                if interval_sec < MIN_POLL_INTERVAL:
                    logger.warning(
                        "Pipeline adjusted: poll interval %ss → %ss (minimum)",
                        interval_sec,
                        MIN_POLL_INTERVAL,
                    )
                    source["interval"] = int(MIN_POLL_INTERVAL * 1000)

        # Validate transform (no code, only field mappings)
        transform = definition.get("transform", {})
        fields = transform.get("fields", {})
        if not self._validate_transform(fields):
            logger.warning("Pipeline rejected: invalid transform")
            return None

        # All checks passed — register
        pipeline = PipelineDefinition(
            pipeline_id=pipeline_id,
            source_type=source_type,
            source_config=source,
            transform=fields,
            title=definition.get("title", pipeline_id),
            workspace=workspace,
        )

        self._pipelines[pipeline_id] = pipeline
        self._workspace_counts[workspace] = ws_count + 1

        logger.info(
            "Pipeline registered: %s (type=%s, workspace=%s)",
            pipeline_id,
            source_type,
            workspace,
        )
        return pipeline

    def unregister(self, pipeline_id: str) -> bool:
        """
        Remove a pipeline registration.

        Returns True if found and removed.
        """
        pipeline = self._pipelines.pop(pipeline_id, None)
        if pipeline:
            ws = pipeline.workspace
            self._workspace_counts[ws] = max(
                0, self._workspace_counts.get(ws, 1) - 1
            )
            logger.info("Pipeline unregistered: %s", pipeline_id)
            return True
        return False

    def cleanup_workspace(self, workspace: str) -> List[str]:
        """
        Remove all pipelines for a workspace.
        Returns list of removed pipeline IDs.
        """
        removed = []
        for pid, pipeline in list(self._pipelines.items()):
            if pipeline.workspace == workspace:
                del self._pipelines[pid]
                removed.append(pid)

        self._workspace_counts[workspace] = 0
        if removed:
            logger.info(
                "Cleaned up %d pipelines from workspace '%s'",
                len(removed),
                workspace,
            )
        return removed

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineDefinition]:
        """Get a pipeline definition by ID."""
        return self._pipelines.get(pipeline_id)

    def list_pipelines(
        self, workspace: str = None
    ) -> List[PipelineDefinition]:
        """List active pipelines, optionally filtered by workspace."""
        if workspace:
            return [
                p
                for p in self._pipelines.values()
                if p.workspace == workspace
            ]
        return list(self._pipelines.values())

    @property
    def total_count(self) -> int:
        """Total number of registered pipelines."""
        return len(self._pipelines)

    # ================================================================
    # VALIDATION HELPERS
    # ================================================================

    @staticmethod
    def _validate_url(url: str) -> bool:
        """Validate a URL for pipeline use."""
        if not url:
            return False

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        if parsed.scheme not in ALLOWED_SCHEMES:
            return False

        if not parsed.netloc:
            return False

        # Block localhost/private IPs in production?
        # For now, allow all — this is a preview.

        return True

    @staticmethod
    def _validate_transform(fields: Dict[str, str]) -> bool:
        """
        Validate transform field mappings.

        Only dot-notation paths are allowed (e.g., 'data.temp.current').
        No code, no eval, no function calls.
        """
        if not isinstance(fields, dict):
            return False

        for key, path in fields.items():
            if not isinstance(key, str) or not isinstance(path, str):
                return False

            # Only allow alphanumeric, dots, underscores, and array indices
            for char in path:
                if char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._":
                    return False

        return True
