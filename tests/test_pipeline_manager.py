"""Tests for ServerPipelineManager — validation, constraints, lifecycle."""

import pytest

from bigbrain.web.pipeline_manager import (
    ServerPipelineManager,
    PipelineDefinition,
    MAX_PIPELINES_PER_WORKSPACE,
    MIN_POLL_INTERVAL,
)


# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
def manager():
    return ServerPipelineManager()


def make_bus_def(title="Test"):
    """Helper: create a valid bus pipeline definition."""
    return {
        "source": {"type": "bus", "filter": {"type": "event"}},
        "transform": {"fields": {"status": "payload.status"}},
        "title": title,
    }


def make_http_def(url="https://api.example.com/data", interval=10000, title="HTTP"):
    """Helper: create a valid HTTP pipeline definition."""
    return {
        "source": {"type": "http-poll", "url": url, "interval": interval},
        "transform": {"fields": {"temp": "data.temp"}},
        "title": title,
    }


def make_ws_def(url="wss://stream.example.com/live", title="WS"):
    """Helper: create a valid WebSocket pipeline definition."""
    return {
        "source": {"type": "websocket", "url": url},
        "transform": {"fields": {"price": "data.price"}},
        "title": title,
    }


# ================================================================
# BASIC REGISTRATION
# ================================================================


class TestRegistration:
    def test_register_bus_pipeline(self, manager):
        result = manager.validate_and_register("p1", make_bus_def())
        assert result is not None
        assert isinstance(result, PipelineDefinition)
        assert result.id == "p1"
        assert result.source_type == "bus"

    def test_register_http_pipeline(self, manager):
        result = manager.validate_and_register("p1", make_http_def())
        assert result is not None
        assert result.source_type == "http-poll"

    def test_register_ws_pipeline(self, manager):
        result = manager.validate_and_register("p1", make_ws_def())
        assert result is not None
        assert result.source_type == "websocket"

    def test_total_count(self, manager):
        assert manager.total_count == 0
        manager.validate_and_register("p1", make_bus_def())
        assert manager.total_count == 1
        manager.validate_and_register("p2", make_http_def())
        assert manager.total_count == 2

    def test_get_pipeline(self, manager):
        manager.validate_and_register("p1", make_bus_def(), workspace="demo")
        p = manager.get_pipeline("p1")
        assert p is not None
        assert p.workspace == "demo"

    def test_get_nonexistent(self, manager):
        assert manager.get_pipeline("nope") is None

    def test_list_all(self, manager):
        manager.validate_and_register("p1", make_bus_def())
        manager.validate_and_register("p2", make_http_def())
        assert len(manager.list_pipelines()) == 2

    def test_list_by_workspace(self, manager):
        manager.validate_and_register("p1", make_bus_def(), workspace="a")
        manager.validate_and_register("p2", make_http_def(), workspace="b")
        manager.validate_and_register("p3", make_ws_def(), workspace="a")
        assert len(manager.list_pipelines(workspace="a")) == 2
        assert len(manager.list_pipelines(workspace="b")) == 1


# ================================================================
# VALIDATION — rejection cases
# ================================================================


class TestValidation:
    def test_reject_invalid_source_type(self, manager):
        defn = {"source": {"type": "ftp", "url": "ftp://evil.com"}}
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_missing_source_type(self, manager):
        defn = {"source": {}}
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_duplicate_id(self, manager):
        manager.validate_and_register("p1", make_bus_def())
        result = manager.validate_and_register("p1", make_bus_def())
        assert result is None
        assert manager.total_count == 1

    def test_reject_invalid_url_scheme(self, manager):
        defn = make_http_def(url="ftp://evil.com/data")
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_javascript_url(self, manager):
        defn = make_http_def(url="javascript:alert(1)")
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_empty_url(self, manager):
        defn = make_http_def(url="")
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_no_netloc(self, manager):
        defn = make_http_def(url="http://")
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_allow_https(self, manager):
        defn = make_http_def(url="https://api.example.com/v1")
        result = manager.validate_and_register("p1", defn)
        assert result is not None

    def test_allow_wss(self, manager):
        defn = make_ws_def(url="wss://stream.example.com/live")
        result = manager.validate_and_register("p1", defn)
        assert result is not None

    def test_reject_transform_with_special_chars(self, manager):
        defn = {
            "source": {"type": "bus"},
            "transform": {"fields": {"x": "data.$(evil)"}},
        }
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_reject_transform_with_code(self, manager):
        defn = {
            "source": {"type": "bus"},
            "transform": {"fields": {"x": "eval('malicious')"}},
        }
        result = manager.validate_and_register("p1", defn)
        assert result is None

    def test_allow_valid_transform(self, manager):
        defn = {
            "source": {"type": "bus"},
            "transform": {"fields": {
                "temp": "data.weather.temp_c",
                "city": "data.location.name",
                "items_0": "data.items.0.value",
            }},
        }
        result = manager.validate_and_register("p1", defn)
        assert result is not None

    def test_allow_empty_transform(self, manager):
        defn = {"source": {"type": "bus"}}
        result = manager.validate_and_register("p1", defn)
        assert result is not None


# ================================================================
# CONSTRAINTS
# ================================================================


class TestConstraints:
    def test_max_pipelines_per_workspace(self, manager):
        """Enforce max 6 pipelines per workspace."""
        for i in range(MAX_PIPELINES_PER_WORKSPACE):
            result = manager.validate_and_register(
                f"p{i}", make_bus_def(), workspace="test"
            )
            assert result is not None

        # 7th should fail
        result = manager.validate_and_register(
            "overflow", make_bus_def(), workspace="test"
        )
        assert result is None
        assert manager.total_count == MAX_PIPELINES_PER_WORKSPACE

    def test_different_workspaces_independent(self, manager):
        """Pipelines in different workspaces don't affect each other's limits."""
        for i in range(MAX_PIPELINES_PER_WORKSPACE):
            manager.validate_and_register(
                f"a-{i}", make_bus_def(), workspace="ws-a"
            )

        # Different workspace should still work
        result = manager.validate_and_register(
            "b-0", make_bus_def(), workspace="ws-b"
        )
        assert result is not None

    def test_min_poll_interval_enforced(self, manager):
        """HTTP poll interval below minimum should be adjusted."""
        defn = make_http_def(interval=1000)  # 1 second — too fast
        result = manager.validate_and_register("p1", defn)
        assert result is not None
        # Source config should have been adjusted
        assert defn["source"]["interval"] >= MIN_POLL_INTERVAL * 1000

    def test_valid_poll_interval_unchanged(self, manager):
        """HTTP poll interval above minimum should not be changed."""
        defn = make_http_def(interval=30000)
        manager.validate_and_register("p1", defn)
        assert defn["source"]["interval"] == 30000


# ================================================================
# UNREGISTER + CLEANUP
# ================================================================


class TestUnregister:
    def test_unregister(self, manager):
        manager.validate_and_register("p1", make_bus_def())
        assert manager.total_count == 1

        result = manager.unregister("p1")
        assert result is True
        assert manager.total_count == 0

    def test_unregister_nonexistent(self, manager):
        result = manager.unregister("nope")
        assert result is False

    def test_unregister_frees_slot(self, manager):
        """After unregister, the workspace slot should be freed."""
        for i in range(MAX_PIPELINES_PER_WORKSPACE):
            manager.validate_and_register(
                f"p{i}", make_bus_def(), workspace="test"
            )

        # Full — should reject
        assert manager.validate_and_register("overflow", make_bus_def(), workspace="test") is None

        # Remove one
        manager.unregister("p0")

        # Now should accept again
        result = manager.validate_and_register("new", make_bus_def(), workspace="test")
        assert result is not None

    def test_cleanup_workspace(self, manager):
        manager.validate_and_register("p1", make_bus_def(), workspace="demo")
        manager.validate_and_register("p2", make_http_def(), workspace="demo")
        manager.validate_and_register("p3", make_ws_def(), workspace="other")

        removed = manager.cleanup_workspace("demo")
        assert len(removed) == 2
        assert "p1" in removed
        assert "p2" in removed
        assert manager.total_count == 1  # "other" workspace untouched

    def test_cleanup_empty_workspace(self, manager):
        removed = manager.cleanup_workspace("nonexistent")
        assert len(removed) == 0

    def test_cleanup_frees_slots(self, manager):
        """After cleanup, workspace should accept new pipelines."""
        for i in range(MAX_PIPELINES_PER_WORKSPACE):
            manager.validate_and_register(
                f"p{i}", make_bus_def(), workspace="test"
            )

        manager.cleanup_workspace("test")

        # Should work again
        result = manager.validate_and_register("new", make_bus_def(), workspace="test")
        assert result is not None
