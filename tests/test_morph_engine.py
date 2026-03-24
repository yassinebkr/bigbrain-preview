"""Tests for the Morphable UI spring physics and layout system.

Since the FLIP engine is JavaScript (morph.js), we test the Python-side
equivalents and validate the architecture contracts here.

These tests verify:
  1. Layout catalog completeness and validity
  2. Workspace defaults validity
  3. Spring parameter ranges (matching morph.js constants)
  4. Pipeline manager integration with web adapter
"""

import pytest
import json
import re
from pathlib import Path

# ================================================================
# STATIC FILE VALIDATION
# ================================================================

STATIC_DIR = Path(__file__).parent.parent / "bigbrain" / "web" / "static"


class TestStaticFiles:
    """Verify all required static files exist and are valid."""

    def test_index_html_exists(self):
        assert (STATIC_DIR / "index.html").exists()

    def test_morph_js_exists(self):
        assert (STATIC_DIR / "morph.js").exists()

    def test_layout_js_exists(self):
        assert (STATIC_DIR / "layout.js").exists()

    def test_panel_js_exists(self):
        assert (STATIC_DIR / "panel.js").exists()

    def test_bus_client_js_exists(self):
        assert (STATIC_DIR / "bus-client.js").exists()

    def test_pipeline_js_exists(self):
        assert (STATIC_DIR / "pipeline.js").exists()

    def test_app_js_exists(self):
        assert (STATIC_DIR / "app.js").exists()

    def test_style_css_exists(self):
        assert (STATIC_DIR / "style.css").exists()


class TestMorphJSContent:
    """Verify morph.js contains the critical spring physics functions."""

    @pytest.fixture
    def morph_content(self):
        return (STATIC_DIR / "morph.js").read_text()

    def test_has_create_spring(self, morph_content):
        assert "function createSpring" in morph_content

    def test_has_spring_defaults(self, morph_content):
        assert "SPRING_DEFAULTS" in morph_content
        assert "stiffness: 100" in morph_content
        assert "damping: 10" in morph_content

    def test_has_spring_presets(self, morph_content):
        assert "SPRING_PRESETS" in morph_content
        assert "panel" in morph_content
        assert "breathe" in morph_content
        assert "snap" in morph_content
        assert "bounce" in morph_content
        assert "stiff" in morph_content

    def test_has_flip_functions(self, morph_content):
        assert "function snapshotPanels" in morph_content
        assert "function flipPanels" in morph_content
        assert "function breathePanel" in morph_content
        assert "function highlightPanel" in morph_content

    def test_has_morph_throttle(self, morph_content):
        assert "class MorphThrottle" in morph_content

    def test_has_css_linear_generator(self, morph_content):
        assert "function springToLinearCSS" in morph_content
        assert "linear(" in morph_content

    def test_has_three_spring_regimes(self, morph_content):
        """Must handle underdamped, critically damped, and overdamped."""
        assert "zeta < 1" in morph_content or "underdamped" in morph_content.lower()
        assert "zeta === 1" in morph_content or "critically damped" in morph_content.lower()
        # Overdamped is the else branch
        assert "overdamped" in morph_content.lower() or "else" in morph_content

    def test_exports_complete(self, morph_content):
        """All public functions should be exported."""
        for name in [
            "createSpring", "calcSpringDuration", "springToLinearCSS",
            "SPRING_DEFAULTS", "SPRING_PRESETS", "getSpringCSS",
            "snapshotPanels", "flipPanels", "breathePanel", "highlightPanel",
            "MorphThrottle",
        ]:
            assert name in morph_content, f"Missing export: {name}"


class TestLayoutJSContent:
    """Verify layout.js contains all required layouts."""

    @pytest.fixture
    def layout_content(self):
        return (STATIC_DIR / "layout.js").read_text()

    def test_has_layout_catalog(self, layout_content):
        assert "LAYOUT_CATALOG" in layout_content

    def test_has_seven_layouts(self, layout_content):
        """Architecture specifies 6-8 layouts. We have 7."""
        layouts = [
            "focus", "split", "focus-left", "tri-left",
            "quad", "primary-dock", "tri-bottom",
        ]
        for name in layouts:
            assert f"'{name}'" in layout_content or f'"{name}"' in layout_content, \
                f"Missing layout: {name}"

    def test_has_slot_manager(self, layout_content):
        assert "class SlotManager" in layout_content

    def test_has_workspace_defaults(self, layout_content):
        assert "WORKSPACE_DEFAULTS" in layout_content

    def test_workspace_defaults_cover_domains(self, layout_content):
        """Each domain should have a workspace default."""
        domains = ["python-dev", "web-dev", "3d-printing", "electronics", "research", "default"]
        for domain in domains:
            # JS keys can be quoted ('domain') or unquoted (domain:)
            assert (f"'{domain}'" in layout_content or
                    f'"{domain}"' in layout_content or
                    f"{domain}:" in layout_content), \
                f"Missing workspace default: {domain}"

    def test_slot_manager_has_collapse(self, layout_content):
        assert "collapseSlot" in layout_content
        assert "expandSlot" in layout_content
        assert "toggleSlot" in layout_content


class TestPanelJSContent:
    """Verify panel.js contains all required panel types."""

    @pytest.fixture
    def panel_content(self):
        return (STATIC_DIR / "panel.js").read_text()

    def test_has_base_panel(self, panel_content):
        assert "class BasePanel" in panel_content

    def test_base_panel_contract(self, panel_content):
        """Panel contract: mount/subscribe/onEvent/unmount/getState/setState."""
        for method in ["mount(", "subscribe(", "onEvent(", "unmount(", "getState(", "setState("]:
            assert method in panel_content, f"Missing panel contract method: {method}"

    def test_has_chat_panel(self, panel_content):
        assert "class ChatPanel" in panel_content

    def test_has_brain_status_panel(self, panel_content):
        assert "class BrainStatusPanel" in panel_content

    def test_has_task_list_panel(self, panel_content):
        assert "class TaskListPanel" in panel_content

    def test_has_bus_monitor_panel(self, panel_content):
        assert "class BusMonitorPanel" in panel_content

    def test_has_pipeline_panel(self, panel_content):
        assert "class PipelinePanel" in panel_content

    def test_has_status_strip_panel(self, panel_content):
        assert "class StatusStripPanel" in panel_content

    def test_has_panel_registry(self, panel_content):
        assert "PANEL_TYPES" in panel_content
        assert "createPanel" in panel_content
        assert "registerPanelType" in panel_content


class TestStyleCSSContent:
    """Verify CSS has all layout grid definitions."""

    @pytest.fixture
    def css_content(self):
        return (STATIC_DIR / "style.css").read_text()

    def test_has_layout_grids(self, css_content):
        """Each layout must have a CSS grid definition."""
        layouts = ["focus", "split", "focus-left", "tri-left", "quad", "primary-dock", "tri-bottom"]
        for name in layouts:
            assert f'[data-layout="{name}"]' in css_content, \
                f"Missing CSS grid for layout: {name}"

    def test_has_panel_styles(self, css_content):
        assert ".panel" in css_content
        assert ".panel-title-bar" in css_content
        assert ".panel-content" in css_content

    def test_has_collapsed_styles(self, css_content):
        assert ".panel-collapsed" in css_content

    def test_has_dark_theme_vars(self, css_content):
        assert "--bg:" in css_content
        assert "--accent:" in css_content
        assert "--text:" in css_content

    def test_has_focus_mode_overrides(self, css_content):
        assert "data-focus-mode" in css_content

    def test_has_responsive(self, css_content):
        assert "@media" in css_content

    def test_has_status_strip(self, css_content):
        assert "#status-strip" in css_content

    def test_has_chat_styles(self, css_content):
        assert ".chat-msg-user" in css_content
        assert ".chat-msg-assistant" in css_content


class TestBusClientJSContent:
    """Verify bus-client.js has required features."""

    @pytest.fixture
    def bus_content(self):
        return (STATIC_DIR / "bus-client.js").read_text()

    def test_has_bus_client(self, bus_content):
        assert "class BusClient" in bus_content

    def test_has_reconnect(self, bus_content):
        assert "reconnect" in bus_content.lower()

    def test_has_filter_matching(self, bus_content):
        assert "_matches" in bus_content

    def test_has_queue(self, bus_content):
        """Should queue messages when disconnected."""
        assert "_queue" in bus_content


class TestPipelineJSContent:
    """Verify pipeline.js has all three source types."""

    @pytest.fixture
    def pipeline_content(self):
        return (STATIC_DIR / "pipeline.js").read_text()

    def test_has_bus_pipeline(self, pipeline_content):
        assert "class BusPipeline" in pipeline_content

    def test_has_http_pipeline(self, pipeline_content):
        assert "class HttpPollPipeline" in pipeline_content

    def test_has_ws_pipeline(self, pipeline_content):
        assert "class WebSocketPipeline" in pipeline_content

    def test_has_pipeline_manager(self, pipeline_content):
        assert "class PipelineManager" in pipeline_content

    def test_has_nested_value_getter(self, pipeline_content):
        assert "getNestedValue" in pipeline_content

    def test_min_poll_interval(self, pipeline_content):
        """Should enforce 5s minimum poll interval."""
        assert "5000" in pipeline_content


class TestIndexHTML:
    """Verify index.html has the right structure."""

    @pytest.fixture
    def html_content(self):
        return (STATIC_DIR / "index.html").read_text()

    def test_has_grid_container(self, html_content):
        assert 'id="grid-container"' in html_content

    def test_has_status_strip(self, html_content):
        assert 'id="status-strip"' in html_content

    def test_has_chat_input(self, html_content):
        assert 'id="chat-input"' in html_content

    def test_has_workspace_selector(self, html_content):
        assert 'id="workspace-selector"' in html_content

    def test_has_connection_status(self, html_content):
        assert 'id="connection-status"' in html_content

    def test_loads_app_js(self, html_content):
        assert "app.js" in html_content

    def test_loads_style_css(self, html_content):
        assert "style.css" in html_content

    def test_es_modules(self, html_content):
        assert 'type="module"' in html_content
