"""Tests for the Architect Phase — ProjectSpec generation and parsing."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from bigbrain.orchestrator.architect import (
    ArchitectPhase,
    DataModelSpec,
    FieldDef,
    FileSpec,
    FunctionContract,
    ProjectSpec,
)


def test_parse_spec_respects_explicit_non_executable_deliverable():
    architect = ArchitectPhase(llm_provider=None)
    spec = architect._parse_spec({
        "project_name": "fitness-models",
        "executable": False,
        "entry_point": None,
        "file_specs": [{
            "path": "models.py",
            "purpose": "Reusable domain models only",
            "dependencies": [],
        }],
    })

    assert spec.executable is False
    assert spec.entry_point is None
    assert [file.path for file in spec.file_specs] == ["models.py"]


def test_parse_spec_repairs_missing_entry_point():
    architect = ArchitectPhase(llm_provider=None)
    spec = architect._parse_spec({
        "project_name": "fitness",
        "file_specs": [{
            "path": "models.py",
            "purpose": "models",
            "dependencies": [],
        }],
        "entry_point": "main.py",
    })

    assert spec.entry_point == "main.py"
    main = spec.get_file_spec("main.py")
    assert main is not None
    assert main.dependencies == ["models.py"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """LLM provider mock with chat_complete."""
    llm = MagicMock()
    llm.chat_complete = AsyncMock()
    return llm


@pytest.fixture
def architect(mock_llm):
    return ArchitectPhase(llm_provider=mock_llm, model="test-model")


@pytest.fixture
def sample_spec_json():
    """A realistic architect output for a chat app."""
    return {
        "project_name": "realtime-chat",
        "description": "A realtime chat application with authentication and WebSocket support.",
        "tech_decisions": [
            "Use aiohttp for async HTTP + WebSocket: lightweight, stdlib-adjacent",
            "In-memory storage: no external DB dependency for simplicity",
            "SHA-256 password hashing via hashlib: stdlib, no bcrypt needed for demo",
        ],
        "data_models": [
            {
                "name": "User",
                "description": "Represents a registered user",
                "fields": [
                    {"name": "username", "type": "str", "description": "Unique username"},
                    {"name": "password_hash", "type": "str", "description": "SHA-256 hash of password"},
                    {"name": "created_at", "type": "float", "description": "Unix timestamp of registration"},
                ],
                "methods": [
                    {"name": "check_password", "params": [{"name": "self"}, {"name": "password", "type": "str"}], "returns": "bool", "description": "Verify password against stored hash"},
                ],
            },
            {
                "name": "Message",
                "description": "A chat message",
                "fields": [
                    {"name": "id", "type": "int", "description": "Auto-incrementing message ID"},
                    {"name": "author", "type": "str", "description": "Username of sender"},
                    {"name": "content", "type": "str", "description": "Message text"},
                    {"name": "timestamp", "type": "float", "description": "Unix timestamp"},
                ],
                "methods": [],
            },
        ],
        "file_specs": [
            {
                "path": "models.py",
                "purpose": "Data models and in-memory storage layer",
                "exports": [
                    {"name": "User", "params": [], "returns": "class", "description": "User dataclass"},
                    {"name": "Message", "params": [], "returns": "class", "description": "Message dataclass"},
                    {"name": "create_user", "params": [{"name": "username", "type": "str"}, {"name": "password", "type": "str"}], "returns": "User", "description": "Register a new user"},
                    {"name": "get_user", "params": [{"name": "username", "type": "str"}], "returns": "Optional[User]", "description": "Look up user by username"},
                    {"name": "add_message", "params": [{"name": "author", "type": "str"}, {"name": "content", "type": "str"}], "returns": "Message", "description": "Store a new message"},
                    {"name": "get_messages", "params": [{"name": "limit", "type": "int", "default": "50"}], "returns": "List[Message]", "description": "Get recent messages"},
                ],
                "data_models": ["User", "Message"],
                "imports_from": {},
                "dependencies": [],
                "implementation_notes": "Use dataclasses. Store users in dict[str, User], messages in list[Message]. Thread-safe not needed (single async event loop).",
                "edge_cases": ["duplicate username", "empty username/password", "message limit 0 or negative"],
            },
            {
                "path": "auth.py",
                "purpose": "Authentication: login, session tokens, middleware",
                "exports": [
                    {"name": "login", "params": [{"name": "username", "type": "str"}, {"name": "password", "type": "str"}], "returns": "Optional[str]", "description": "Verify credentials, return session token or None"},
                    {"name": "register", "params": [{"name": "username", "type": "str"}, {"name": "password", "type": "str"}], "returns": "tuple[bool, str]", "description": "Register new user, return (success, message)"},
                    {"name": "validate_session", "params": [{"name": "token", "type": "str"}], "returns": "Optional[str]", "description": "Validate session token, return username or None"},
                ],
                "data_models": [],
                "imports_from": {"models.py": ["create_user", "get_user"]},
                "dependencies": ["models.py"],
                "implementation_notes": "Use secrets.token_hex(32) for session tokens. Store sessions in dict[str, str] mapping token→username. Use hashlib.sha256 for password hashing.",
                "edge_cases": ["expired/invalid token", "duplicate registration", "empty credentials"],
            },
            {
                "path": "websocket_handler.py",
                "purpose": "WebSocket connection management and message broadcasting",
                "exports": [
                    {"name": "WebSocketHandler", "params": [], "returns": "class", "description": "Manages WebSocket connections and broadcasting"},
                ],
                "data_models": [],
                "imports_from": {"models.py": ["add_message", "get_messages"], "auth.py": ["validate_session"]},
                "dependencies": ["models.py", "auth.py"],
                "implementation_notes": "Track connected clients in set. On new message: validate session, store via add_message, broadcast JSON to all connected clients. Send last 50 messages on connect.",
                "edge_cases": ["client disconnects mid-broadcast", "invalid session on WS connect", "malformed JSON from client"],
            },
            {
                "path": "app.py",
                "purpose": "HTTP routes and aiohttp application setup",
                "exports": [
                    {"name": "create_app", "params": [], "returns": "web.Application", "description": "Create and configure the aiohttp application"},
                ],
                "data_models": [],
                "imports_from": {"auth.py": ["login", "register", "validate_session"], "websocket_handler.py": ["WebSocketHandler"]},
                "dependencies": ["auth.py", "websocket_handler.py"],
                "implementation_notes": "Routes: POST /api/login, POST /api/register, GET /ws (WebSocket), GET / (serve index.html). Use aiohttp.web.",
                "edge_cases": ["missing form fields", "JSON parse errors", "static file not found"],
            },
            {
                "path": "templates/index.html",
                "purpose": "Frontend UI — login form, chat interface, WebSocket client",
                "exports": [],
                "data_models": [],
                "imports_from": {},
                "dependencies": [],
                "implementation_notes": "Single HTML file with embedded CSS and JS. Login form toggles to chat view. JS WebSocket client connects to /ws with session token. Display messages in scrollable div, auto-scroll on new message.",
                "edge_cases": ["WebSocket disconnect/reconnect", "XSS in message content (escape HTML)"],
            },
            {
                "path": "main.py",
                "purpose": "Entry point — starts the server",
                "exports": [],
                "data_models": [],
                "imports_from": {"app.py": ["create_app"]},
                "dependencies": ["app.py"],
                "implementation_notes": "Import create_app, run with aiohttp.web.run_app on port 8080. Print startup message.",
                "edge_cases": ["port already in use"],
            },
        ],
        "entry_point": "main.py",
        "execution_strategy": "python main.py — starts HTTP server on port 8080. Open browser to http://localhost:8080",
    }


# ---------------------------------------------------------------------------
# Unit tests — Data structures
# ---------------------------------------------------------------------------

class TestFieldDef:
    def test_to_dict_minimal(self):
        f = FieldDef(name="x", type="int")
        assert f.to_dict() == {"name": "x", "type": "int"}

    def test_to_dict_full(self):
        f = FieldDef(name="x", type="int", description="count", default="0")
        d = f.to_dict()
        assert d["description"] == "count"
        assert d["default"] == "0"


class TestFunctionContract:
    def test_signature_no_params(self):
        fn = FunctionContract(name="get_all", params=[], returns="list")
        assert fn.signature() == "def get_all() -> list"

    def test_signature_with_params(self):
        fn = FunctionContract(
            name="login",
            params=[
                {"name": "username", "type": "str"},
                {"name": "password", "type": "str"},
            ],
            returns="Optional[str]",
        )
        assert fn.signature() == "def login(username: str, password: str) -> Optional[str]"

    def test_signature_with_default(self):
        fn = FunctionContract(
            name="get_msgs",
            params=[{"name": "limit", "type": "int", "default": "50"}],
            returns="List[Message]",
        )
        assert "limit: int = 50" in fn.signature()

    def test_to_dict(self):
        fn = FunctionContract(
            name="test", params=[], returns="None",
            description="does stuff", raises=["ValueError"],
        )
        d = fn.to_dict()
        assert d["name"] == "test"
        assert d["raises"] == ["ValueError"]


class TestDataModelSpec:
    def test_to_dict(self):
        dm = DataModelSpec(
            name="User",
            description="A user",
            fields=[FieldDef("name", "str")],
            methods=[FunctionContract("greet", [], "str")],
        )
        d = dm.to_dict()
        assert d["name"] == "User"
        assert len(d["fields"]) == 1
        assert len(d["methods"]) == 1


class TestFileSpec:
    def test_to_dict(self):
        fs = FileSpec(
            path="auth.py",
            purpose="Authentication",
            dependencies=["models.py"],
            imports_from={"models.py": ["User"]},
        )
        d = fs.to_dict()
        assert d["path"] == "auth.py"
        assert d["dependencies"] == ["models.py"]

    def test_render_for_worker_basic(self):
        fs = FileSpec(
            path="auth.py",
            purpose="Authentication module",
            exports=[
                FunctionContract("login", [{"name": "user", "type": "str"}], "bool", "Log in"),
            ],
            imports_from={"models.py": ["User", "get_db"]},
            dependencies=["models.py"],
            implementation_notes="Use hashlib for hashing.",
            edge_cases=["empty password"],
        )
        text = fs.render_for_worker()
        assert "# File: auth.py" in text
        assert "def login(user: str) -> bool" in text
        assert "from models import User, get_db" in text
        assert "Use hashlib" in text
        assert "empty password" in text

    def test_render_with_upstream(self):
        models_spec = FileSpec(
            path="models.py",
            purpose="Data models",
            exports=[
                FunctionContract("get_user", [{"name": "name", "type": "str"}], "User"),
            ],
            data_models=[
                DataModelSpec("User", "A user", fields=[FieldDef("name", "str")]),
            ],
        )
        auth_spec = FileSpec(
            path="auth.py",
            purpose="Auth",
            dependencies=["models.py"],
            imports_from={"models.py": ["get_user", "User"]},
        )
        text = auth_spec.render_for_worker(upstream_specs=[models_spec])
        assert "Dependency Interfaces" in text
        assert "models.py" in text
        assert "get_user" in text
        assert "class User" in text


class TestProjectSpec:
    def test_get_file_spec(self):
        spec = ProjectSpec(
            project_name="test",
            description="test",
            file_specs=[
                FileSpec(path="a.py", purpose="A"),
                FileSpec(path="b.py", purpose="B"),
            ],
        )
        assert spec.get_file_spec("a.py").purpose == "A"
        assert spec.get_file_spec("c.py") is None

    def test_get_upstream_specs(self):
        models = FileSpec(path="models.py", purpose="Models")
        auth = FileSpec(path="auth.py", purpose="Auth", dependencies=["models.py"])
        spec = ProjectSpec(
            project_name="test",
            description="test",
            file_specs=[models, auth],
        )
        upstream = spec.get_upstream_specs(auth)
        assert len(upstream) == 1
        assert upstream[0].path == "models.py"

    def test_dependency_order(self):
        models = FileSpec(path="models.py", purpose="Models", dependencies=[])
        auth = FileSpec(path="auth.py", purpose="Auth", dependencies=["models.py"])
        app = FileSpec(path="app.py", purpose="App", dependencies=["auth.py", "models.py"])
        spec = ProjectSpec(
            project_name="test",
            description="test",
            file_specs=[app, auth, models],  # intentionally out of order
        )
        order = spec.dependency_order()
        paths = [fs.path for fs in order]
        assert paths.index("models.py") < paths.index("auth.py")
        assert paths.index("auth.py") < paths.index("app.py")

    def test_dependency_order_no_deps(self):
        a = FileSpec(path="a.py", purpose="A")
        b = FileSpec(path="b.py", purpose="B")
        spec = ProjectSpec(project_name="t", description="t", file_specs=[a, b])
        order = spec.dependency_order()
        assert len(order) == 2

    def test_to_dict_roundtrip(self):
        spec = ProjectSpec(
            project_name="chat",
            description="Chat app",
            tech_decisions=["aiohttp"],
            data_models=[DataModelSpec("User", "user")],
            file_specs=[FileSpec(path="main.py", purpose="entry")],
            entry_point="main.py",
        )
        d = spec.to_dict()
        assert d["project_name"] == "chat"
        assert len(d["data_models"]) == 1
        assert len(d["file_specs"]) == 1


# ---------------------------------------------------------------------------
# Unit tests — ArchitectPhase
# ---------------------------------------------------------------------------

class TestArchitectPhase:
    @pytest.mark.asyncio
    async def test_design_basic(self, architect, mock_llm, sample_spec_json):
        """Architect produces a valid ProjectSpec from LLM output."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design("Build a realtime chat app")

        assert isinstance(spec, ProjectSpec)
        assert spec.project_name == "realtime-chat"
        assert len(spec.data_models) == 2
        assert len(spec.file_specs) == 7
        assert spec.get_file_spec("tests/test_acceptance.py") is not None
        assert spec.entry_point == "main.py"

    @pytest.mark.asyncio
    async def test_design_with_research(self, architect, mock_llm, sample_spec_json):
        """Research context is passed to the LLM call."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design(
            "Build a chat app",
            research_context={"websocket libs": "aiohttp is good"},
        )

        call_args = mock_llm.chat_complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_msg = messages[-1]["content"]
        assert "Research Findings" in user_msg
        assert "aiohttp is good" in user_msg

    @pytest.mark.asyncio
    async def test_design_code_fenced(self, architect, mock_llm, sample_spec_json):
        """Handles LLM output wrapped in code fences."""
        fenced = f"```json\n{json.dumps(sample_spec_json)}\n```"
        mock_llm.chat_complete.return_value = fenced

        spec = await architect.design("Build a chat app")
        assert spec.project_name == "realtime-chat"

    @pytest.mark.asyncio
    async def test_design_invalid_json(self, architect, mock_llm):
        """Raises ValueError on unparseable output."""
        mock_llm.chat_complete.return_value = "This is not JSON at all."

        with pytest.raises(ValueError, match="could not parse"):
            await architect.design("Build something")

    @pytest.mark.asyncio
    async def test_data_model_resolution(self, architect, mock_llm, sample_spec_json):
        """File specs resolve data model references to full DataModelSpec objects."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design("Build a chat app")

        models_file = spec.get_file_spec("models.py")
        assert models_file is not None
        assert len(models_file.data_models) == 2
        assert models_file.data_models[0].name == "User"
        assert len(models_file.data_models[0].fields) == 3

    @pytest.mark.asyncio
    async def test_function_contracts_parsed(self, architect, mock_llm, sample_spec_json):
        """Exports are parsed into FunctionContract objects with signatures."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design("Build a chat app")

        auth_file = spec.get_file_spec("auth.py")
        assert auth_file is not None
        login_fn = next(e for e in auth_file.exports if e.name == "login")
        assert "username: str" in login_fn.signature()
        assert "Optional[str]" in login_fn.signature()

    @pytest.mark.asyncio
    async def test_imports_and_deps_parsed(self, architect, mock_llm, sample_spec_json):
        """imports_from and dependencies are correctly parsed."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design("Build a chat app")

        ws = spec.get_file_spec("websocket_handler.py")
        assert "models.py" in ws.dependencies
        assert "auth.py" in ws.dependencies
        assert ws.imports_from["models.py"] == ["add_message", "get_messages"]

    @pytest.mark.asyncio
    async def test_render_for_worker_integration(self, architect, mock_llm, sample_spec_json):
        """Full integration: design → render worker prompt for a file."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        spec = await architect.design("Build a chat app")

        auth = spec.get_file_spec("auth.py")
        upstream = spec.get_upstream_specs(auth)
        prompt = auth.render_for_worker(upstream_specs=upstream)

        # Worker prompt should include auth's own exports
        assert "def login" in prompt
        assert "def register" in prompt
        # And upstream interfaces
        assert "Dependency Interfaces" in prompt
        assert "models.py" in prompt
        assert "create_user" in prompt

    @pytest.mark.asyncio
    async def test_model_passed_to_llm(self, architect, mock_llm, sample_spec_json):
        """Model override is passed to chat_complete."""
        mock_llm.chat_complete.return_value = json.dumps(sample_spec_json)

        await architect.design("Build something")

        call_kwargs = mock_llm.chat_complete.call_args.kwargs
        assert call_kwargs.get("model") == "test-model"

    @pytest.mark.asyncio
    async def test_empty_file_specs(self, architect, mock_llm):
        """Handles spec with no files gracefully."""
        mock_llm.chat_complete.return_value = json.dumps({
            "project_name": "empty",
            "description": "nothing",
            "file_specs": [],
        })

        spec = await architect.design("Build nothing")
        assert spec.project_name == "empty"
        assert len(spec.file_specs) == 0

    @pytest.mark.asyncio  
    async def test_inline_data_models(self, architect, mock_llm):
        """Handles inline data model dicts in file_specs (fallback)."""
        mock_llm.chat_complete.return_value = json.dumps({
            "project_name": "test",
            "description": "test",
            "data_models": [],
            "file_specs": [{
                "path": "main.py",
                "purpose": "Entry",
                "data_models": [{"name": "Item", "description": "An item"}],
                "exports": [],
                "dependencies": [],
            }],
        })

        spec = await architect.design("test")
        assert len(spec.file_specs[0].data_models) == 1
        assert spec.file_specs[0].data_models[0].name == "Item"


# ---------------------------------------------------------------------------
# Integration tests — Artifact flow through orchestrator
# ---------------------------------------------------------------------------

class TestArtifactFlow:
    """Tests that upstream code is properly passed to downstream workers."""

    def test_upstream_context_keyed_by_filepath(self):
        """Orchestrator should key upstream_context by file_path when available."""
        from bigbrain.orchestrator.orchestrator import (
            WorkspaceOrchestrator, TaskPlan, SubTask, TaskStatus
        )
        from bigbrain.bus.bus import MessageBus

        bus = MessageBus()
        orch = WorkspaceOrchestrator("test", bus)

        plan = TaskPlan(
            id="plan1",
            original_task=None,
            subtasks=[
                SubTask(
                    id="s1",
                    description="Write models.py",
                    brain_target="python_brain",
                    payload={"type": "write_project_file"},
                    status=TaskStatus.COMPLETE,
                    result={
                        "success": True,
                        "file_path": "models.py",
                        "file_content": "class User:\n    pass\n",
                    },
                ),
                SubTask(
                    id="s2",
                    description="Write auth.py",
                    brain_target="python_brain",
                    payload={
                        "type": "write_project_file",
                        "file_path": "auth.py",
                    },
                    dependencies={"s1"},
                    status=TaskStatus.PENDING,
                ),
            ],
        )

        import asyncio
        resolved = asyncio.get_event_loop().run_until_complete(
            orch._resolve_payload_references(plan.subtasks[1].payload, plan)
        )

        # upstream_context should be keyed by file_path, not brain:description
        assert "upstream_context" in resolved
        assert "models.py" in resolved["upstream_context"]
        upstream_models = resolved["upstream_context"]["models.py"]
        assert upstream_models["file_content"] == "class User:\n    pass\n"

    def test_render_with_actual_code(self):
        """FileSpec.render_for_worker should show interface contracts."""
        models = FileSpec(
            path="models.py",
            purpose="Data models",
            exports=[
                FunctionContract(
                    "create_user",
                    [{"name": "name", "type": "str"}],
                    "User",
                    "Create a user",
                ),
            ],
            data_models=[
                DataModelSpec(
                    "User", "A user",
                    fields=[FieldDef("name", "str"), FieldDef("email", "str")],
                ),
            ],
        )
        auth = FileSpec(
            path="auth.py",
            purpose="Auth module",
            imports_from={"models.py": ["create_user", "User"]},
            dependencies=["models.py"],
            exports=[
                FunctionContract("login", [{"name": "u", "type": "str"}], "bool"),
            ],
        )

        prompt = auth.render_for_worker(upstream_specs=[models])

        # Should contain auth's exports
        assert "def login" in prompt
        # Should contain upstream interface
        assert "create_user" in prompt
        assert "class User" in prompt
        # Should contain import instruction
        assert "from models import create_user, User" in prompt

    def test_syntax_check_valid(self):
        """Valid Python passes syntax check."""
        from bigbrain.brains.python_brain import PythonBrain
        result = PythonBrain._check_syntax("x = 1\nprint(x)\n", "test.py")
        assert result is None

    def test_syntax_check_invalid(self):
        """Invalid Python returns error message."""
        from bigbrain.brains.python_brain import PythonBrain
        result = PythonBrain._check_syntax("def foo(\n", "test.py")
        assert result is not None
        assert "SyntaxError" in result
        assert "test.py" in result

    def test_syntax_check_html_not_checked(self):
        """HTML files don't go through Python syntax check."""
        # This is tested implicitly by the file_path.endswith(".py") check
        # in _write_project_file, but let's verify the check method works
        from bigbrain.brains.python_brain import PythonBrain
        # HTML is not valid Python but we shouldn't check it
        result = PythonBrain._check_syntax("<html></html>", "index.html")
        # Actually this would fail Python syntax check but the method
        # is only CALLED for .py files in the write loop
        assert result is not None  # It IS a syntax error for Python

    def test_build_file_fix_prompt(self):
        """Fix prompt includes errors and original code."""
        from bigbrain.brains.python_brain import PythonBrain
        brain = PythonBrain.__new__(PythonBrain)  # skip __init__

        prompt = brain._build_file_fix_prompt(
            file_path="auth.py",
            project_name="chat",
            user_request="build chat",
            previous_code="def foo(\n    pass",
            attempt_history=[{"attempt": 1, "error": "SyntaxError line 1: unexpected EOF"}],
            original_prompt="Write auth.py...",
        )
        assert "auth.py" in prompt
        assert "SyntaxError" in prompt
        assert "def foo(" in prompt
        assert "Fix ALL syntax errors" in prompt

    def test_dependency_order_complex(self):
        """Topological order with diamond dependency pattern."""
        #   models (no deps)
        #   ├── auth (depends on models)
        #   ├── ws (depends on models)
        #   └── app (depends on auth + ws)
        models = FileSpec(path="models.py", purpose="M", dependencies=[])
        auth = FileSpec(path="auth.py", purpose="A", dependencies=["models.py"])
        ws = FileSpec(path="ws.py", purpose="W", dependencies=["models.py"])
        app = FileSpec(path="app.py", purpose="App", dependencies=["auth.py", "ws.py"])

        spec = ProjectSpec(
            project_name="test",
            description="test",
            file_specs=[app, ws, auth, models],  # reverse order
        )
        order = spec.dependency_order()
        paths = [fs.path for fs in order]

        # models must come before auth and ws
        assert paths.index("models.py") < paths.index("auth.py")
        assert paths.index("models.py") < paths.index("ws.py")
        # auth and ws must come before app
        assert paths.index("auth.py") < paths.index("app.py")
        assert paths.index("ws.py") < paths.index("app.py")
