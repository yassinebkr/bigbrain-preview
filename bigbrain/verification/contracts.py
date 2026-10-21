"""Contract drafting for the pre-implementation approval flow.

Pattern shopifast-local: before the agent writes code, it proposes
checkable contracts in plain language; the user approves them and the
approval is traced in the DesignSpec (evidence repository).

The contracts themselves are drafted by the LLM — deterministic code
only parses and validates them. No keyword matching anywhere.
"""

from __future__ import annotations

import json
import asyncio
import os
from typing import Any, List, Optional

# Subtask types that WRITE code/files — those need contract approval
# before they run. Read-only or conversational types never pause.
CODEGEN_TYPES = frozenset({
    "maintain_project",
    "generate_and_execute",
    "write_project_file",
    "write_web_file",
    "batch_write_files",
    "assemble_and_run",
    "assemble_and_preview",
    "edit_file",
    "compound",
})

CONTRACTS_PROMPT = """You are drafting acceptance contracts for a coding task.
Given the user's request, write 2 to 4 contracts: concrete, checkable
statements about what the delivered work must satisfy. Use the SAME
LANGUAGE as the user's request. Each contract is one short sentence that
can be verified by running code or checking the filesystem.

Rules:
- No vague contracts ("works well", "good quality")
- Only what the output can prove: file existence, printed values,
  program behaviour, structure
- The architecture context below is authoritative. Do not invent or change its stack.
- Respond with EXACTLY a JSON array of strings, nothing else

Example:
User request: "écris un script fibonacci.py qui affiche les 10 premiers nombres de la suite"
Response: ["le fichier fibonacci.py existe dans le projet courant", "l'exécution du script affiche exactement 10 nombres", "le premier nombre affiché est 0"]
"""


def stack_contract(project_spec: Any) -> Optional[str]:
    """Render the LLM-selected ProjectSpec stack as an explicit contract."""
    if project_spec is None:
        return None
    deliverable = str(getattr(project_spec, "deliverable_type", "") or "").strip()
    interaction = str(getattr(project_spec, "interaction_mode", "") or "").strip()
    entry_point = str(getattr(project_spec, "entry_point", "") or "").strip()
    strategy = str(getattr(project_spec, "execution_strategy", "") or "").strip()
    decisions = [str(item).strip() for item in
                 (getattr(project_spec, "tech_decisions", None) or [])
                 if str(item).strip()]
    parts = []
    if deliverable:
        parts.append(f"livrable {deliverable}")
    if interaction:
        parts.append(f"interaction {interaction}")
    if entry_point:
        parts.append(f"point d’entrée {entry_point}")
    if decisions:
        parts.append("technologies " + ", ".join(decisions))
    if strategy:
        parts.append("validation " + strategy)
    return "[Stack] " + " · ".join(parts) if parts else None


async def draft_contracts(llm_provider: Any, user_request: str,
                          project_spec: Any = None) -> List[str]:
    """Ask the LLM for checkable contracts; empty list if unavailable."""
    architecture = stack_contract(project_spec)
    proposed = list(getattr(project_spec, "acceptance_contracts", []) or [])
    if proposed:
        return ([architecture] if architecture else []) + proposed
    if not user_request.strip():
        return [architecture] if architecture else []
    if not llm_provider:
        return [architecture] if architecture else []
    try:
        response = await asyncio.wait_for(llm_provider.chat_complete(
            messages=[
                {"role": "system", "content": CONTRACTS_PROMPT},
                {"role": "user", "content": (
                    user_request[:2000]
                    + (f"\n\nArchitecture context:\n{architecture}" if architecture else "")
                )},
            ],
            stream=False,
            max_tokens=768,
            temperature=0.1,
        ), timeout=20)
    except Exception:
        return [architecture] if architecture else []
    contracts = parse_contracts(str(response))
    if architecture:
        contracts = [architecture, *[item for item in contracts
                                     if not item.lstrip().startswith("[Stack]")]]
    return contracts


def parse_contracts(response: str) -> List[str]:
    """Extract a JSON array of contract strings from an LLM response."""
    text = (response or "").strip()
    # Balanced-bracket scan: the array may sit in prose or code fences.
    start = text.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i + 1])
                        if (isinstance(parsed, list)
                                and all(isinstance(c, str) for c in parsed)):
                            return [c.strip() for c in parsed if c.strip()]
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("[", start + 1)
    return []


def approval_flow_enabled() -> bool:
    """Kill switch: BIGBRAIN_CONTRACTS=0 disables the approval gate."""
    return os.environ.get("BIGBRAIN_CONTRACTS", "1") != "0"


def plan_needs_approval(subtasks: List[Any]) -> bool:
    """True if any subtask writes code and should wait for contracts."""
    return any(
        (getattr(st, "payload", None) or {}).get("type") in CODEGEN_TYPES
        for st in subtasks
    ) and bool(subtasks)


def build_proposal_spec(user_request: str,
                        contracts: Optional[List[str]]) -> Any:
    """DesignSpec for the proposal (design_id derives from the request,
    so the RunGate links every run manifest back to the SAME design)."""
    from .evidence import DesignSpec
    import hashlib

    design_id = "task-" + hashlib.sha256(
        user_request.encode("utf-8")).hexdigest()[:16]
    if not contracts:
        contracts = [f"the delivered code answers the request: {user_request.strip()[:120]}"]
    return DesignSpec(
        design_id=design_id,
        name=user_request.strip()[:60] or "unnamed request",
        user_request=user_request,
        contracts=list(contracts),
    )
