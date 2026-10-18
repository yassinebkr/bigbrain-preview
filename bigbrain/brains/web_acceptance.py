"""Versioned acceptance-document boundary for generated static web projects.

These are scenarios, not executed browser tests. Parsing this document must
never be reported as proof that its behavioral assertions passed.
"""

from typing import Any


ACCEPTANCE_CONTRACT = '''tests/acceptance.json must be JSON with this exact schema:
{"schema_version":1,"cases":[{"name":"descriptive scenario","steps":["user action"],"assertions":["observable expected result"]}]}
cases must be a non-empty array. Each case needs a non-empty name and a
non-empty assertions array. steps is optional. Every steps/assertions item
must be a non-empty string or object. Describe the actual generated UI.
This file specifies scenarios; do not claim browser tests have been executed.'''


def normalize_acceptance(document: Any) -> dict:
    """Validate v1 and explicitly adapt pre-v1 documents at the boundary."""
    if not isinstance(document, dict):
        raise ValueError("acceptance document must be an object")
    version = document.get("schema_version")
    if version is not None and (type(version) is not int or version != 1):
        raise ValueError("unsupported acceptance schema_version (expected 1)")
    keys = [key for key in ("cases", "tests", "acceptanceCriteria") if key in document]
    if len(keys) != 1 or (version == 1 and keys != ["cases"]):
        raise ValueError("acceptance document must define one cases array (legacy: tests or acceptanceCriteria)")
    cases = document[keys[0]]
    if not isinstance(cases, list) or not cases:
        raise ValueError("acceptance cases must be a non-empty array")

    def items(value: Any, label: str, required: bool = False) -> list:
        if not isinstance(value, list) or (required and not value):
            raise ValueError(f"{label} must be a {'non-empty ' if required else ''}array")
        if any(not ((isinstance(item, str) and item.strip())
                    or (isinstance(item, dict) and item)) for item in value):
            raise ValueError(f"{label} items must be non-empty strings or objects")
        return value

    normalized = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index + 1} must be an object")
        name = case.get("name") or (case.get("title") if version is None else None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"case {index + 1} needs a non-empty name")
        steps = items(case.get("steps", []), f"case {index + 1} steps")
        assertions = case.get("assertions")
        if assertions is None and version is None:
            assertions = case.get("expectedResults", steps)
        assertions = items(assertions, f"case {index + 1} assertions", required=True)
        normalized.append({"name": name.strip(), "steps": steps, "assertions": assertions})
    return {"schema_version": 1, "cases": normalized}
