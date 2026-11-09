# Drawing 42 completion preparation

## Retained candidate

| Item | Recorded state |
| --- | --- |
| Document | `d4f8d16c0e884319b9df205f76f19943` |
| Confirmed definition | `task-438023c3c2435ca7`, revision 2 |
| Contract SHA-256 | `c701d53f76fded211e43b6025f034dedb59980d218fb054ccb752809a742a484` |
| Accepted checkpoints | 12 |
| Cumulative controller decisions | 66 |
| Historical native failures | 4 |
| Retained native commands | 27 |
| Current scoped command ceiling | 96 |
| Engine | Original SolidCraft 0.28.0, SHA-256 `8d67a0d09eb41232268b73406d660ce5d50894d0a42f1ff506bf17704f841350` |

The confirmed definition remains valid. Its approval, source dimensions and
acceptance targets require preservation. The resource continuation is separate
from the drawing contract. Existing counters and failed evidence remain retained.

## Remaining construction and evidence

| Stage | Required work | Evidence before continuing |
| --- | --- | --- |
| 1. Interior passage | Continuous Ø210 through the R260 bend and both straight ends | Scoped cutter intent, extension checks against every material body, continuous empty bore and retained wall samples |
| 2. Bolt holes | Four Ø30 holes in each flange, 260 × 260 pattern | Independent diameter, count, center and through-depth checks |
| 3. Counterbores | Eight Ø60 counterbores, depth 10 from the exterior faces | Entry orientation, depth, remaining floor/wall and correspondence with bolt holes |
| 4. Finishes | Two local R10 junctions and two local C10 bore-mouth chamfers | Current topology, individual finishing operations and local measurements |
| 5. Whole-part inspection | Geometry, editable history, driving constraints and artifact consistency | Final inspection covering every confirmed requirement and traceable STEP/native outputs |

The exterior-first native construction pattern remains the basis for the bore.
Any cutter extension must satisfy the existing material-preservation checks.
The specialist retains responsibility for selecting its concrete native groups.
This preparation supplies no operator-authored substitute construction recipe.

## Resource estimate

The following is a planning estimate, rather than a completion guarantee:

| Allocation | Estimated model decisions |
| --- | ---: |
| Interior-passage construction and evidence selection | 6–8 |
| Hole and counterbore profile/cut groups | 8 |
| Four individual finishes | 4 |
| Missing native signatures or targeted evidence | 2–4 |
| Inspection assembly and conclusion | 2–4 |
| Repair margin | 4 |

The initial estimate was 32 additional calls and 20 minutes of inference. The
user requested additional margin. The active allocation is **40 additional
provider calls and 30 minutes of cumulative inference**, with **six calls reserved
for inspection and conclusion**. Construction has a 34-call share. Unresolved work
remains incomplete when the inspection reserve cannot establish delivery.

The confirmed per-worker execution deadline remains 600 seconds. Stage-boundary
resumptions may use the same candidate and cumulative campaign ledger. A failed
operation or incomplete diagnostic requires offline investigation before another
repair call. The transport's bounded request and cancellation behavior remains.

## Capacity gate discovered before inference

The current 64-command construction protocol leaves 40 commands after the
retained exterior. A direct explicit-profile estimate is:

- Three bore profile/cut groups: approximately 12 commands.
- Four grouped hole/counterbore profiles and cuts: approximately 28 commands.
- Four local finishes: 4 commands.

This route reaches about **68 total commands**, before extra datum, tool-union
or organization commands. A pattern-based route may be shorter, but its complete
material-removal and verification behavior must be qualified before relying on
that reduction. The model must retain professional design quality throughout.

Implemented capacity: **96 cumulative commands for this explicitly extended run**,
while preserving the existing 64-command per-group bound. The resource change
must cover all corresponding representations together:

1. Controller's cumulative command gate and exposed remaining capacity.
2. `CadConstruction.commands` assembly and retained-run validation.
3. `CutIntent.command_index`, including offsets during group concatenation.
4. Construction/inspection handoff, cut-safety replay and evidence serialization.

The default cumulative capacity remains 64 for runs lacking that extension.
The original failure and checkpoint hashes remain unchanged.

The controller's default cumulative decision ceiling is also 64. An explicit
40-call continuation from decision 63 has an absolute decision ceiling of 103.
The packet must expose actual remaining authorized calls and command capacity,
alongside the inspection reserve. A reset of historical counters cannot implement
this extension.

The 16-cut-intent aggregate ceiling must also be checked during offline assembly:
grouping four flange holes per explicit profile cut keeps the estimate within it;
individual hole/counterbore cuts can exceed it. Per-command source provenance
and opening/stop limits remain mandatory under either representation. The
specialist must receive the representation bounds before constructing a suffix.

## Offline gates before the paid continuation

1. Implement the confirmed extension with exact contract, document and engine
   scope; retain every previous continuation and consumed call.
2. Test crossing the old decision/command ceilings through a scoped extension,
   unchanged default limits, altered-grant rejection and restart persistence.
3. Exercise concatenated cut-intent indices above 63 through complete construction
   assembly and its inspection/retention handoff. Reject invalid limits before
   native mutation or model inference.
4. Replay current-checkpoint evidence availability and meaningful rejected-state
   diagnostics using the retained drawing-42 trace and disposable native copies.
5. Start only the drawing-42 continuation, on its original executable, with the
   exact same accepted head. Observe the first construction outcome before further
   repairs. Preserve the final inspection reserve across stage resumptions.

## Current status

The scoped capacity extension is implemented. The focused offline regression
suite passed 129 tests. Four resource tests also passed against the exact original
SolidCraft executable used by this candidate, covering extended replay, inspection
handoff, persisted counters, grant scope and first-error stopping.

The continuation recorded three provider requests:

| Ledger call | Outcome |
| --- | --- |
| 45 | Exterior geometry observation completed |
| 46 | Entrance-bore profile accepted as checkpoint `32c2bc57207d4cfb92a105c42d665bb4` |
| 47 | Provider rejected the request with `usageLimitExceeded`; decision 66 records the transport error |

The accepted profile is fully constrained and solved. Its diameter is driven by
`bore_diameter = 210 mm`; its center is located at the sketch origin. The parameter
graph reports no cycles or errors. This checkpoint contains the profile; material
removal and final whole-part inspection remain pending.

The segment recorded 48.154 seconds of inference and consumed three of its 40
requests, including the quota-rejected request. **37 requests remain, including
the six-call inspection reserve.** The campaign ledger contains 47 requests in
total. Historical counters, four native failure records, the original executable,
source dimensions and manufacturing tolerances remain preserved.

The provider quota blocks further inference. The interrupted request produced no
accepted construction group. Resume from the retained checkpoint once provider
access is available, with the existing ledger and resource grant. Other drawing
campaigns remain outside this completion segment.

During the quota-blocked follow-up, 49 controller, resource and observation tests
passed locally in 16.88 seconds using the original SolidCraft executable. The
demonstration server on port 3134 was restarted and returned HTTP 200. Startup
preserved decision 66 and the same accepted checkpoint; it issued no model call.
