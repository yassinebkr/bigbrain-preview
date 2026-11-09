# Conversational CAD qualification

This cycle extends `feat/cad-drawings` to natural-language requests, sketches,
dimensioned drawings and photographs supplemented by user measurements.

## Parametric workflow prerequisites

Before resuming drawing 117, qualify the native capabilities, enforce design
intent and prove coherent parameter edits on saved/reopened models. See
[Parametric CAD workflow](CAD_PROFESSIONAL_WORKFLOW.md) for measured capabilities,
the runtime sequence, qualification tests and remaining platform limits.

The sketch checkpoint implementation is committed as `19a272d` on
`feat/cad-drawings`. Phase 2 measurement qualification and its reference-solid
results are recorded in [CAD measurement qualification](CAD_MEASUREMENT_QUALIFICATION.md).
The reference sections satisfy the 0.05 mm nominal gate. Independent analytic
STEP inspection resolves cylinder radius/axis and volumetric precision on the
reference solids. SolidCraft's face `exact` flag refers to naming history;
the runtime uses independently inspected analytic surfaces for acceptance.
The next recorded probe applies these methods to drawing 117.

The subsequent frontend resume produced revision 5 with 54/54 passing checks.
One construction repair call took 20.375 seconds. A disposable parameter-edit
check changed length to 180 mm while preserving solved sketches and active
history. The evidence, provider choices and retained R25/H8 limits are recorded
in the measurement qualification report. Windows native qualification remains open.

### Second drawing probe: drawing 83

The next frontend probe used the user-supplied drawing 83 in a new conversation.
The front requested a higher-resolution source without identifying a specific
unreadable annotation. A follow-up asked it to identify the uncertain label and
local feature; the decision cycle timed out at 120 seconds. Neither turn
dispatched CAD construction. This probe remains incomplete and establishes a
reading/decision-path issue before any conclusion about modeling capability.

The uploaded PNG and the user's original JPEG both measure 474 × 670 pixels.
The application sends original image bytes through native Codex image inputs;
no resize was found in that path. A generic resolution request does not establish
which annotation is unavailable. Future clarification must identify the label,
view and affected feature and preserve the dimensions already read.

Evidence: `tests/cad-capability-live-20261102/drawing83-initial-result.png` under
the external qualification workspace. The four subsequent user-supplied drawings
are retained there as drawing42.png, pipe-with-flange.png, drawing90.png and
rectangular-elbow.png. They define the next complex-part qualification campaign.

## Current recovery plan — 2 November 2026

Objective: deliver drawing 117 through the normal BigBrain frontend workflow,
then qualify the same construction and verification mechanism on other parts.
The following four phases define the proposed implementation sequence. The
earlier phase table and execution records below describe existing work.

The user contract fixes the part requirements before construction. Construction
commands and measurement procedures can be corrected against those requirements
without repeating approval of unchanged dimensions. Changes to requirements,
design assumptions or acceptance tolerances require a new user decision.

### 1. Separate requirements from implementation

Keep a versioned definition of dimensions, features, source references, user
answers, the chosen R25 profile and the H8 qualification limits. Each requirement
has a stable identifier. Present dimensions, holes, recesses, chamfer, editable
model and expected exports in a readable contract.

Gate: drawing 117 has a complete definition and understandable contract. An
incorrect measurement expression produces a technical diagnostic while the
authoritative definition remains available for correction.

### 2. Prepare construction and verification

The specialist prepares the SolidCraft recipe. Preflight collects all detectable
command and measurement errors into one diagnostic before requesting correction.
Provide runtime calculations for common checks: diameter from radius, depth
between faces, axis position and angle between surfaces. The specialist selects
the relevant geometry; runtime checks validate those selections and calculations.

Record the verification obligations for every requirement in the definition.
Prepare surface selection and sampling against the constructed candidate, using
its native topology and recorded geometry. The inspection stage receives the
confirmed definition, construction recipe and captured revision identity.
An unavailable measurement capability must produce an explicit limitation before
execution. Preserve measurement provenance and independent expected values.

Gate: regression cases cover self-subtraction, incompatible coordinate axes,
missing angular checks and offset samples bound to exact coordinates across
multiple geometries. Preflight reports the applicable errors together.

### 3. Construct, inspect and repair within bounds

```text
versioned definition -> user contract -> construction and check preparation
                                                |
                                                v
                       construct -> inspect -> measure -> diagnose
                            ^                                |
                            |________ bounded repair ________|
                                                |
                                    all required evidence passes
                                                v
                                     editable model + exports
```

Inspect actual candidate faces and sections to assemble revision-bound evidence.
Expected values continue to come from the confirmed definition. Correct an
invalid measurement procedure, repair a reproduced geometry defect, and ask a
user question when a design ambiguity prevents progress. Procedure corrections
must preserve requirements and acceptance thresholds; a failing measurement
cannot be removed solely to obtain a passing result.

Budget exhaustion leaves an incomplete result with its cause and evidence.
Gate: drawing 117 is constructed and checked, the R25 assumption is visible,
and every requirement lacking evidence remains explicitly unresolved.

### 4. Qualify the workflow and close the branch

Fix the campaign cases before execution:

| Case | Required evidence |
| --- | --- |
| Drawing 117 through the frontend | Complete contract, native geometry, local checks, editable model and exports |
| A second part combining a hole, depth and chamfer | The same mechanism succeeds with different geometry |
| Deliberately incorrect geometry | Relevant checks reject the defect and retain the diagnostic |
| An ambiguous request | A precise clarification preserves the acquired definition |
| Cancellation or exhausted budget | The Atelier displays the terminal state and retained evidence |

Closure gate: the defined user workflows pass, injected defects are detected,
remaining limits are documented, and CI passes on the merge candidate. Merge
still requires the user's explicit instruction. Existing source continuity,
conversation isolation and portability requirements remain applicable.

### Deferred beyond this recovery

- General interpretation of complex photographs. Existing photograph-plus-user-
  measurement support remains part of the wider conversational CAD scope.
- Certification of manufacturing tolerances and fits, including H8. The current
  trial preserves the annotation and checks nominal geometry.
- A visual redesign of the Atelier. This recovery includes the status, evidence
  and assumption display needed to use and assess the CAD workflow.

The existing Windows native qualification and older-component portability
backlog remain tracked in `PORTABILITY.md`. This recovery adds no portability
exception. The earlier successful language-only and image-plus-measurements
qualification obligations remain open where the recorded evidence is incomplete.

### Current campaign

### Continuation checkpoints

The Atelier can explicitly resume a failed CAD operation from its confirmed
contract. The continuation record binds the conversation, exact contract digest,
document identity and last validated construction or inspection recipe. A resumed
operation creates a new orchestrated run and retains the original confirmation.
Superseded contracts, another conversation and already delivered documents are
rejected. A document execution lock prevents concurrent native work.

Native geometry is regenerated locally from the retained recipe. Native measures
and acceptance observations are collected again for the new captured revision.
Inspection procedures can be retained; their previous measurement results remain
historical evidence. An interrupted inspection can resume without front-brain or
construction-generation calls.

The 2 November continuation trial recovers the unchanged construction response
from call four of the earlier campaign, tied to its original confirmed contract.
This recovery is recorded as an assisted migration of historical trial data. The
live continuation uses the normal Atelier action. Three additional Sol 6.1 low
calls are authorized, recorded separately in `calls-resume-20261102.json`.

The campaign transport uses its remaining cumulative allowance for each call.
The confirmed worker execution deadline and user cancellation remain effective.

Continuation outcome: three specialist calls consumed 122.775 seconds, with zero
front-brain calls. The first two assembled and corrected inspection procedures.
The third repaired misplaced holes and extrusion directions against the native
coordinate frame. Reverification initially passed 53 of 54 checks. The remaining
analytic Ø80 observation was reported as a failure because unrelated exact
coaxial faces were available while the matching R40 surfaces carried
`exact: false`. The classifier now records that situation as inconclusive and
keeps the target measurement empty. Approximate geometry remains unqualified.

A final zero-inference continuation regenerated the repaired candidate and
reported 51 passed checks, zero reproduced failures and three inconclusive checks:
the Ø80 analytic surface plus its two dependent position checks. The common cause
is the unavailable qualified analytic observation. The editable native candidate,
STEP/STL exports, inspection plan and evidence are retained under document
`f7d3392ade104c1085458a7f4cbd61c0`, revision four. Delivery remains blocked.
An independent geometric measurement of that feature is the next qualification
step. The second live part and branch closure remain pending.

Regression evidence: 166 CAD/native-adapter tests pass, followed by a passing
13-test surface-observation recheck. The frontend has 163 passing tests and a
successful build. The full backend run recorded 2,245 passes, eight optional skips
and two timing-sensitive failures; both failing tests passed in an isolated
rerun. A clean full-suite result on the final tree remains open.

### Earlier campaign allowance

The 2 November continuation has an independent allowance of eight Codex Sol 6.1
low calls and 480 seconds of cumulative inference. Its ledger is
`calls-20261102.json` in the existing isolated drawing-117 evidence directory.
The preceding ledger retains 22 calls and 1,016.510 seconds. Historical status
paragraphs below describe earlier checkpoints.

The frontend continuation proposed a definition contract without a separate CAD
planning call. After confirmation, the worker entered construction planning.
The current inspection-boundary correction retains the construction repair
ceiling and rejects inspection output attempting to change that ceiling.

The campaign stopped after seven recorded calls and 411.957 seconds. The first
construction response omitted sketches from its timeline inventory. Construction
preflight now permits one diagnostic-led correction within the enclosing budget.
The next candidate reached native execution; the quality gate incorrectly compared
a native angular value in radians with a drawing value in degrees. Angular
provenance now converts that observed value to degrees before comparison. A native
regression covers both the matching 45-degree value and a genuinely wrong target.
Coordinate-expression profiles are accepted when the native dependency graph
connects the sketch to declared parameters. A native edit test verifies this path.

The final frontend retry reached its 120-second deadline. No further task was
dispatched. Drawing 117 remains unvalidated, and the second live part remains
pending. The remaining one call and 68.043 seconds cannot cover a new complete
frontend, construction and inspection sequence. All 162 CAD/native-adapter tests
pass after these corrections; this local result leaves the live gate open.

### Evidence motivating the revision

The latest frontend continuation reached a complete proposed recipe and stopped
at contract validation before native construction. Offline inspection found
endpoint samples of 25.000075 mm linked to exact 25 mm coordinates, a counterbore
depth expression yielding 0 instead of 5 mm, a chamfer expression yielding -20
instead of 10 mm, and a missing 45-degree binding. These findings motivate
aggregate diagnostics and runtime measurement calculations.

The campaign has consumed 16 calls and 705.027 seconds of inference. Its current
authorization allows 17 calls and 886.8506304370048 seconds in total. One call
remains; a fresh front-to-specialist round requires two. Drawing 117 remains
unvalidated. The persistent evidence and current ledger are in
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/`.

## Earlier phases and gates

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 1. Source continuity | Conversation-owned image inventory, original hashes, persisted attachment references and versioned clarification dossier | Restart/reload retains sources and answers; another conversation receives neither |
| 2. Progressive definition | Acquired/unresolved dimensions, literal user quotations, explicit contradiction handling and one authoritative drawing specification | Resolved definition reaches the recipe; critical omissions, changed sources and unsupported measurements block publication |
| 3. Interface | Expandable thumbnails in composer/history, design dossier in the Atelier, acquired dimensions and current question | Inspect the image and pending question after reload; review the contract through one Atelier action |
| 4. Qualification | Offline boundary cases, native geometry and bounded frontend probes | Record outcomes, defects, costs where available and remaining coverage; inspect CI before proposing a merge |

## Data flow

```text
image upload ──> conversation inventory (attachment ID + original SHA256)
                         │
user answers ──> front brain + verified images + saved design dossier
                         │
                clarify ─┴─> next question + versioned dimensions/exchanges
                         │ resolved
                         v
           immutable drawing interpretation
                         │
              construction recipe only
                         │
           measured contract ──> user confirmation
                         │
                native CAD + bounded repair
                         │ all required checks pass
                 editable part + exports
```

The session file stores original attachment references and image hashes. The
front brain restores its dossier independently of the rolling 20-message model
window. User-provided dimensions retain the exact message ID and literal quote;
unit conversion may carry an explanatory note. Geometric derivations retain
their dimension dependencies. Critical identifiers remain stable during a
clarification sequence. Changing an acquired value requires a sourced user
correction, an unresolved contradiction, or an updated derived dependency.
Origin-specific native schemas expose the required quotation fields and the
empty dependency list for direct measurements. Arithmetic derivations use a
separate variant with required inputs and reasoning. Revision comparison rejects
late responses against a newer dossier. A proposed dossier binds to its exact
run before the Atelier displays it beside the contract.

The planner receives the resolved interpretation and original verified images.
It outputs `CadRecipe` or a typed `CadClarification` containing a question,
affected dimension IDs and the reason for the uncertainty. A clarification
adds a blocking issue to the current versioned dossier. Its exact run enters
`needs_input`; the front relays the question without an additional model call.
The Atelier displays the question and preserves its record. Execution remains
blocked until a later resolved definition produces a new confirmed contract.
Stale specialist responses cannot replace a newer design run.
`CadPlan` adds the runtime-owned drawing and validates measurement bindings.
An invented dimension identifier or replacement interpretation is rejected.
Images are rechecked against their uploaded hashes before inference and CAD
delegation. A fresh upload can recover an unavailable source using a new identity.

## Bounds and remaining scope

- Each inference can include up to eight relevant images. The dossier keeps up
  to 64 exact exchanges; reaching a bound produces an explicit diagnostic.
- Photographs supply shape context. Exact sizes require visible annotations,
  a user-supplied scale or measurements. Perspective pixels provide no metric
  authority. Ambiguous or unsupported details require clarification.
- Geometry qualification retains the existing linear measurements, sampled
  sections, closed-body and volume checks. Arbitrary topology, manufacturing
  tolerances and fits need additional measurement tools. Angular bindings now
  use checked perpendicular rise/run sections, as described below.
- Attachments sent before reference persistence was implemented may require
  uploading again. Their original bytes cannot be authenticated retroactively
  from a filename alone.
- Shared session/evidence formats use portable filesystem APIs. Windows native
  SolidCraft qualification remains open in the portability backlog.
- `tools/serve_cad_clarification_probe.py` isolates all application data and
  retains its call report across restarts. Its campaign limit is ten model calls
  and ten minutes of accumulated inference, with a 120-second per-call ceiling.
  Explicit extensions currently permit up to seventeen calls through
  `CAD_PROBE_MAX_CALLS`. An explicit time extension uses
  `CAD_PROBE_MAX_INFERENCE_SECONDS` with the already-consumed time included.

## Qualification status — 1 November 2026

Phases 1–3 are implemented and covered by isolated regression tests. Phase 4
remains open for final frontend qualification. CI review is deferred at the
user's request; the workflow currently runs on main and pull requests, and this
cycle has no pull request or merge.

| Case | Observed result |
| --- | --- |
| Dimensioned drawing with two requested changes | Height and hole diameter were requested separately. The source survived browser reload and server restarts. The resulting 80 × 40 × 25 mm stepped support with Ø8 through-hole passed all 11 checks in the Atelier. |
| Natural-language annular spacer | The complete request reached confirmation and native construction. The volume check failed, and the part remained incomplete. One repair retained the volume discrepancy; the campaign ceiling stopped further calls. |
| Unscaled artificial render plus explicit measurements | The first response used geometric relationships in arithmetic dependency fields and was rejected. Origin-specific schemas now encode the constraints. The final resumed trial has an unobserved outcome following an execution-environment renewal. |
| Missing, replaced or changed image | Isolated tests verify an explicit stop before inference, new-upload recovery and original hash validation. |
| Cross-conversation and stale-response isolation | Isolated tests verify source/quotation ownership, revision conflicts, preserved pending questions and run-bound dossier display. |

The spacer's expected volume was 2,243.097154663112 mm³ (714π). SolidCraft
reported 2,242.9876432870474 mm³, an approximately 0.00488% discrepancy, exceeding
the confirmed 0.001% relative tolerance. Its other ten checks passed. A second
construction recipe retained the discrepancy. Qualification of the engine's
mass-property precision and suitable measurement contracts remains necessary;
the existing candidate's acceptance criteria remain unchanged.

The live campaign used Codex Sol 6.1 low. Eleven completed calls were observed
before the last resumed trial. That trial and any downstream calls could have
consumed the remainder of the fourteen-call ceiling. Its temporary server,
call report and captures became unavailable in the renewed execution environment.
The automation tool then rejected access to the existing browser tab through
its URL policy. Further paid calls remain suspended until their budget and
browser access can be re-established. Monetary cost and the final trial's
token usage remain unknown.

The final standalone backend run passes 2,194 cases with eight optional skips.
An added volume-tolerance regression passes separately. Targeted CAD/session
coverage passes 63 cases; the frontend build and all 159 UI tests pass. An
earlier concurrent run hit the five-second deadline in the existing
high-event-throughput test; its isolated recheck and the standalone suite pass.
The final backend log is preserved outside temporary storage at
`/home/kwestog/Documents/code/tests/cad-conversation-qualification-20261101/backend-current.log`.

### Drawing 117 follow-up

The original user drawing 117 is retained in the isolated qualification folder
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/`.
The browser upload and same-conversation source restoration succeeded. Its
first three decisions produced two 60-second timeouts and one complete
clarification dossier in 55.298 seconds (11,612 response characters).

Visual decisions and turns with a persisted CAD dossier now have a 120-second
decision-cycle deadline and an 8,192-token output allowance. Ordinary decisions
retain 60 seconds and 4,096 output tokens. Runtime events expose the selected
deadline; cancellation and late-result rejection remain enforced. The probe
transport allows the same 120 seconds within its existing total campaign
ceiling. The focused front/CAD clarification suite passes 41 tests.
Native construction of drawing 117 remains under qualification.

The follow-up also exposed a destination-field ambiguity and a missing visual
handoff. The decision schema now describes CAD document ownership explicitly.
CAD planning receives the original conversation-owned images alongside the
runtime-bound drawing dossier, with ownership and SHA-256 checks repeated when
reading the bytes. Providers without vision stop before planning a drawing.

Angular drawing bindings can use checked perpendicular rise/run sections.
The runtime derives the nominal angle with atan2 and preserves the individual
material-section checks. Manufacturing-fit certification remains outside this
measurement contract. Local measurements and full drawing fidelity still need
native qualification on the original drawing.

Analytic cylinder criteria now read native `body_topology` observations for the
named body. They check the actual face radius and axis coordinates perpendicular
to a selected world axis. Radius bindings accept radius dimensions directly and
diameter dimensions through exactly twice the measured radius, with source-unit
conversion. Every observation retains its native revision hash and topology
evidence path. Material sections remain responsible for trimmed profile extents.
Arbitrary freeform and manufacturing certification remain outside this coverage.
Native tests distinguish a correct truncated cylinder from a wrong radius and
a translated cylinder with unchanged envelope dimensions. The focused CAD suite
passes 61 cases, and the frontend suite passes 162 cases.

The user authorized a coherent assumed R25 geometry for drawing 117. The chosen
profile spans Z=25 to Z=55 across Y=66; its right circular boundary has center
X=5, Z=40 and radius 25, reaching X=30. This is a design choice used in a guided
construction trial. It does not establish autonomous recovery of that profile
from the original source. Four additional calls were authorized. The fourteen
completed campaign calls consumed 586.851 seconds of inference. The last planner
asked about the radius/diameter binding convention; that convention is now
explicit in the schema and validated offline. No native drawing-117 candidate
was constructed at that checkpoint. The later continuation and remaining
allowance are recorded in the current recovery plan above.

The complete backend suite after these changes passes 2,219 tests with eight
optional skips (249.28 seconds). Its durable log is
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/backend-analytic-final.log`.
All 162 frontend tests and the production build pass. The drawing-117 native
delivery gate remains open; these checks establish runtime regression coverage.

The initial vision-enabled planner requested clarification of the lateral R25
surface and its relationship with the two 25 mm lips. It emitted a suspended
recipe rather than a constructible contract; validation rejected its zero-body
criterion. This is an incomplete qualification result. The typed planner
clarification outcome and conversational handoff are now implemented, with
regressions for persistence, stale-run rejection and zero worker dispatch. The
source drawing has not been established as contradictory, and no simplified
candidate was constructed. The focused regression run passes 126 tests.

### Remaining browser checks

Verify the final schema and source-retry path through the browser, enlarge a
persisted image, confirm the correct run-bound dossier, and construct the
unscaled-image candidate after reviewing its measured contract. Retain a fresh
trace and screenshot outside temporary storage. Add a successful fresh
language-only delivery alongside the already observed incomplete spacer case.
CI review and merge remain separate, deferred actions.
