"""Versioned acceptance-document boundary for generated static web projects.

These are scenarios, not executed browser tests. Parsing this document must
never be reported as proof that its behavioral assertions passed.
"""

from typing import Any

ACCEPTANCE_CONTRACT = """tests/acceptance.json MUST use executable browser schema v2:
{"schema_version":2,"cases":[{"name":"loads","steps":[],"assertions":[{"op":"visible","selector":"main"}]}]}
Each case starts on index.html in a fresh browser context.
steps: {"op":"click","selector":"..."}, {"op":"fill","selector":"...","value":"..."},
{"op":"check","selector":"..."}, {"op":"uncheck","selector":"..."},
{"op":"select","selector":"...","value":"..."}, {"op":"press","selector":"...","value":"Enter"},
{"op":"reload"}, {"op":"viewport","width":375,"height":812}.
assertions: {"op":"visible","selector":"..."}, {"op":"text","selector":"...","value":"substring"},
{"op":"text_equals","selector":"...","value":"exact visible text"},
{"op":"count","selector":"...","value":3}, {"op":"checked","selector":"...","value":true},
{"op":"value","selector":"...","value":"..."}, {"op":"storage_equals","key":"...","value":"raw localStorage string"},
{"op":"no_overflow"}. Assertions may also be placed between steps to check state before/after reload.
Only these operations are supported. No prose strings, arbitrary JS, URLs or Python.
Use real selectors matching your HTML/JS. Include meaningful interaction cases.
Use text_equals for counters and exact state labels; text checks a substring.
If the app saves state, exercise a change then reload and check the restored UI.
At most 20 cases, 40 steps and 40 assertions per case. Non-empty assertions required.
The gate automatically checks main visibility, JS/console errors and failed local assets.
Do not claim execution: BigBrain will execute these scenarios independently."""

STEP_OPS = {"click", "fill", "check", "uncheck", "select", "press", "reload", "viewport"}
ASSERT_OPS = {"visible", "text", "text_equals", "count", "checked", "value", "storage_equals", "no_overflow"}


def _executable_cases(document: dict) -> dict:
    cases = document.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError("browser cases must contain 1 to 20 scenarios")
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("name"), str)
            or not case["name"].strip()
        ):
            raise ValueError("browser case needs a non-empty name")
        for field, allowed in (("steps", STEP_OPS | ASSERT_OPS), ("assertions", ASSERT_OPS)):
            operations = case.get(field, [])
            if (
                not isinstance(operations, list)
                or len(operations) > 40
                or (field == "assertions" and not operations)
            ):
                raise ValueError(f"browser {field} must be an array of at most 40 operations")
            for operation in operations:
                if not isinstance(operation, dict) or operation.get("op") not in allowed:
                    raise ValueError(f"unsupported browser operation in {field}")
                op = operation["op"]
                if op not in {"reload", "viewport", "storage_equals", "no_overflow"}:
                    if (
                        not isinstance(operation.get("selector"), str)
                        or not operation["selector"].strip()
                    ):
                        raise ValueError(f"{op} needs a selector")
                if op in {"fill", "select", "press", "text", "text_equals", "value", "storage_equals"}:
                    if not isinstance(operation.get("value"), str):
                        raise ValueError(f"{op} needs a string value")
                if op == "storage_equals" and not isinstance(operation.get("key"), str):
                    raise ValueError("storage_equals needs a key")
                if op == "count" and (
                    type(operation.get("value")) is not int or operation["value"] < 0
                ):
                    raise ValueError("count needs a non-negative integer")
                if op == "checked" and type(operation.get("value")) is not bool:
                    raise ValueError("checked needs a boolean")
                if op == "viewport" and any(
                    type(operation.get(k)) is not int or not 240 <= operation[k] <= 1920
                    for k in ("width", "height")
                ):
                    raise ValueError("viewport dimensions must be between 240 and 1920")
    return {"schema_version": 2, "cases": cases}


def normalize_acceptance(document: Any) -> dict:
    """Validate v1 and explicitly adapt pre-v1 documents at the boundary."""
    if not isinstance(document, dict):
        raise ValueError("acceptance document must be an object")
    version = document.get("schema_version")
    if type(version) is int and version == 2:
        return _executable_cases(document)
    if version is not None and (type(version) is not int or version != 1):
        raise ValueError("unsupported acceptance schema_version (expected 1)")
    keys = [key for key in ("cases", "tests", "acceptanceCriteria") if key in document]
    if len(keys) != 1 or (version == 1 and keys != ["cases"]):
        raise ValueError(
            "acceptance document must define one cases array (legacy: tests or acceptanceCriteria)"
        )
    cases = document[keys[0]]
    if not isinstance(cases, list) or not cases:
        raise ValueError("acceptance cases must be a non-empty array")

    def items(value: Any, label: str, required: bool = False) -> list:
        if not isinstance(value, list) or (required and not value):
            raise ValueError(f"{label} must be a {'non-empty ' if required else ''}array")
        if any(
            not ((isinstance(item, str) and item.strip()) or (isinstance(item, dict) and item))
            for item in value
        ):
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
