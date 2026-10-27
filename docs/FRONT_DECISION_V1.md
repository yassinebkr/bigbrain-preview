# Front decision protocol — version 1

Branch: `feat/front-decision-v1`, based on approved research merge `0226a2a`
on local `main` (24 October 2026). Version 2, incremental structured-field
streaming, awaits user evaluation of this version.

## Research transition hardening (25 October)

The live failure opened a URL/unknown reference with an empty source registry.
The model's static action schema permitted this proposal; the runtime then
treated the reference rejection as a fatal exception. This was a protocol gap,
not an acquisition failure.

Research generation now receives available tools and exact question/source IDs
both in its context and native schema. Local preflight checks phase, references,
tool budgets, browser access eligibility, repetitions and claim evidence before
mutating counters or calling tools. Rejected proposals enter the observation
journal and consume existing action/time/token budgets. Two consecutive rejected
proposals stop collection with an explicit incomplete result. Successful recovery
does not weaken citation or independent-review requirements.

Offline regressions cover empty/invalid source references, recovery through
discovery and reading, unknown questions, fabricated citations, resource caps,
duplicate plans and native schema availability. These are protocol regressions,
not a claim that a live provider has completed the user's research.

The preceding timeout log showed 6.5 seconds for planning and no second decision
before the 90-second run deadline. UI elapsed time now interpolates locally at
one-second intervals and freezes for terminal/inactive results; server checkpoints
remain the authoritative measurements. Timeout diagnostics identify the phase
and preserve collected observations. No latency improvement is inferred from this.

No automatic provider/model switch or paid validation was performed.

## Decision and execution

Every model-driven front turn requests exactly one native
`bigbrain_front_decision` function result. Its closed root object contains one
`decision`, with a closed shape for one operation:

| Operation | Required input | Runtime effect |
| --- | --- | --- |
| `respond` | reply | Display the complete reply |
| `clarify` | reply | Display the question without launching work |
| `consult_memory` | tool and typed arguments | Perform one conversation-scoped consultation and continue the same turn |
| `delegate` | reply and autonomous objective | Route the validated work through the existing orchestrator |

A delegation may choose a direct researcher, taskboard, Python-file execution
or web-project execution route. Closed route variants tie each brain to its
specialist payload. The model supplies the research objective once. The runtime
maps this sole objective to the researcher's `query` and execution `user_request`;
the model's route payload only selects the research mode. Generic
code generation and compound work retain the existing orchestrator planning,
contract approval and verification flows. `test_changes` remains a proposal,
never an execution permission. The orchestrator remains the destination owner.

The front's production path never searches reply prose for task JSON. A JSON
example inside a `respond` reply cannot cause execution. The old parsing helper
is retained for compatibility tests, not used to dispatch a model-driven turn.
Plain provider text, incomplete JSON, extra fields, mixed operations and
contradictory research objectives fail local validation. The visible diagnostic
does not repeat provider bodies or historical model errors. Diagnostics are
recorded in `front.decision_failed`; validated operation metadata is recorded
in `front.decision` with the conversation and turn identifiers.

The model resolves a follow-up from the current conversation, preserving the
original constraints. It can consult memory and must clarify ambiguous targets.
No keyword detector chooses or rewrites the requested action. The schema
guarantees structural validity, not correct intent interpretation or factual
truth of a free-text reply; those remain live acceptance criteria.

## Dispatch and Atelier

Validated delegation creates `task.routing` with a new run ID and the initiating
conversation. The existing Atelier reducer follows that attempt. The task carries
the resolved execution objective in `user_request`, the exact conversational turn
in `user_message`, and the same session/run ownership throughout dispatch.

Checked bus dispatch requires a registered destination subscriber and valid
source authentication when HMAC is enabled. Its acceptance callback publishes
the chat acknowledgement after those checks and before target execution. Bus
acceptance establishes transport admission, not execution success. Subsequent
`task.received`, subtask and terminal events belong to the orchestrator/workers.
An exception during dispatch settles the created attempt with a correlated
`task.failed` event and an explicit user-facing failure. Target-handler execution
errors retain the bus/orchestrator's existing error-handling semantics.

Turn-local context variables prevent a concurrent conversation's decision from
authorizing another turn's dispatch. Stop is checked after provider completion
and memory reads, before publishing or delegating their results.

## Memory, provider transport and latency

At most three memory consultations precede a final decision; a fourth requested
lookup ends with an explicit limit. Existing session scope, fact source/revision
checks, timeout and 6,000-character result bound remain enforced. Lookup errors
are reported as errors rather than absence. Intermediate decisions and tool
results are not displayed as chat content or automatically appended to permanent
conversation history.

OpenAI-compatible and LiteLLM providers force one named function; Anthropic uses
one forced native tool; Codex receives the closed output schema through its
existing conversation-scoped adapter. All results undergo the same Pydantic
validation. Codex account binding, session reuse and compaction are unchanged.
The Anthropic adapter now retains all system messages instead of only the last
one, preserving the front instructions alongside memory/source context.

Version 1 uses `stream=False`, with a 4,096-output-token ceiling passed to the
existing provider adapter. It displays the reply after complete validation;
delegation acknowledgements also wait for checked transport admission. This
adds first-visible-text latency compared with streaming. It adds no separate
intent-classification call. Provider-specific reasoning policies remain intact.

## Verification and manual acceptance

Version 1 regression receipt:
`../tests/front-decision-v1-regression.xml` — 1,506 passed, 8 skipped.
The subsequently added provider/Stop/concurrent-delegation cases pass in the
24-test focused front suite. The final transport adjustment also passes the
10-test provider/OAuth suite. No UI source changed after the research merge;
its 128 UI tests and production build remain the applicable UI gate.

Offline checks use frozen HTTP/RPC responses and isolated user storage. They
cover native forced schema framing, historical failure text, literal routing
JSON, invalid/mixed decisions, sourced memory lookup/write, vision, conversation
isolation, Stop, unavailable destinations and rejected unsigned tasks. Provider
checks cover OpenAI-compatible, Codex, LiteLLM and Anthropic without account
traffic. Research's full pre-merge gate passed 1,489 Python tests with 8 skips,
plus 128 UI tests and the production build.

After restarting BigBrain and refreshing the UI:

1. Ask a bounded research question; verify the new attempt appears in Atelier.
2. In that same chat, ask to retry; verify the original objective survives and a
   new attempt is followed. A historical failure must not appear as its result.
3. Ask an ordinary question and an ambiguous follow-up; these must not launch
   unintended work.
4. Check a sourced personal-memory lookup, switch conversations and exercise
   Stop. Assess whether the wait before a complete reply warrants version 2.

No new paid probe or claim of successful live model intent resolution is made
by these offline checks. New branch merge remains subject to user approval.

## Live refusal and Atelier correction

The next user attempt reached the delegate operation but failed the original
local exact-string equality check between objective and research query. The
schema had asked the model to express the same intent twice. That duplication
has been removed from the model contract, rather than normalized heuristically.
Local diagnostics now validate the selected operation first, avoiding unrelated
union-variant error noise. The correction passes 112 targeted Python tests.

Research disclosures now reuse the existing Radix accordion and Framer Motion
components, with controlled expansion, reduced-motion support and hidden/inert
closed content. The Atelier work selector reuses its Radix menu with scoped
radio choices and readable status labels. Existing theme tokens and rounded
surfaces are preserved. Overview statistics, source domains and observed quote
blocks establish hierarchy; source transport metadata follows the evidence in
a closed technical disclosure. The expanded layout keeps the summary in the
left column while right-hand sections follow each other without a blank grid
row forced by summary height.

UI gate: 128 tests and production build pass. Browser inspection used real
components and production CSS with the existing isolated worker/bus replay,
not user data or a live model call. It covered overview, source evidence,
expansion, radio-menu keyboard selection and retained attempt selection.
Receipts/screenshots: `../tests/front-decision-polish/browser/`.
