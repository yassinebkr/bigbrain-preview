# Declared Python execution

24 October 2026 — follow-up to verified project delivery.

PythonBrain executes finite Python CLI and library checks. WebAppBrain owns
browser application generation and preview. The two can ultimately participate
in one full-stack project; specialist choice is not inferred from source imports.

## Current contract

The architect declares deliverable_type and interaction_mode. The proposal
records execution.interaction_mode in its immutable approved DesignSpec.
Python assembly checks that approval before execution, carries it through the
added delivery subtask, and binds execution metadata into the delivery receipt.
A worker cannot switch an approved CLI to a service, a browser application to
Python, or the executable/library declaration. Changed intent needs new approval.

Old approvals without execution metadata retain finite CLI/library semantics.
Unbound legacy assembly defaults to CLI or an explicitly non-executable library;
it no longer scans comments, strings, tests or imports to decide what to launch.

The former Python preview launcher was removed: no automatic port rewriting,
no installation of packages guessed from imports, no long-lived server started
by matching Flask/FastAPI/websocket vocabulary. Web preview diagnostics now use
the actual WebAppBrain registry.

## Explicit limitation

Python interaction_mode=service remains a valid declaration for an explicitly
requested backend/service. The finite runner reports environment_blocked and an
incomplete result before launching or editing files. A declared service does not
silently become a CLI or a browser deliverable. Shared repair does not blindly
patch an unavailable runtime capability.

This deliberately removes the previous heuristic preview behavior. It does not
add a replacement HTTP hosting/validation mechanism or claim full-stack support.
The proposed temporary HTTP probe was withdrawn before validation/commit.
Next discussion: Python backend + React frontend coordination, ownership of API
contracts, environments, process lifecycle and integration tests, followed by the
previously planned observable ResearchBrain/Web Search milestone.

Validation covers web-looking CLI source actually running unchanged, approval
mode mismatches, old approvals, web-specialist boundaries, explicit service
blockage, receipt rejection after intent changes, and preview diagnostics.
Project repair and delivery gates retain their existing tests and semantics.

Validation: broad Python suite 1,338 passed, 9 existing warnings, 166.90 s.
Two later regression additions and the final approval guard are covered by the
99-test focused run (all passed, 4 deprecation warnings). The broad run is not
claimed as a fresh 1,340-test execution of the final revision. No UI source
changed and no new paid model campaign was run. git diff --check passed.
