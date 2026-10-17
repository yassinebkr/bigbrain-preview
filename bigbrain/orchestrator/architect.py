"""
Architect Phase — Comprehensive project specification before code generation.

The architect phase sits between complexity assessment and task dispatch.
Instead of going straight from "build a chat app" to "write auth.py",
the architect produces a detailed technical specification that gives each
worker brain enough context to write correct code in isolation.

Flow:
    User Request → Complexity Assessment → [Research] → ARCHITECT → Task DAG → Workers

The architect produces a ProjectSpec containing:
    - Technology decisions (stdlib only, or specific frameworks)
    - Data models with exact fields and types
    - Interface contracts (function signatures between files)
    - File specs with imports, exports, and implementation guidance
    - Dependency graph
    - Entry point and execution strategy

Each worker brain receives its FileSpec + all upstream FileSpecs it depends on,
giving it enough context to write code that integrates correctly without
seeing the full project.

Reference: MetaGPT's structured artifact passing, ChatDev's waterfall phases.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FieldDef:
    """A field in a data model."""
    name: str
    type: str  # Python type annotation as string
    description: str = ""
    default: Optional[str] = None  # repr of default value, or None

    def to_dict(self) -> dict:
        d = {"name": self.name, "type": self.type}
        if self.description:
            d["description"] = self.description
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class FunctionContract:
    """Interface contract for a function or method."""
    name: str
    params: List[Dict[str, str]]  # [{name, type, default?}]
    returns: str  # return type annotation
    description: str = ""
    raises: List[str] = field(default_factory=list)

    def signature(self) -> str:
        """Render as a Python-style signature string."""
        parts = []
        for p in self.params:
            s = f"{p['name']}: {p.get('type', 'Any')}"
            if "default" in p:
                s += f" = {p['default']}"
            parts.append(s)
        return f"def {self.name}({', '.join(parts)}) -> {self.returns}"

    def to_dict(self) -> dict:
        d = {"name": self.name, "params": self.params, "returns": self.returns}
        if self.description:
            d["description"] = self.description
        if self.raises:
            d["raises"] = self.raises
        return d


@dataclass
class DataModelSpec:
    """Specification for a data model / class."""
    name: str
    description: str
    fields: List[FieldDef] = field(default_factory=list)
    methods: List[FunctionContract] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
            "methods": [m.to_dict() for m in self.methods],
        }


@dataclass
class FileSpec:
    """Detailed specification for one source file."""
    path: str
    purpose: str
    exports: List[FunctionContract] = field(default_factory=list)
    data_models: List[DataModelSpec] = field(default_factory=list)
    imports_from: Dict[str, List[str]] = field(default_factory=dict)  # file -> [names]
    dependencies: List[str] = field(default_factory=list)  # file paths
    implementation_notes: str = ""  # detailed guidance for the worker
    edge_cases: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "purpose": self.purpose,
            "exports": [e.to_dict() for e in self.exports],
            "data_models": [dm.to_dict() for dm in self.data_models],
            "imports_from": self.imports_from,
            "dependencies": self.dependencies,
            "implementation_notes": self.implementation_notes,
            "edge_cases": self.edge_cases,
        }

    def render_for_worker(self, upstream_specs: List["FileSpec"] = None) -> str:
        """Render this spec as readable text for a worker brain's prompt.

        Includes upstream dependency specs so the worker knows the exact
        interfaces it must call/import.
        """
        lines = [
            f"# File: {self.path}",
            f"Purpose: {self.purpose}",
            "",
        ]

        # Show what this file must export
        if self.exports:
            lines.append("## Exports (you MUST implement these exactly):")
            for fn in self.exports:
                lines.append(f"  {fn.signature()}")
                if fn.description:
                    lines.append(f"    {fn.description}")
                if fn.raises:
                    lines.append(f"    Raises: {', '.join(fn.raises)}")
            lines.append("")

        # Show data models this file defines
        if self.data_models:
            lines.append("## Data Models (define in this file):")
            for dm in self.data_models:
                lines.append(f"  class {dm.name}:")
                lines.append(f"    \"{dm.description}\"")
                for f in dm.fields:
                    default = f" = {f.default}" if f.default else ""
                    lines.append(f"    {f.name}: {f.type}{default}  # {f.description}")
                for m in dm.methods:
                    lines.append(f"    {m.signature()}")
            lines.append("")

        # Show what this file imports from dependencies
        if self.imports_from:
            lines.append("## Imports (use these exact names):")
            for dep_file, names in self.imports_from.items():
                module = dep_file.replace("/", ".").replace(".py", "")
                lines.append(f"  from {module} import {', '.join(names)}")
            lines.append("")

        # Show upstream dependency interfaces (so the worker knows what's available)
        if upstream_specs:
            lines.append("## Dependency Interfaces (already implemented):")
            for spec in upstream_specs:
                lines.append(f"  ### {spec.path}")
                for fn in spec.exports:
                    lines.append(f"    {fn.signature()}")
                for dm in spec.data_models:
                    lines.append(f"    class {dm.name}: {dm.description}")
                    for fld in dm.fields:
                        lines.append(f"      {fld.name}: {fld.type}")
            lines.append("")

        if self.implementation_notes:
            lines.append(f"## Implementation Notes:\n{self.implementation_notes}")
            lines.append("")

        if self.edge_cases:
            lines.append("## Edge Cases to Handle:")
            for ec in self.edge_cases:
                lines.append(f"  - {ec}")

        return "\n".join(lines)


@dataclass
class ProjectSpec:
    """Complete project specification produced by the architect phase."""
    project_name: str
    description: str
    tech_decisions: List[str] = field(default_factory=list)
    data_models: List[DataModelSpec] = field(default_factory=list)
    file_specs: List[FileSpec] = field(default_factory=list)
    executable: bool = True
    entry_point: Optional[str] = "main.py"
    execution_strategy: str = ""  # how to run/test
    deliverable_type: str = "python"  # python | web_app
    interaction_mode: str = "cli"  # cli | browser | library

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "description": self.description,
            "tech_decisions": self.tech_decisions,
            "data_models": [dm.to_dict() for dm in self.data_models],
            "file_specs": [fs.to_dict() for fs in self.file_specs],
            "executable": self.executable,
            "entry_point": self.entry_point,
            "execution_strategy": self.execution_strategy,
            "deliverable_type": self.deliverable_type,
            "interaction_mode": self.interaction_mode,
        }

    def get_file_spec(self, path: str) -> Optional[FileSpec]:
        """Get FileSpec by path."""
        for fs in self.file_specs:
            if fs.path == path:
                return fs
        return None

    def get_upstream_specs(self, file_spec: FileSpec) -> List[FileSpec]:
        """Get FileSpecs for all dependencies of a given file."""
        upstream = []
        for dep_path in file_spec.dependencies:
            dep_spec = self.get_file_spec(dep_path)
            if dep_spec:
                upstream.append(dep_spec)
        return upstream

    def dependency_order(self) -> List[FileSpec]:
        """Return file specs in topological order (dependencies first)."""
        visited = set()
        order = []
        path_map = {fs.path: fs for fs in self.file_specs}

        def visit(fs: FileSpec):
            if fs.path in visited:
                return
            visited.add(fs.path)
            for dep_path in fs.dependencies:
                dep = path_map.get(dep_path)
                if dep:
                    visit(dep)
            order.append(fs)

        for fs in self.file_specs:
            visit(fs)
        return order


# ---------------------------------------------------------------------------
# Architect — produces ProjectSpec from user request
# ---------------------------------------------------------------------------

ARCHITECT_SYSTEM_PROMPT = """You are a senior software architect. Given a user request and optional research context, produce a comprehensive technical specification for the project.

Your specification must be detailed enough that SEPARATE developers (who cannot talk to each other) can each implement one file and have everything integrate correctly.

## Rules
- Choose `deliverable_type` from `python` or `web_app` from the requested user experience, never from a keyword rule.
- Python deliverables use Python and are operated through CLI/library/service semantics.
- Web app deliverables are browser-first and MUST use separate HTML/CSS/JavaScript files. For this initial capability, prefer dependency-free static web apps with localStorage when persistence is needed.
- `tech_decisions` is UI metadata: list only concise technology choices (for example `HTML/CSS/JavaScript`, `localStorage`). Put explanations and product behaviour in description, file specs, or acceptance contracts — never in `tech_decisions`.
- A web app MUST include index.html, styles.css, app.js, and tests/acceptance.json. It must be usable by opening the preview, not by printing a textual imitation to a console.
- Every function signature must include parameter types and return type
- Every data model must list all fields with types
- Dependencies between files must be explicit (what imports what)
- Set executable=false ONLY when the user explicitly requests a library, passive module, source-only deliverable, or otherwise explicitly asks for no runnable entry point
- Otherwise executable defaults to true and the entry point must be clear (which file to run, what command)
- When executable=true, entry_point MUST be present in file_specs, run non-interactively with no arguments, and print a meaningful demo/result (never silent exit 0)
- When executable=false, entry_point MUST be null and no artificial runner/demo may be added
- Every executable project MUST include at least one tests/test_*.py acceptance test that asserts the user-visible requested behavior, not merely imports or exit code
- Keep to 3-8 implementation files for most projects, plus acceptance tests. Don't over-engineer.
- Current year: {current_year}

## Output Format
Respond with ONLY a JSON object matching this schema:
{{
  "project_name": "short-kebab-name",
  "deliverable_type": "python|web_app",
  "interaction_mode": "cli|browser|library",
  "description": "One paragraph describing the project",
  "tech_decisions": ["technology or framework", "storage/runtime choice"],
  "data_models": [
    {{
      "name": "ClassName",
      "description": "What this model represents",
      "fields": [{{"name": "field_name", "type": "str", "description": "what it stores"}}],
      "methods": [{{"name": "method_name", "params": [{{"name": "param", "type": "str"}}], "returns": "bool", "description": "what it does"}}]
    }}
  ],
  "file_specs": [
    {{
      "path": "models.py",
      "purpose": "Defines data models for the application",
      "exports": [
        {{"name": "function_or_class_name", "params": [{{"name": "param", "type": "str"}}], "returns": "ReturnType", "description": "what it does"}}
      ],
      "data_models": ["ClassName"],
      "imports_from": {{}},
      "dependencies": [],
      "implementation_notes": "Detailed guidance on how to implement this file",
      "edge_cases": ["edge case 1", "edge case 2"]
    }},
    {{
      "path": "auth.py",
      "purpose": "Handles user authentication",
      "exports": [
        {{"name": "authenticate", "params": [{{"name": "username", "type": "str"}}, {{"name": "password", "type": "str"}}], "returns": "Optional[User]", "description": "Verify credentials"}}
      ],
      "data_models": [],
      "imports_from": {{"models.py": ["User", "get_db"]}},
      "dependencies": ["models.py"],
      "implementation_notes": "Use hashlib for password hashing, sessions stored in-memory dict",
      "edge_cases": ["empty password", "non-existent user", "concurrent sessions"]
    }}
  ],
  "executable": true,
  "entry_point": "main.py or index.html",
  "execution_strategy": "python main.py — starts HTTP server on port 8080"
}}

CRITICAL: The `data_models` field in file_specs is a list of model NAME STRINGS that reference the top-level data_models array. The top-level `data_models` defines the full schema; file_specs reference them by name."""


class ArchitectPhase:
    """Produces a ProjectSpec from a user request using LLM planning.

    Usage:
        architect = ArchitectPhase(llm_provider, model="...")
        spec = await architect.design(user_request, research_context={...})
        # spec is a ProjectSpec with full file specs, data models, interfaces
    """

    def __init__(self, llm_provider, model: str = None):
        """
        Args:
            llm_provider: LLM provider instance (must have chat_complete method)
            model: Model override for architect calls (Opus-class recommended)
        """
        self.llm_provider = llm_provider
        self.model = model

    async def design(
        self,
        user_request: str,
        research_context: Optional[Dict[str, Any]] = None,
    ) -> ProjectSpec:
        """Run the architect phase: produce a full ProjectSpec.

        Args:
            user_request: The user's original task description
            research_context: Optional dict of research results
                              (key=query, value=findings text)

        Returns:
            ProjectSpec with detailed file specs and data models.

        Raises:
            ValueError: If the LLM output can't be parsed into a valid spec.
        """
        raw_spec = await self._generate_spec(user_request, research_context)
        return self._parse_spec(raw_spec)

    async def _generate_spec(
        self,
        user_request: str,
        research_context: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Call the LLM to generate the raw specification JSON."""
        system = ARCHITECT_SYSTEM_PROMPT.format(
            current_year=datetime.now().year,
        )

        user_parts = [user_request]
        if research_context:
            user_parts.append("\n\n## Research Findings:")
            for query, findings in research_context.items():
                # Truncate findings to avoid blowing context
                text = findings if isinstance(findings, str) else str(findings)
                user_parts.append(f"\n### {query}\n{text[:1500]}")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        raw = await asyncio.wait_for(
            self.llm_provider.chat_complete(
                messages=messages,
                model=self.model,
                stream=False,
                max_tokens=8192,
                temperature=0.2,
            ),
            timeout=45,  # Fail fast to legacy planner if architect is too slow
        )

        return self._extract_json(raw)

    def _extract_json(self, raw: str) -> dict:
        """Extract JSON object from LLM output, handling code fences."""
        text = raw.strip()

        # Strip markdown fences
        if text.startswith("```"):
            first_nl = text.index("\n")
            text = text[first_nl + 1:]
            if "```" in text:
                text = text[:text.rindex("```")]
            text = text.strip()

        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Find outermost { ... }
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"Architect: could not parse spec JSON: {text[:300]}")

    def _parse_spec(self, raw: dict) -> ProjectSpec:
        """Parse raw JSON dict into a validated ProjectSpec."""
        # Parse top-level data models
        data_models = []
        model_map: Dict[str, DataModelSpec] = {}

        for dm_raw in raw.get("data_models", []):
            dm = DataModelSpec(
                name=dm_raw.get("name", "Unknown"),
                description=dm_raw.get("description", ""),
                fields=[
                    FieldDef(
                        name=f.get("name", ""),
                        type=f.get("type", "Any"),
                        description=f.get("description", ""),
                        default=f.get("default"),
                    )
                    for f in dm_raw.get("fields", [])
                ],
                methods=[
                    self._parse_function(m)
                    for m in dm_raw.get("methods", [])
                ],
            )
            data_models.append(dm)
            model_map[dm.name] = dm

        # Parse file specs
        file_specs = []
        for fs_raw in raw.get("file_specs", []):
            # Resolve data model references
            file_data_models = []
            for dm_ref in fs_raw.get("data_models", []):
                if isinstance(dm_ref, str) and dm_ref in model_map:
                    file_data_models.append(model_map[dm_ref])
                elif isinstance(dm_ref, dict):
                    # Inline data model definition (fallback)
                    file_data_models.append(DataModelSpec(
                        name=dm_ref.get("name", "Unknown"),
                        description=dm_ref.get("description", ""),
                    ))

            file_specs.append(FileSpec(
                path=fs_raw.get("path", "unknown.py"),
                purpose=fs_raw.get("purpose", ""),
                exports=[
                    self._parse_function(e)
                    for e in fs_raw.get("exports", [])
                ],
                data_models=file_data_models,
                imports_from=fs_raw.get("imports_from", {}),
                dependencies=fs_raw.get("dependencies", []),
                implementation_notes=fs_raw.get("implementation_notes", ""),
                edge_cases=fs_raw.get("edge_cases", []),
            ))

        deliverable_type = str(raw.get("deliverable_type") or "python")
        if deliverable_type not in {"python", "web_app"}:
            raise ValueError(f"Architect: unsupported deliverable_type {deliverable_type!r}")
        interaction_mode = str(raw.get("interaction_mode") or (
            "browser" if deliverable_type == "web_app" else "cli"))
        executable = raw.get("executable", True) is not False
        default_entry = "index.html" if deliverable_type == "web_app" else "main.py"
        entry_point = str(raw.get("entry_point") or default_entry) if executable else None
        implementation_paths = [spec.path for spec in file_specs
                                if not spec.path.startswith("tests/")]
        if executable and file_specs and not any(spec.path == entry_point for spec in file_specs):
            # Repair a structurally invalid LLM spec deterministically. The
            # dedicated worker will generate the missing executable adapter.
            file_specs.append(FileSpec(
                path=entry_point,
                purpose=("Browser application entry point" if deliverable_type == "web_app"
                         else "Executable, non-interactive project entry point"),
                dependencies=[spec.path for spec in file_specs],
                imports_from={},
                implementation_notes=(
                    "Wire the local CSS and JavaScript into an accessible, usable page."
                    if deliverable_type == "web_app" else
                    "Wire the project modules into a runnable demonstration. "
                    "Running with no arguments must print meaningful output "
                    "and must not call input()."
                ),
                edge_cases=(["keyboard navigation", "small viewport"]
                            if deliverable_type == "web_app" else
                            ["no command-line arguments", "stdin unavailable"]),
            ))
            implementation_paths.append(entry_point)

        if deliverable_type == "web_app":
            web_required = {
                "index.html": ("Semantic browser entry point", "Reference styles.css and app.js with relative URLs."),
                "styles.css": ("Responsive visual design", "Style every user-visible state and keyboard focus state."),
                "app.js": ("Browser interaction and state", "Implement the requested interactions without external dependencies."),
                "tests/acceptance.json": (
                    "Machine-readable user acceptance scenarios",
                    'Return JSON {"cases":[{"name":"...","assertions":["..."]}]} covering the requested browser behavior.'),
            }
            existing = {spec.path for spec in file_specs}
            for path, (purpose, notes) in web_required.items():
                if path not in existing:
                    file_specs.append(FileSpec(
                        path=path, purpose=purpose,
                        dependencies=[] if path != "index.html" else ["styles.css", "app.js"],
                        implementation_notes=notes,
                    ))

        if deliverable_type == "python" and executable and file_specs and not any(
                spec.path.startswith("tests/") and spec.path.endswith(".py")
                for spec in file_specs):
            file_specs.append(FileSpec(
                path="tests/test_acceptance.py",
                purpose="Acceptance tests for the user-visible requested behavior",
                dependencies=list(dict.fromkeys(implementation_paths)),
                imports_from={},
                implementation_notes=(
                    "Write deterministic pytest acceptance tests derived from the "
                    "user request. Assert meaningful domain output/state and reject "
                    "empty placeholders; do not merely test imports or exit code."
                ),
                edge_cases=["empty generated domain data", "placeholder-only output"],
            ))

        raw_project_name = str(raw.get("project_name") or "project").strip()
        # A project name is an identifier, never a path. Models sometimes
        # echo the selected project as a prefix, nesting a new project in it.
        project_name = Path(raw_project_name.replace("\\", "/")).name or "project"

        return ProjectSpec(
            project_name=project_name,
            description=raw.get("description", ""),
            tech_decisions=raw.get("tech_decisions", []),
            data_models=data_models,
            file_specs=file_specs,
            executable=executable,
            entry_point=entry_point,
            execution_strategy=raw.get("execution_strategy", ""),
            deliverable_type=deliverable_type,
            interaction_mode=interaction_mode,
        )

    def _parse_function(self, raw: dict) -> FunctionContract:
        """Parse a function/method definition from raw dict."""
        return FunctionContract(
            name=raw.get("name", "unknown"),
            params=raw.get("params", []),
            returns=raw.get("returns", "None"),
            description=raw.get("description", ""),
            raises=raw.get("raises", []),
        )
