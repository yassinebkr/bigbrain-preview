# Drawing 42 retained status

## Relocated artifact storage

The published artifacts matched their recorded hashes and sizes, but their reads
were rejected because the configured CAD store itself is a symbolic link to the
cold disk. The artifact guard compared the unresolved configured path with its
resolved path and treated the intended whole-store relocation as a replacement.

`CadStore` now pins its configured root to the resolved location at initialization.
Document links, artifact links, hardlinks, changed sizes, changed bytes and
cross-session access remain rejected. Retargeting the configured link after
initialization leaves that store instance bound to its original location.
Direct reads of the published preview, native document, STEP and STL all pass
their normal integrity checks through the relocated configuration. No artifact
metadata, file contents or model-call counters were changed.

## Published-result reconciliation

The reported 64-check error remained visible after publication because CadPanel
rendered the failed task's retained CAD state. No new inference occurred: the
ledger remained at 82 requests and the canonical delivery contained 66 passed
checks. Previous verification covered publication and schema capacity; it missed
this terminal-task presentation path.

The owned-document view now explicitly reports delivery status. For an inactive
task, the panel reads a separately published delivery and validates its document,
revision, native hash and passed check hashes before displaying it. An incomplete,
cross-document, older or inconsistent result is rejected. The task's terminal
history remains unchanged; a label distinguishes the published result from the
earlier attempt. Nine panel tests pass, including this reconciliation and the
existing terminal-event guard.

## Offline measurement and delivery

The retained inspection was evaluated against revision 14, native hash
`3732cfdfc9cacb90adfe4a33e683301a76969abb4b9d580ef449a09c9bb866e8`,
without inference. The native and STEP hashes were checked before evaluation;
the active checkpoint and call ledger remained unchanged.

The original inspection passed 62/66 checks. Four whole-axis empty-line checks
encountered legitimate remote elbow material beyond the tested flange. Their
original results remain under `revision-14/offline-inspection/`. The local
through-hole obligation concerns the flange thickness: entry Z=0..50 and outlet
X=360..410. These bounds derive from the confirmed flange thickness (50),
end-to-tangent distance (150) and centerline radius (260), in the recorded native
coordinate frame. All eight through-hole probes were consistently scoped to
their respective flange; other checks remained unchanged.

`CadSection.empty_span_mm` now supports local empty-through checks. It requires
empty targets, ordered finite bounds and no legacy dimension bindings. It retains
full-axis intervals in its diagnostic and continues to detect obstruction inside
the local span. Tests preserve the original whole-line behavior and check partial
and full local obstruction. Scoped probes cannot replace raw dimension probes.

The corrected inspection passes 66/66 checks. Its complete plan, derivation,
measurements and original remote intervals are retained under
`revision-14/scoped-inspection/`. Revision 14 was published through `CadDelivery`
and `CadStore.publish`; the stored view round-trips all 66 checks and a current
preview. The historical failed task remains part of the conversation history.
Publication does not rewrite its terminal event.

The sections/requirements/capacity/contracts suite passed 89 tests before four
additional invalid-scope cases were added. The subsequent sections/capacity/
integration/workflow suite passes 58 tests. Eight CAD panel tests pass, including
rendering all 66 checks. No new model calls were consumed; the ledger remains at
82 requests. Actual browser presentation has not been observed in this session.

## Inspection-capacity diagnosis

The four-call batch started at cumulative request 79. Request 80 completed the
construction transition. Requests 81 and 82 each proposed 64 inspection checks:
3 global criteria, 16 cylinders, 12 sections, 14 vertices and 19 requirement
measurements. The runtime added design-quality and cut-safety, then rejected 66
against its shared 64-check limit. The inspection prompt had explicitly allowed
64 authored checks. Its automatic formatting retry repeated the same mismatch.

The authored capacity remains 64. Delivery and frontend records now reserve two
additional slots for the mandatory runtime checks. All existing checks, source
bindings, tolerances and delivery gates remain required. The exact retained
response from request 82 passes proposal preflight and requirement precision
validation offline. The capacity/contracts/requirements suite passes 67 tests.

For continuations with stop-on-new-error enabled, inspection proposal validation
now also stops before its automatic model retry. The batch remains at request
82 with one authorized request remaining. No live request was issued while
diagnosing this mismatch. Actual measurement execution remains pending.

## Retained response replay and recovery actions

Decision 97 was replayed through the standard construction driver after local
schema tests passed. Its definition, executable identity, execution authorization,
base checkpoint and execution operation were checked before execution. All normal
workflow, topology, removal-safety, capacity and intermediate acceptance checks
remained active. The outlet C10 chamfer was accepted as checkpoint
`21fdca8cfad5493c8bdb801612fa59e8`. Both named C10 features occur in its native history.

The replay used a provider that raises on any inference request. The cumulative
ledger remained byte-identical and the controller remained at 98 decisions.
The user's earlier conclusion attempt had already consumed request 79, leaving
five of the original 84 requests. No inference was issued during this follow-up.
Whole-part inspection remains pending; the candidate has no delivery validation.

Recovery now records a typed category and checkpoint. The UI fetches the action
from an owned-document endpoint; the resume endpoint rechecks its availability.
Unknown, stale, budget-limited, geometry-failure and response-validation states
require diagnosis or explicit intervention. Cancellation and provider interruption
can resume their retained state, while completed construction targets inspection.
Diagnostic prose does not choose these actions. The retained-response replay is
an explicit operator action; the UI does not execute it automatically.

The replay/recovery/controller/execution/resource/context/integration suites pass
82 tests. A subsequent controller/resource/recovery run passes 52 tests after the
typed budget exception change. The CAD panel's seven tests and production build
pass. UI browser observation remains unavailable in this session; these results
describe native replay, automated tests and compilation.

The earlier sections below preserve the intermediate chronology.

## Follow-up: descriptive obligation validation

The user-triggered continuation reached 78 cumulative requests. The inlet C10
chamfer was accepted. The outlet C10 proposal was rejected before native execution:
its pending-verification description contained 190 characters, while the field
used the 160-character native identity type.

Execution-group obligations now accept descriptive strings of 1–1000 characters,
with the existing 64-item limit. Native identity limits remain unchanged. The
exact retained response validates with this schema. The execution, controller,
resource and context suites pass 53 tests; `git diff --check` passes. This change
has consumed no model requests and has executed no new geometry.

The controller has reached decision 97, the construction-share boundary. Six
model requests remain reserved for conclusion and inspection. Completing the
outlet chamfer requires a controlled replay of the retained proposal against its
unchanged base checkpoint, with the normal execution checks. That replay remains
pending; no call counters or reserve boundaries have been changed. The running
server also requires a reload before it uses the updated schema.

The historical status below describes the earlier handoff.

## Candidate and remaining work

The retained document is `d4f8d16c0e884319b9df205f76f19943`. Its current accepted
head is `bf220612c33f469b8bf1f8f516f775b0`, containing both R10 junction fillets,
the continuous bore, eight through holes and eight counterbores. The two C10
mouth chamfers and final independent inspection remain pending.

The campaign ledger contains 76 requests, including the previous provider
usage-limit rejection. Eight requests remain within the existing 84-request
cumulative ceiling. No new inference was issued during this follow-up.

## Conclusion reserve correction

The controller previously rejected all decisions once the construction share
was consumed, including the decision to request independent inspection. The
reserve now permits a dedicated finalization phase with exactly two decision
types: `complete` and `blocked`.

This phase is charged to the existing inspection/conclusion reserve. Geometry
mutation, revision and tool requests are rejected by a separate decision schema
before native execution. `complete` transfers the candidate to the existing
whole-part inspection; delivery still depends on those checks. The total call
ceiling, confirmed dimensions, tolerances and construction allowance remain
unchanged.

The resource/controller/context suite passes 41 tests, including native replay,
restart persistence, total ceilings, finalization phase accounting and rejection
of attempted mutation from the reserve. `git diff --check` passes.

## Live handoff

The isolated server on port 3134 was restarted with the same candidate, original
SolidCraft executable and cumulative ledger. The browser tool refused authority
to access that page. No alternate browser surface or indirect resume request was
used. The next live step requires the user to select **Reprendre le travail
conservé** in the existing interface.

The retained candidate remains incomplete. Broader project architecture discussion
is scheduled after this bounded continuation; no new drawing campaign has begun.
