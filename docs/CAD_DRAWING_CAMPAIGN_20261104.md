# Supplied-drawing live campaign

The subsequent [offline call audit](CAD_CAMPAIGN_OFFLINE_AUDIT_20261104.md)
classifies all 19 calls, reproduces the exact rejected native operation and records
the runtime evidence corrections with zero provider calls.

## Scope and evidence

The user requested drawing 42 followed by the remaining supplied complex drawings.
The current segment uses Codex Sol 6.1 low through the frontend, with at most 23
new provider calls and 1200 seconds of additional cumulative inference. Existing
call and failure ledgers remain preserved. Each case retains its own contract,
native candidate and acceptance status. Clarifications remain explicit.

| Case | Initial state | Current outcome |
| --- | --- | --- |
| Drawing 42 | Confirmed contract, six retained native checkpoints | Eleven accepted checkpoints: exterior bend, straight connections and both flanges; incomplete |
| Pipe with flanges and ribs | Supplied image retained | Frontend clarification requested; construction undispatched |
| Drawing 90 | Supplied image retained; isolated helix correction qualified separately | Units, helix pitch and handedness clarification requested; construction undispatched |
| Rectangular elbow | Supplied image retained | Front decision timed out after 120 seconds; construction undispatched |

The retained drawing-42 candidate runs its checkpoint-bound original 0.28.0
executable. A new helical candidate requires the separately qualified corrected
executable; existing candidates keep their original engine identity.

Campaign ledger:
`/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/calls-progressive-20261104.json`.
This segment begins after call 25. The prior ledger totals 319.2 seconds inference.
The harness cumulative ceiling is 48 calls and 1520 seconds.

The [axis continuation diagnosis](CAD_AXIS_CONTINUATION_DIAGNOSIS_20261104.md)
records the offline provenance corrections preceding this campaign.

## Drawing 42 observations

Call 26 proposed a revolution using the native named axis and `sketch_normal`
convention. The runtime accepted checkpoint
`f2b0d7c943b74f3c8d5cdd18667d6465` after its intermediate checks.
The model distinguished the old expression-valued explicit axis from the new
construction axis and treated its earlier investigation question as planning.

Calls 27 and 29 requested precise geometry with an explicit existing body.
The observation interface rejected that target; call 28 read body topology and
call 30 repeated the invalid target. The duplicate diagnostic stopped the run.
This interface defect originated in the preceding handoff implementation.

The correction permits an existing body name in precise-geometry questions,
labels the capture as whole-document measurement, and retains a single cache key.
The requested body and document-wide totals remain explicit. The native controller
suite passed 27 tests, including named and unnamed exact measurement requests.
Evidence: `/tmp/cad-precise-body-target-20261104.xml`.
Call 31 successfully retrieved precise geometry after the correction.

Call 32 attempted an extrusion from an observed face. Native construction created
implicit sketch/history objects outside its declared workflow inventory, so the
intermediate gate rejected that attempt and preserved the prefix. The shared
repair path received this diagnosis. Call 33 constructed a named explicit outlet
profile, resolved to zero DOF; later calls extruded it, constructed the second
flange profile and extruded the second flange. Eleven checkpoints are retained.
The last native body is closed with bounds X [-180, 410], Y [-180, 180],
Z [0, 590] mm. These are intermediate native observations.

The exact post-bend STEP-backed measurement returned one closed solid and volume
`40044126.636521906 mm³`, matching the earlier analytic exterior-union expectation.
The candidate exhausted its 16-call segment at call 41 with 63 cumulative
controller decisions and four historical native failures. The bore, bolt holes,
counterbores, R10/C10 finishes and final independent whole-part inspection remain
open. No finished part or delivery qualification is established.

## Remaining source interpretation cases

Call 42 submitted the original pipe-with-flanges-and-ribs image through a separate
frontend conversation. The front preserved its drawing dossier and requested
units plus source information for the internal passage, flange bolt circle,
thicknesses and mounting-base contour/placement. These requests remain unresolved;
they establish the observed interpretation outcome, rather than proof that every
requested quantity is absent from the source. No CAD construction was dispatched.

The idle server then switched to the separately qualified helix executable for
new candidates. Drawing 42 retains its original engine binding and must resume
with that original executable. Call 43 submitted the original drawing 90 in a new
conversation. The front retained the explicit dimensions and requested units,
pitch and handedness, distinguishing the 74.15 length from a pitch measurement.
The user has supplied no new values for these questions in this campaign.

The rectangular elbow was submitted as call 44 with its original image and
explicit preservation of the R30/R33, R57/R60 and thickness-3 annotations.

The focused offline suite after the measurement-target correction passes 91
tests: `/tmp/cad-live-fixes-regressions-20261104.xml`.

## Segment outcome

Call 44 reached the front's 120-second decision deadline. The ledger records
cancellation and the UI displays a terminal timeout message confirming that no
new task was dispatched. The attempt was preserved without an identical retry.
This is a front interpretation/latency failure; it supplies no evidence about
native rectangular-elbow construction capability.

The segment used 19 additional provider calls and 461.5 seconds cumulative
inference, within its announced 23-call / 1200-second envelope. Calls 26–41 were
the retained drawing-42 construction segment; calls 42–44 were separate original
image submissions through the frontend. API-equivalent token cost is unestablished
by this ledger. The 91 passing offline tests establish focused regressions.
They do not establish complete supplied-drawing qualification.

Remaining work:

- Continue drawing 42's interior removals and finishes with renewed resources;
  its historical controller decision budget also needs an explicit resource
  decision before further multi-step work. Preserve all accepted checkpoints.
- Resolve and verify the source questions recorded for the pipe and drawing 90
  before creating their contracts. No additional dimensions were supplied by
  the operator during this segment.
- Diagnose the rectangular drawing's front request/timeout before another trial.
  Its 120-second cancellation retains an explicit terminal UI response.

No complete part was delivered in this segment. No commit, push or merge was
performed. The isolated server currently selects the qualified helix executable
for new candidates; resuming retained drawing 42 requires selecting its original
checkpoint-bound executable as recorded above.
