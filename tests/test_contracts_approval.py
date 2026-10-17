"""Pre-implementation contract approval (Phase B, pattern shopifast-local).

Before the agent writes code it proposes checkable contracts; the plan
PAUSES until the user approves. The verdict is stamped on the DesignSpec
(a new immutable revision) and every run manifest links to the approved
spec. Kill switch: BIGBRAIN_CONTRACTS=0.
"""

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType


def _repo(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
    from bigbrain.verification.evidence import default_repository
    return default_repository()


class TestContractParsing:
    def test_plain_json_array(self):
        from bigbrain.verification.contracts import parse_contracts
        parsed = parse_contracts(
            '["le fichier hello.py existe", "le script affiche bonjour"]')
        assert parsed == ["le fichier hello.py existe",
                          "le script affiche bonjour"]

    def test_array_in_prose(self):
        from bigbrain.verification.contracts import parse_contracts
        parsed = parse_contracts(
            'Voici les contrats :\n```json\n["c1", "c2"]\n```\nDone.')
        assert parsed == ["c1", "c2"]

    def test_invalid_response_is_empty(self):
        from bigbrain.verification.contracts import parse_contracts
        assert parse_contracts("no contracts here") == []
        assert parse_contracts("[1, 2]") == []  # non-strings rejected

    async def test_draft_contracts_uses_llm(self):
        from bigbrain.verification.contracts import draft_contracts

        class Provider:
            async def chat_complete(self, messages=None, **kwargs):
                return '["c1", "c2"]'

        assert await draft_contracts(Provider(), "fais un script") == ["c1", "c2"]
        assert await draft_contracts(None, "x") == []

    async def test_draft_contracts_prepends_architect_stack(self):
        from bigbrain.orchestrator.architect import ProjectSpec
        from bigbrain.verification.contracts import draft_contracts

        class Provider:
            def __init__(self):
                self.user_prompt = ""

            async def chat_complete(self, messages=None, **kwargs):
                self.user_prompt = messages[-1]["content"]
                return '["le bouton permet de changer de séance"]'

        provider = Provider()
        project_spec = ProjectSpec(
            project_name="fitness",
            description="programme interactif",
            deliverable_type="web_app",
            interaction_mode="browser",
            entry_point="index.html",
            tech_decisions=["HTML/CSS/JavaScript sans dépendance", "localStorage pour la progression"],
            execution_strategy="preview statique puis tests navigateur",
        )
        contracts = await draft_contracts(
            provider, "crée un programme fitness", project_spec=project_spec)

        assert contracts[0].startswith("[Stack]")
        assert "livrable web_app" in contracts[0]
        assert "HTML/CSS/JavaScript sans dépendance" in contracts[0]
        assert "point d’entrée index.html" in contracts[0]
        assert "Architecture context:" in provider.user_prompt
        assert contracts[1] == "le bouton permet de changer de séance"

        fallback = await draft_contracts(
            None, "crée un programme fitness", project_spec=project_spec)
        assert fallback == [contracts[0]]


class TestPlanNeedsApproval:
    def test_codegen_types_need_approval(self):
        from bigbrain.verification.contracts import plan_needs_approval
        from bigbrain.orchestrator.orchestrator import SubTask

        codegen = SubTask(id="s1", description="d", brain_target="python_brain",
                          payload={"type": "generate_and_execute"})
        research = SubTask(id="s2", description="d", brain_target="researcher",
                           payload={"type": "research"})
        assert plan_needs_approval([codegen]) is True
        assert plan_needs_approval([research]) is False

    def test_kill_switch(self, monkeypatch):
        from bigbrain.verification.contracts import approval_flow_enabled
        monkeypatch.setenv("BIGBRAIN_CONTRACTS", "0")
        assert approval_flow_enabled() is False
        monkeypatch.setenv("BIGBRAIN_CONTRACTS", "1")
        assert approval_flow_enabled() is True


class TestApprovalStamping:
    def test_approve_spec_creates_new_revision(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path, monkeypatch)
        from bigbrain.verification.contracts import build_proposal_spec

        spec = build_proposal_spec("écris fibonacci.py", ["c1", "c2"])
        repo.save_spec(spec)

        approved = repo.approve_spec(spec.design_id, plan_id="p1")
        assert approved is not None
        assert approved.revision == 2
        stamp = approved.metadata["approval"]
        assert stamp["decision"] == "approved"
        assert stamp["by"] == "user"
        assert stamp["plan_id"] == "p1"

        # The original proposal revision is preserved (immutable trail)
        original = repo.load_spec(spec.design_id, 1)
        assert original.revision == 1
        assert "approval" not in original.metadata

    def test_approve_unknown_design_returns_none(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path, monkeypatch)
        assert repo.approve_spec("task-doesnotexist") is None

    async def test_gate_uses_the_approved_spec(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path, monkeypatch)
        from bigbrain.verification.contracts import build_proposal_spec
        from bigbrain.verification.gate import RunGate

        request = "écris un script fib.py qui affiche 10 nombres"
        spec = build_proposal_spec(request, [
            "le fichier fib.py existe dans le projet courant",
            "l'exécution affiche exactement 10 nombres",
        ])
        repo.save_spec(spec)
        approved = repo.approve_spec(spec.design_id)

        gate = RunGate(repository=repo)
        manifest, _ = await gate.evaluate_attempt(
            user_request=request,
            code="print(list(range(10)))",
            execution={"stdout": "0..9", "stderr": "", "exit_code": 0},
            work_dir=tmp_path,
        )
        # The manifest links to the APPROVED revision (r2), not a fresh one
        assert manifest.design_revision == approved.revision
        assert manifest.spec_sha256 == approved.content_sha256()


class RecordingBus:
    def __init__(self):
        self.events = []  # (event_type, payload)
        self.tasks = []

    async def broadcast_event(self, source, event_type, payload,
                              priority=None, **kwargs):
        self.events.append((event_type, payload))

    async def send_task(self, source, target, task_data, priority=None):
        self.tasks.append((target, task_data))


class ContractProvider:
    """LLM that drafts contracts when asked (chat_complete)."""

    def __init__(self):
        self.calls = 0

    async def chat_complete(self, messages=None, **kwargs):
        self.calls += 1
        content = (messages or [{}])[-1].get("content", "")
        if "contracts" in content or "acceptance contracts" in str(messages[0].get("content", "")):
            return '["le fichier demandé existe", "le script produit une sortie"]'
        return "{}"  # planner output — not used here


def _make_orchestrator(monkeypatch):
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator

    monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", "/tmp/bb-test-ev-contracts")
    orch = WorkspaceOrchestrator("default", MessageBus(auth=None),
                                 llm_provider=ContractProvider())
    orch.register_brain("python_brain_0", {"description": "code"})
    orch.brain_pools = {"python_brain": ["python_brain_0"]}
    bus = RecordingBus()
    orch.bus = bus
    return orch, bus


class TestOrchestratorApprovalFlow:
    async def test_codegen_plan_proposes_and_pauses(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
        monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
        orch, bus = _make_orchestrator(monkeypatch)

        dispatched = []
        async def fake_execute(plan, _depth=0):
            dispatched.append(plan.id)
        monkeypatch.setattr(orch, "_execute_ready_subtasks", fake_execute)

        message = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={
                "type": "generate_and_execute",
                "user_request": "écris un script fibonacci.py",
                "description": "écris un script fibonacci.py",
                "reply_to_ui": True,
            },
        )
        await orch._handle_task_request(message)

        plan = list(orch.task_plans.values())[0]
        assert plan.awaiting_approval is True
        assert dispatched == []  # paused: nothing executes yet

        proposal = next((p for t, p in bus.events
                         if t == "contracts.proposal"), None)
        assert proposal is not None
        assert proposal["plan_id"] == plan.id
        assert proposal["design_id"].startswith("task-")
        assert len(proposal["contracts"]) >= 1

    async def test_approval_resumes_the_plan(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
        monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
        orch, bus = _make_orchestrator(monkeypatch)

        async def fake_execute(plan, _depth=0):
            pass
        monkeypatch.setattr(orch, "_execute_ready_subtasks", fake_execute)

        message = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={"type": "generate_and_execute",
                     "user_request": "écris un script fibonacci.py"},
        )
        await orch._handle_task_request(message)
        plan = list(orch.task_plans.values())[0]
        design_id = plan.approval_design_id

        # User clicks Approve → the orchestrator resumes the plan
        await orch._handle_contracts_approval({
            "type": "contracts.approval",
            "plan_id": plan.id,
            "design_id": design_id,
            "approve": True,
        })
        assert plan.awaiting_approval is False
        types = [t for t, _ in bus.events]
        assert "contracts.approved" in types

        # The approval is stamped on the spec (new revision)
        from bigbrain.verification.evidence import default_repository
        spec = default_repository().load_latest_spec(design_id)
        assert spec is not None
        assert spec.metadata["approval"]["decision"] == "approved"

    async def test_rejection_cancels_the_plan(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
        monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
        orch, bus = _make_orchestrator(monkeypatch)

        message = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={"type": "generate_and_execute",
                     "user_request": "écris un script fibonacci.py"},
        )
        await orch._handle_task_request(message)
        plan = list(orch.task_plans.values())[0]

        await orch._handle_contracts_approval({
            "type": "contracts.approval",
            "plan_id": plan.id,
            "design_id": plan.approval_design_id,
            "approve": False,
        })
        types = [t for t, _ in bus.events]
        assert "contracts.rejected" in types
        from bigbrain.orchestrator.orchestrator import TaskStatus
        assert plan.status == TaskStatus.CANCELLED

    async def test_non_codegen_plan_skips_the_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
        monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
        orch, bus = _make_orchestrator(monkeypatch)

        executed = []
        async def fake_execute(plan, _depth=0):
            executed.append(plan.id)
        monkeypatch.setattr(orch, "_execute_ready_subtasks", fake_execute)

        message = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={"type": "research", "query": "websockets",
                     "user_request": "research websockets"},
        )
        await orch._handle_task_request(message)
        plan = list(orch.task_plans.values())[0]
        assert plan.awaiting_approval is False
        assert executed == [plan.id]  # dispatched immediately
        types = [t for t, _ in bus.events]
        assert "contracts.proposal" not in types

    async def test_kill_switch_disables_the_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGBRAIN_EVIDENCE_ROOT", str(tmp_path / "ev"))
        monkeypatch.setenv("BIGBRAIN_TASKS_FILE", str(tmp_path / "tasks.json"))
        monkeypatch.setenv("BIGBRAIN_CONTRACTS", "0")
        orch, bus = _make_orchestrator(monkeypatch)

        executed = []
        async def fake_execute(plan, _depth=0):
            executed.append(plan.id)
        monkeypatch.setattr(orch, "_execute_ready_subtasks", fake_execute)

        message = BusMessage(
            type=MessageType.TASK, source="front_brain",
            target="orchestrator_default",
            payload={"type": "generate_and_execute",
                     "user_request": "écris un script fibonacci.py"},
        )
        await orch._handle_task_request(message)
        plan = list(orch.task_plans.values())[0]
        assert plan.awaiting_approval is False
        assert executed == [plan.id]


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TestApprovalRouteAuth:
    """Regression: the approval POST must travel the bus as an
    AUTHENTICATED source. An unregistered source (e.g. "web_server")
    is silently DROPPED by the authenticated bus — the plan then waits
    forever even though the UI showed the click as accepted."""

    async def test_route_sends_via_authenticated_source(self):
        from bigbrain.bus.auth import BusAuth
        from bigbrain.bus.bus import MessageBus
        from bigbrain.web.server import WebServer

        auth = BusAuth()
        auth.generate_token("morphable_ui")
        bus = MessageBus(auth=auth)

        received = []

        async def orchestrator_handler(message):
            received.append(message.payload)

        bus.subscribe("orchestrator_default", orchestrator_handler)

        server = WebServer(bus=bus)
        response = await server._handle_contracts_approve(FakeRequest({
            "design_id": "task-x", "plan_id": "p1", "approve": True,
        }))
        assert response.status == 200
        assert len(received) == 1  # delivered, not silently dropped
        assert received[0]["type"] == "contracts.approval"
        assert received[0]["approve"] is True
