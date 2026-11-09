# CAD cutter limits and material preservation

## Five-phase scope

1. Record removal intent against the drawing and the exact construction command.
2. Check cutter overruns before executing the cut on the private candidate.
3. Preserve the result, local verification and parametric edit evidence.
4. Exercise neighboring material, blind floors, multiple bodies and edit hazards.
5. Qualify the complete drawing 42 through the frontend and specialist.

The definition shown for confirmation includes the requirement to preserve
material around cuts. Construction supplies a versioned `CutIntent` for each
removal command: source feature/dimension identifiers, explicit target bodies,
through/blind intent and oriented end planes. The construction and these limits
are retained together. Verification keeps the drawing targets authoritative.

## Execution path

```text
Confirmed drawing -> construction + removal intents
                              |
                 Pre-cut material and native parameters
                              |
              Reconstruct the exact cutter in a private probe
                              |
        Clip its extensions beyond the declared opening/stop planes
                              |
             Intersect extensions with ALL existing material
                              |
          safe -> native cut -> local checks -> delivery evidence
          unsafe / uncertain -> diagnostic -> revised candidate
```

Each opening plane must have a unit outward normal and an anchor point on an
actual material boundary. The inspector checks material on its inward side and
empty space on its outward side. An already open hole can use an anchor on the
surrounding material in the same plane. A blind stop permits no cutter volume
beyond the stop plane.

Plane coordinates may use declared native length parameters. The native
expression evaluator resolves them for the current candidate; unknown references
and non-finite values stop the operation. Target names must match the command's
explicit targets. All material bodies are checked, including non-target bodies;
explicit tool bodies consumed by `solid.combine` are excluded from material.

Overrun length belongs to the cutter recipe. It has no universal 2 mm default.
The proposed length must pass the geometry check. A colliding extension needs a
shorter, segmented or otherwise revised tool, with the same part requirements.

## Geometry and evidence

The current inspector uses independent OpenCascade intersections on native STEP
exports. It verifies valid solid representations, closed shells, units and
positive orientation. The numerical-zero volume threshold is 1e-9 mm³; the
boundary classifier tolerance is 1e-7 mm. These numerical limits remain separate
from delivery tolerances. An invalid or indeterminate inspection blocks the cut.

`inspection.json` records the intent, command, engine, material inventory, resolved
limits, native/STEP hashes, measured extension intersections and execution state.
Candidate snapshots and cutter generation stay in owned private directories.
A blocked initial cut preserves geometry, parameters, solver state and history;
saving its snapshot updates only native file metadata.

Published revisions contain a `cut-safety.json` record bound to the captured
native SHA and a runtime-owned `cut-safety` acceptance observation. Later
parameter edits replay the retained construction with current native parameters
in a private validation session before publication. An unsafe edit preserves the
last delivered revision. Independent GUI copies retain their normal native edit
behavior outside BigBrain's publication gate.

## Supported cut representations

Explicit cutters currently cover box, cylinder, sphere, cone, torus, extrusion,
revolution, sweep, loft, pipe and explicit `solid.combine` tools. The probe uses
the native command and profile state with a new-body operation. `solid.hole`'s
implicit cutter remains unsupported by this inspector; the specialist receives
an actionable instruction to use explicit scoped cylinder/profile cuts.

The initial guard represents end limits as planes. Openings with geometry that
cannot be represented safely this way require another construction strategy or
a future qualified inspector. Source interpretation and complete local feature
verification retain their own gates: the overrun check establishes preservation
beyond the declared end limits.

The shared intent, orchestration and evidence formats target Linux and Windows.
Native launching remains behind `SolidCraftSession`; the geometry backend uses
the portable CAD dependency. Native qualification so far runs on Linux. Windows
qualification and future native measurement/inspection replacement remain open.

## Qualification and remaining gates

Offline cases cover safe through cuts, properly bounded blind cuts, neighboring
bodies, a same-body rib, a thin wall, shorter extensions, unknown parameters,
unresolved opening planes, inconclusive geometry inspection and changed obstacle
positions. Worker tests exercise retained safety evidence, safe edits and
preservation of the previous delivery after unsafe edits. Existing local feature
measurement and repair assertions remain exercised.

The initial targeted suite passed 84 tests. An additional guarded elbow
qualification passes at R30 and blocks at R60 before mutation. At R60, the
exported inlet face is approximately 0.0000745 mm from its nominal plane after
the native exterior union. This exceeds the guard's 0.0000001 mm boundary
threshold. The record remains an open precision/alignment case; no tolerance
relaxation has been applied. Exact face-distance checks supplement native solid
classification because a trimmed STEP boundary can be classified as interior.

New complete recipes allow 64 geometry commands and declare up to 600 seconds
in their displayed definition. The newly authorized drawing 42 live campaign
has a separate ceiling of 12 Sol 6.1 low calls and 900 inference seconds, on the
already supplied drawing and disposable CAD models only. It remains pending
until the offline gates and the real frontend run have current evidence.

Construction discovery permits two successful reference requests, one reference
correction and one construction correction within five inference calls. Each
phase retains its own correction slot and shares the worker deadline and the
campaign ceiling. Cut-intent mismatch diagnostics enumerate missing, extra and
required command indices. A drawing 42 attempt exposed an extra intent on a
chamfer command before any candidate mutation; this failed recipe remains in
the campaign ledger. The separate correction-slot regression suite passes
19 tests.

### Drawing 42 frontend campaign, 2026-11-03

The authorized ledger consumed 12 completed calls and 358.261 seconds of
inference. The frontend displayed every drawing dimension before execution.
The first recipe failed cut-intent preflight. After the bounded correction-slot
fix, a second frontend attempt reached native construction. Its first recipe
used unsupported point parameters for `sketch.rectangle.rounded`. Automatic
repair changed the sketch construction and reached the exterior flange union.
The next failure selected a smooth tangent edge for `solid.fillet`; SolidCraft
requires a sharp edge there. A further repair request was refused at the
12-call ceiling. No ready delivery or completed local-feature verification was
produced, and the cut-overrun guard was not reached on this complete model.

The native flange union reported a Boolean retry displacement of
0.001784397 mm and rotation of 0.000002 rad. Subsequent geometry measurements
and boundary checks must retain this diagnostic when qualifying that candidate.
Reference requests were repeated during recipe repair, consuming four of the
second attempt's six specialist calls. Reusing retrieved signatures and choosing
fillet edges from actual intermediate geometry remain concrete follow-up work.

Machine-local evidence:

- `calls-cut-safety-20261103.json` in the isolated probe root records all calls.
- CAD document `4437e5166dd1449c95d2352d46c8c70b` retains both native failures.
- `cut-safety-final-20261103-results.xml` records the 84-test targeted run.
- `guarded-elbow-distance-20261103/` retains the separate R60 alignment failure.

The complete drawing 42 qualification remains open.

The campaign allowance was subsequently extended to 36 total calls and 2700
cumulative inference seconds for the same drawing and disposable models.
Worker-local reference evidence now accompanies repair packets. Failed native
fillet/chamfer commands execute separately from preceding features; their
rollback preserves the real operand, which is saved and measured for the
repair diagnostic. Eight focused reference/operand-evidence tests pass. The
new live outcome remains to be established.

Measured planar alignment is now an explicit optional opening-boundary field,
`alignment_tolerance_mm` (default zero, maximum 0.05 mm as stated in the
definition). The inspector resolves a real trimmed planar face within that
distance and 0.1 degree of the requested normal, requires an unambiguous plane
and verifies outward material classification. It then performs the unchanged
extension-versus-all-material intersection checks using that measured plane.
Evidence records both requested and measured origins/normals and the distance.
Blind stops retain their strict limits. Two aligned elbow cases pass with their
parameter edits and local material checks; 18 safety tests pass, including
nearby ribs, other bodies, thin walls and out-of-tolerance alignment rejection.
The original zero-alignment R60 case remains a strict diagnostic fixture.

The expanded targeted suite passes 92 tests. Four transport/session tests also
pass. Native construction now permits 120 seconds per engine request inside
the unchanged 600-second worker deadline. A native timeout closes the uncertain
session and reports the operation and elapsed allowance through `CadTimeoutError`,
preserving compatibility with `TimeoutError`. A drawing 42 replay reached the
guarded continuous bore and mouth-chamfer operations; its earlier 30-second
cone-cut timeout remains retained evidence. Complete delivery is still pending.

The cone cut also exceeded 120 seconds. Its timeout now carries a structured
closed-session diagnostic through the existing bounded repair loop. Repairs
start a fresh private session from the confirmed original; the uncertain
session is never reused. Cone cuts retain native operand topology before
execution so a repair can select a native mouth chamfer from observed edges.
The construction prompt recommends that alternative after a cone-cut timeout.
Thirty focused safety/reference/transport tests pass after this change.
