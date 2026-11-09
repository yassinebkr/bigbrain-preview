# Complex CAD part qualification

## Starting point

Branch `feat/cad-complex-parts` starts at `93e486d`, preserving the measurement
providers, drawing 117 result and free preview rotation. The preceding branch
has been pushed. Merge remains a separate action.

Drawing 117 passed its 54 nominal checks under the retained R25 assumption and
H8 boundary. Drawing 83 initially stopped in the front reading path: a generic
image-quality clarification followed by a 120-second decision timeout. No CAD
construction was dispatched. The uploaded image and original JPEG both have
474 × 670 pixels. Preserve this failure in the campaign record.

## Frozen cases

| Source | Capabilities to exercise | Local verification obligations |
| --- | --- | --- |
| Drawing 42 | Curved hollow passage, flanges, bolt patterns, fillets and chamfers | Bore continuity, wall thickness, bend and straight lengths, flange geometry and hole locations |
| Pipe with flange | Curved pipe, circular flanges, mounting base and reinforcing ribs | Source units, bend radii, openings, flange patterns, rib placement and thickness |
| Drawing 90 | Helical geometry, end transitions, R3 roots and end chamfers | Pitch/start/handedness when defined, diameters, overall and active lengths, local cross-sections |
| Rectangular elbow | Hollow rectangular bend, mating flanges and repeated holes | Curved wall thickness, internal continuity, flange apertures and hole positions |

The user-supplied sources are retained outside Git in
`/home/kwestog/Documents/code/tests/cad-capability-live-20261102/`.
Drawing 83 remains the preliminary reading/decision regression.

## Work sequence

The 3 November architecture decision supersedes the exploratory live-first
sequence below. Retain SolidCraft 0.28.0, qualify required operation variants and
their interactions, then complete progressive construction and Atelier wiring
before the next drawing campaign. The current measured results and remaining
gates are recorded in [capability qualification](CAD_CAPABILITY_QUALIFICATION.md).
The separately retained architecture document contains the user's confirmed
decision package and M0–M6 milestones.

Current state: native inventory and save/reopen baseline refreshed; M2 operation
qualification remains open for the remaining complex paths. The isolated 0.28.0
coil correction passes its recorded Linux precision/edit/reopen cases; application
runtime promotion remains separate. The M3 progressive driver
and M4 worker/Atelier wiring are implemented and exercised with prepared model
decisions and the native engine. Live model and complex-drawing qualification
remain open; detailed evidence and limits are in the capability report.

The [capability qualification matrix](CAD_CAPABILITY_QUALIFICATION.md) now defines
general command coverage and operation-family qualification. The frozen drawings
below serve as integration cases within that broader program.

1. Run each case through the frontend and record the first outcome: precise
   clarification, complete definition, technical block or construction result.
2. Separate source uncertainty, interpretation, tool selection, native command
   execution, design quality and verification failures from the recorded trace.
3. Improve shared capabilities exposed by those failures. Keep measured targets,
   source provenance and editable construction history across corrections.
4. Re-run affected cases and regressions, then inspect the saved native result,
   local geometry and Atelier state. Report the final outcome for every case.

Each live attempt uses Codex Sol 6.1 low and records calls, duration, errors and
artifact identities. The campaign has a 24-call / 20-minute inference ceiling,
including the preceding drawing 117 and 83 calls in its retained ledger.
Source ambiguities require a targeted question. A simplified substitute or
unresolved local feature remains incomplete.

## Later work

Return STEP fallback measurements to native SolidCraft capabilities after the
same qualification passes. Qualify Windows native integration. Add versioned
standards knowledge with verified sources for fits, threads, surface finish and
geometric tolerances. Manufacturing certification retains its own evidence gate.

## Native tool discovery

Construction receives the installed geometry command IDs and a compact starting
reference. It can request related command descriptions and bundled workflow
guides before returning its complete recipe. Descriptions come directly from
SolidCraft's `describe_command`, retaining input/output schemas where available;
guides come from `skill_reference`. Discovery uses a separate read-only session
and the geometry allowlist. These requests share the existing worker deadline
and inference allowance. The confirmed definition remains unchanged.

This path currently covers new-part construction. Existing recipe planning and
inspection/repair still have their previous reference interfaces. Their broader
qualification remains open. Native documentation availability establishes tool
access; successful part construction and local measurement require their own
campaign evidence.

The first drawing 42 attempt exposed omitted sweep/revolution descriptions in
the fixed starting reference. It produced an incomplete construction. The pipe
with flange stopped in front-decision validation on a derived dimension with an
unknown dependency. Both failures remain in the retained live ledger.

### Native discovery qualification, 2026-11-02

The targeted suite passes 71 tests, including installed command descriptions,
all three bundled skill entry files, geometry allowlisting, reference-request
limits, drawing provenance, workflow, worker integration and metrology.

The frontend drawing 42 retry reached a confirmed definition and exercised
native reference retrieval. An initial guide request used the default file;
the editing skill only exposes `SKILL.md`. The loader now explicitly requests
the entry file for every guide, with an installed-engine regression.

The resumed candidate corrected generated hole names and reached the union of
the pipe and flanges. SolidCraft rejected `solid.combine` with `boolean Union:
the operation failed: no result`. An exact local replay before that operation
produced three bodies reported closed by the native engine. Each flange union
also failed separately. These observations do not establish whether the cause
is the construction geometry, its representation or a kernel limitation.

The saved pre-union native model and diagnostics are in the machine-local
directory `/mnt/cold-hdd/bigbrain-local/cad/drawing42-union-audit-s2r_5cwh`.
The frontend screenshot is retained with the external campaign evidence as
`drawing42-native-discovery-result.png`. The campaign ledger contains 23 calls
and about 674 seconds of inference out of its 24-call / 1200-second ceiling.
Drawing 42 remains incomplete; the other complex cases remain unqualified.

The follow-up [native Boolean investigation](CAD_NATIVE_BOOLEAN_LIMITATION.md)
records the failing intersection-loop stages and an exterior-first/extended-bore
construction alternative qualified on two radii and their edits. Reuse this
native feature-order pattern when rebuilding the candidate; preserve the full
drawing definition, detailed measurements and professional design-quality gates.
Independent OpenCascade fusion remains diagnostic evidence.

The [cut-safety implementation](CAD_CUT_SAFETY.md) binds every removal to drawing
intent, checks extensions before mutation and rechecks retained cuts after
parameter edits. Its 84-test targeted regression suite passes. Additional R60
elbow qualification exposes an exported-face alignment limit, retained as an
open failure. The drawing 42 frontend campaign uses a separate 12-call /
900-second inference ledger dated 2026-11-03.
