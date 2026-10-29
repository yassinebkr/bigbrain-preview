"""Front decisions, specialist inputs and provider-native response schema."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectTarget(ClosedModel):
    mode: Literal["new", "existing"]
    path: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def existing_path(self):
        if self.mode == "existing" and not self.path:
            raise ValueError("Existing project requires its exact path")
        return self


class ValidationChange(ClosedModel):
    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    authority: str = Field(min_length=1)


class ResearchInput(ClosedModel):
    type: Literal["research", "search_only"]
    resume_research_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$")
    obligations: list[Annotated[str, Field(min_length=5, max_length=500)]] | None = Field(
        default=None, min_length=1, max_length=6,
        description="Atomic questions explicitly requested by the user. Capture requested scope and source/version restrictions without adding research requirements.")

    @field_validator('obligations')
    @classmethod
    def distinct_obligations(cls, values):
        if values is None:
            return values
        cleaned = [value.strip() for value in values]
        if any(len(value) < 5 for value in cleaned) or len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError('Research obligations must be distinct nonempty questions')
        return cleaned

    @model_validator(mode="after")
    def continuation_requires_research(self):
        if self.resume_research_id and self.type != "research":
            raise ValueError("Continuation requires the full research runtime, not search_only")
        return self


class BoardInput(ClosedModel):
    type: Literal["board_task"]
    title: str = Field(min_length=1)
    description: str | None = None
    status: str = "todo"


class PythonInput(ClosedModel):
    type: Literal["run_file"]
    file: str = Field(min_length=1)


class AttachedProject(ClosedModel):
    project_id: str = Field(min_length=1)
    revision: int = Field(ge=1, strict=True)


class AttachedPythonInput(ClosedModel):
    type: Literal['maintain_project']
    deliverable_type: Literal['python']
    local_project: AttachedProject
    entry_point: str = Field(min_length=1)


class AttachedWebInput(ClosedModel):
    type: Literal['maintain_project']
    deliverable_type: Literal['web_app']
    local_project: AttachedProject
    entry_point: str = Field(min_length=1)
    web_stack: Literal['static']


class WebInput(ClosedModel):
    type: Literal["run_web_project"]
    project_name: str = Field(min_length=1)


class ResearchRoute(ClosedModel):
    brain: Literal["researcher"]
    payload: ResearchInput


class BoardRoute(ClosedModel):
    brain: Literal["taskboard"]
    payload: BoardInput


class PythonRoute(ClosedModel):
    brain: Literal["python_brain"]
    payload: PythonInput | AttachedPythonInput


class WebRoute(ClosedModel):
    brain: Literal["web_app_brain"]
    payload: WebInput | AttachedWebInput


class Respond(ClosedModel):
    operation: Literal["respond"]
    reply: str = Field(min_length=1)


class Clarify(ClosedModel):
    operation: Literal["clarify"]
    reply: str = Field(min_length=1)


class Delegate(ClosedModel):
    operation: Literal["delegate"]
    reply: str = Field(min_length=1)
    objective: str = Field(min_length=2, max_length=8000)
    route: ResearchRoute | BoardRoute | PythonRoute | WebRoute | None = None
    project_target: ProjectTarget | None = None
    test_changes: list[ValidationChange] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def attached_destination(self):
        if (isinstance(self.route, (PythonRoute, WebRoute))
                and isinstance(self.route.payload, (AttachedPythonInput, AttachedWebInput))
                and (self.project_target is not None or self.test_changes)):
            raise ValueError('Attached maintenance uses its selected project scope and preserved validation')
        return self

    def task_payload(self):
        """Adapt validated intent to the existing orchestrator envelope."""
        result = {"reply":self.reply}
        if self.route:
            result["route"] = self.route.model_dump(exclude_none=True)
            result["route"]["payload"]["user_request"] = self.objective
            if isinstance(self.route, ResearchRoute):
                # One model-authored objective is mapped to the specialist's
                # input contract; the model never has to repeat it verbatim.
                result["route"]["payload"]["query"] = self.objective
        else:
            result["task"] = self.objective
        if self.project_target:
            result["project_target"] = self.project_target.model_dump(exclude_none=True)
        if self.test_changes:
            result["test_changes"] = [c.model_dump() for c in self.test_changes]
        return result


class MemoryArguments(ClosedModel):
    query: str | None = None
    id: str | None = None
    key: str | None = None
    value: str | None = None
    quote: str | None = None
    source_message_id: str | None = None
    expected_revision: int | None = None


class ConsultMemory(ClosedModel):
    operation: Literal["consult_memory"]
    tool: Literal["projects.list", "projects.read", "facts.search", "facts.read", "facts.write", "memory.search"]
    arguments: MemoryArguments


class FrontDecision(ClosedModel):
    # A closed root object is accepted by both function-call endpoints and the
    # Codex output schema. Each operation has its own closed argument shape.
    decision: Respond | Clarify | Delegate | ConsultMemory

    @field_validator("decision", mode="before")
    @classmethod
    def validate_selected_operation(cls, value):
        # Report the selected operation's actual error rather than all the
        # irrelevant errors produced while trying the other union variants.
        if isinstance(value, dict):
            operations = {"respond":Respond, "clarify":Clarify, "delegate":Delegate, "consult_memory":ConsultMemory}
            model = operations.get(value.get("operation"))
            if model:
                return model.model_validate(value)
        return value


FRONT_TOOL_SCHEMA = {
    "name": "bigbrain_front_decision",
    "description": "Choose one response, clarification, memory consultation or delegation for this conversation turn.",
    "parameters": FrontDecision.model_json_schema(),
}
