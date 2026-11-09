# Retained elbow: observation coverage and next-operation diagnosis

## Finding

The six-checkpoint drawing-42 candidate supports the next exterior bend
revolution. A local reproduction on disposable copies succeeds with a positive
90-degree revolution about `Axe_revolution_coude`, joined to `Coude_42`.
The complete part remains incomplete. This reproduction establishes one native
construction boundary; model-directed continuation and final inspection remain open.

## Trace reconstruction

| Campaign call | Observed action | Evidence contribution |
| --- | --- | --- |
| 16 | Retrieve datum-plane and axis command references | Native signatures |
| 17 | Create two datum planes and their intersection axis | Sixth accepted checkpoint |
| 18 | Cancelled during operator server restart | Charged call; no returned decision |
| 19 | `inspect_design` | Feature names, sketch state and existing solid |
| 20 | `parameter_graph` | Identical to the graph already stored in checkpoint 6 |
| 21 | `precise_geometry` | Bounds and surfaces of the existing flange/straight exterior |

The axis group's first unresolved obligation explicitly requests observation of
the axis orientation before revolution. The controller packet omits that group's
`unresolved_obligations`. It supplies the accepted workflow and feature names,
while its compact timeline also drops native `type` through a `kind`-only filter.

The available observation enum provides general design inspection, parameter
dependencies, body topology and precise solid geometry. General inspection
reports the axis name but omits its resolved origin/direction. Body/STEP geometry
contains solid faces; the new construction axis contributes no solid geometry.
The controller exposes no targeted native `timeline.inspect` observation, although
the installed engine supports that read-only command for feature definitions.
Native definitions identify the two referenced planes; resolving the axis still
requires geometry evaluation or a native output that exposes its actual frame.

After execution the runtime clears its live observation map. Detailed design and
parameter-graph evidence remain in the immutable checkpoint, but only a compact
design is supplied automatically to the next model decision. This explains why
the repeated graph request can retrieve existing evidence through an extra call.
The runtime has no observation intent/expected-evidence field to distinguish a
useful new inspection from an observation that cannot answer the pending question.

These are concrete observation-interface gaps. The three observation choices alone
do not prove indefinite model looping. Provider request packets were not persisted
by the campaign ledger, so their exact byte-for-byte historical contents and the
model's internal rationale cannot be reconstructed from that ledger.

## Local native reproduction

Source checkpoint:
`525ca892243049aca73f3e25df9f63d2` in candidate
`d4f8d16c0e884319b9df205f76f19943`.

The test opens a separate copy for each direction using the checkpoint's original
0.28.0 executable. The accepted source SHA-256 remains unchanged. The command is:

```json
{"command":"solid.revolve","params":{
  "sketch":"Profil_coude_exterieur",
  "axis":"Axe_revolution_coude",
  "angle":"90 deg",
  "operation":"join",
  "targets":["Coude_42"],
  "name":"Diagnostic_revolution"
}}
```

| Direction | Result |
| --- | --- |
| +90 degrees | One closed solid, no native timeline errors |
| -90 degrees | Native union returns no result |

The successful STEP-backed volume is `40044126.636521906 mm³`.
Existing measured volume plus the analytic quarter-torus volume
`π × 145² × π × 260 / 2` gives `40044126.6365218 mm³`;
relative difference is approximately `2.6e-15`.
Bounds are X `[-180, 260]`, Y `[-180, 180]`, Z `[0, 555]` mm,
within the measurement bounding-box margin. This is evidence for the exterior
union only; bore continuity, second flange, holes and finishes are pending.

Evidence:
`/mnt/cold-hdd/bigbrain-local/cad/axis-trace-9z0zw46r/report.json`.
The disposable reproduction script is `/tmp/cad_axis_trace_diagnostic.py`.
No provider calls were issued during this diagnosis.

## Focused correction boundary

1. Supply current-checkpoint evidence availability and pending group obligations.
   Reuse the stored design and parameter graph with explicit checkpoint provenance.
2. Expose targeted feature-definition inspection and clearly state which geometric
   properties each observation can establish. Identify unresolved native frames
   explicitly; precise solid measurement does not establish datum-axis orientation.
3. Bind observation requests to the information they seek and retain outcomes.
   Detect repeated reads at unchanged checkpoints while allowing new questions and
   topology-specific evidence. Preserve full request/action traces for diagnosis.
4. Qualify that handoff offline before another paid continuation. Keep geometry
   choice model-directed and retain the existing final delivery checks.

The successful operator-directed local reproduction is diagnostic evidence.
It has not been promoted into the user's accepted construction history.

## Implemented handoff and offline verification

The controller now supplies the current checkpoint's full observed design and
parameter graph, their checkpoint provenance, and its pending obligations. The
compact history retains native feature types. Additional observations from older
checkpoints are excluded from the decision packet.

`feature_definition` invokes the installed read-only `timeline.inspect` command
for an existing named feature. Returned identity is checked. Each observation
states its question; cached reads at the same checkpoint receive a diagnostic
pointing to the existing evidence. Tool coverage explicitly distinguishes native
definitions, parameter dependencies and STEP-backed solid measurements. Resolved
datum frames remain unavailable from these native outputs.

Each new decision retains its text input packet, system instructions, model
settings and provider response or interruption status in a local trace. Image
content remains in its existing attachment store; the trace records image count.
Paid-call and native repair counters keep their existing semantics.

Offline verification on 2026-11-04:

| Check | Result |
| --- | --- |
| Controller, recovery, worker, capabilities and transport suites | 86 passed, zero failures/skips |
| Targeted feature inspection through native engine | Existing feature definition returned with matching identity |
| Cached parameter graph | Supplied directly; redundant request rejected before native reread |
| Provider failure | Input packet and interruption retained |
| Actual six-checkpoint drawing-42 packet | Pending axis obligation, graph and native axis type present |

The actual retained packet is 113628 bytes, within the 256000-byte input bound.
Its generation leaves the candidate controller file unchanged. No model calls
were made for this verification. Evidence reports:
`/tmp/cad-observation-regressions-20261104.xml` and
`/tmp/cad42-evidence-packet-check.json`.

The observation handoff is qualified offline. Its effect on the model's next
choice and completion of drawing 42 still requires an authorized live continuation.

## Subsequent four-call live result

The user requested continuation after the offline checks. Four additional calls
were announced and issued through the browser, with one-decision grants and a
reviewed result before every subsequent call. Calls 22–24 read the native axis
definition and the two referenced datum-plane definitions. Each result answered
the stated question; references and checkpoint evidence persisted across resumes.
Call 25 returned `blocked`, preserving all six accepted checkpoints. This segment
used 39.0 seconds of inference, with zero new native mutation failures.

The returned blockage correctly identifies a derived line parallel to Y at X=260,
Z=150, but treats direct observation of a resolved axis frame as a prerequisite.
That prerequisite originated in the model's earlier group obligation. It is
separate from the confirmed dimensional acceptance requirements. The blockage
also cites the historical revolution error from an explicit expression-valued
axis, although the current named native axis has a different construction.
The failure summary preserves the error text without the failed command's axis
arguments, which limits strategy-specific interpretation of that history.

The live test establishes successful targeted evidence retrieval. It leaves the
transition from sufficient evidence to construction unresolved. The earlier local
positive-angle reproduction remains separate evidence of native feasibility;
the live model did not receive that operator-generated reproduction as an input.
Whole-part delivery remains closed. No fifth call was issued.

Before another continuation, distinguish model-proposed investigation questions
from contractual acceptance gates and retain failed-command input provenance.
Any failure-resolution statement must identify the changed inputs and evidence;
historical failure records remain preserved. The four-call result supplies no
evidence that the complete drawing-42 part is qualified.

## Planning authority and historical input correction

The decision packet now labels the last group's pending items as
`construction_questions`, with model-group provenance and an explicit planning
authority. The original definition and runtime checks retain acceptance authority.
The controller instructions allow evidence-based revision of investigation
questions while preserving confirmed dimensions and safety requirements.
The legacy `pending_obligations` field remains available for saved trace readers.

New native failures reference their retained proposal and its SHA-256 digest.
Historical failure inputs are recovered from failed-attempt proposals whose exact
command/workflow/cut-intent fingerprint matches the failure record. Missing
proposals remain explicitly unavailable. Tampered referenced proposals stop
context assembly. Every exposed failure is scoped to its historical attempt and
base checkpoint; a changed strategy remains subject to actual execution checks.

On the real retained drawing-42 candidate, all three historical proposals were
recovered by fingerprint. The failed revolution's axis origin is
`["elbow_axis_radius", 0, "end_tangent_distance"]`; its direction is `[0, 1, 0]`.
This input is distinct from the named construction axis subsequently created.
The candidate controller and its six accepted checkpoints remain unchanged.
The updated packet occupies 119130 bytes. Blocked decisions now persist their
actual reason in `last_action` for subsequent diagnosis.

Offline qualification: 90 tests passed, zero failures/skips, in
`/tmp/cad-failure-provenance-regressions-20261104.xml`.
The actual-candidate packet check is recorded in
`/tmp/cad42-evidence-packet-check.json`.
This correction issued zero provider calls. Its influence on the model's next
decision remains a live qualification gate; no complete-part result is claimed.
