# CAD measurement qualification

## Provider strategy and native migration

Native analytic measurements are preferred whenever their capability is
qualified. The current native provider supplies cylinder radii and axes; the
STEP provider supplies precise volume, bounds, vertices and solid validation.
`MeasurementRouter` selects providers by capability. The CAD brain consumes
one shared result with units, revision hashes and per-capability provenance.

Return precise volume and other fallback capabilities to native tools when
SolidCraft exposes them and they pass the same reference, defect and persistence
tests. This migration remains a tracked CAD milestone. Enable the capability in
the native provider after qualification; worker orchestration and acceptance
criteria stay shared. STEP remains available for independent cross-checks.

Both providers use platform-neutral paths and results. Native process launch
and executable discovery remain in the SolidCraft adapter, including Windows
process groups and PATH/configured-executable discovery. OpenCascade is loaded
as a Python dependency, with an explicit diagnostic when unavailable. Linux
native qualification is exercised locally. Windows native qualification remains
pending; simulated selection tests establish the shared provider contract only.

## Scope

Phase 2 checks measurement mechanisms against independent analytic references.
The qualification uses SolidCraft 0.28.0 on Linux, the version currently integrated
with BigBrain. Construction uses fixed reference geometry; expected material
intervals and volumes are calculated separately from elementary geometry.

```text
Reference solid -> native saved candidate -> body topology
                            |
                        STL export
                            |
                 independent line intersections
                            |
       compare with analytic coordinates and defect expectations
```

STL sections run outside SolidCraft. They inspect its exported boundary mesh,
so this cross-check shares the CAD kernel and export path. It establishes
nominal local geometry within the tested section tolerance. Manufacturing
certification requires a separate accuracy contract.

## Observed accuracy

Section acceptance is 0.05 mm. Analytic radius and axis acceptance is
0.001 mm. No inference calls are involved. The table below records the initial
SolidCraft-only diagnostic, before the independent STEP reader was connected.

| Reference | Maximum section coordinate error | Native cylinder result | Absolute volume error |
| --- | ---: | --- | ---: |
| 60 × 40 × 12 mm plate, Ø10 through-hole | 0.005099 mm | Passed | 0.156550 mm³ |
| Same plate, Ø18 counterbore 4 mm deep | 0.009177 mm | Passed | 0.219222 mm³ |
| 170 × 66 × 35 mm block, clipped Ø80 pocket 18 mm deep | 0.014467 mm | Inconclusive | 5.536625 mm³ |

Values are rounded upward. The volume column records observed discrepancies;
volume precision at 0.01 mm³ is unsupported by these results. Existing product
acceptance criteria remain in force.

### Analytic STEP correction

SolidCraft 0.28.0 computes volume from a fine tessellation. Its face `exact`
flag reports whether the face name follows exact feature history. That flag
does not certify or invalidate an analytic cylindrical surface. The initial
interpretation of `exact:false` as approximate geometry was incorrect.

Sources from the integrated release:
[volume implementation](https://github.com/tangency-labs/solidcraft/blob/v0.28.0/crates/kernel/src/measure.rs)
and [face naming](https://github.com/tangency-labs/solidcraft/blob/v0.28.0/crates/doc/src/naming.rs).

The CAD adapter now reads the exported STEP with OpenCascade through the
`cadquery-ocp-novtk` CAD extra. It checks B-rep validity, closed shells, solid
inventory and body identity, integrates the actual surfaces with adaptive
quadrature, and reads analytic cylinder radii and axes. Invalid or ambiguous
geometry produces a diagnostic. The worker uses these observations for geometry
acceptance and inspection planning. Native measurements remain retained.

| Reference | STEP volume error | STEP cylinder |
| --- | ---: | --- |
| Ø10 through-hole | 3.64 × 10⁻¹² mm³ | Radius 5 mm, axis at (20, 20) mm |
| Ø18 counterbore | 3.64 × 10⁻¹² mm³ | Radius 9 mm, axis at (20, 20) mm |
| Clipped Ø80 pocket | Below displayed double precision | Radius 40 mm, axis at (110, 33) mm |

Regression assertions require volume error below 10⁻⁶ mm³ for these reference
solids and radius/axis error below 10⁻⁹ mm. These measured results establish
accuracy on the reference set. General integration error remains numerical;
manufacturing certification retains its separate contract.

`measurement-inspection.json` binds observations to both native and STEP hashes and
records the method, units and integration error estimate. `geometry.evidence_ref`
points to this record. Multi-body association requires unique matching bounds;
ambiguous bodies stop inspection. The 0.05 mm envelope matching threshold selects
identity only; acceptance uses independently calculated analytic bounds.

Install the CAD extra with `pip install -e '.[cad]'`. The dependency has no VTK
renderer and uses the shared Python adapter on Linux and Windows. Native Windows
qualification remains pending.

The Ø80 reference samples five horizontal chords, including its centerline,
and vertical sections inside and outside the pocket. Expected chord endpoints
are `110 ± sqrt(40² − (y − 33)²)`. These observations establish the sampled opening,
position and depth at the section tolerance. The STEP analytic measurement
resolves the cylinder independently of native face-name reliability.

## Defect and boundary checks

- Every valid reference section rejects a target displaced by 1 mm.
- A blind hole with a 1 mm floor fails the through-hole requirement.
- Tangent or surface-boundary lines remain inconclusive.
- Section calculations retain their results after axis permutations and translation.
- Existing cylinder tests reject an incorrect radius, an offset axis and an
  incorrectly oriented axis. Legacy observations lacking verified analytic
  surface data preserve uncertainty.
- Existing section tests distinguish holes of equal volume at different positions,
  reject malformed STL input and check ambiguous intersections.

## Reproduction and next gate

Run `pytest tests/test_cad_measurement_qualification.py tests/test_cad_sections.py
tests/test_cad_surfaces.py tests/test_cad_requirements.py` with the native engine
available. Each reference test writes `qualification.json` alongside its saved
candidate and exports in the pytest temporary directory. The record includes
the source hash, engine version, topology, expected and observed sections,
numeric errors and retained analytic uncertainty.

The section qualification supports inspecting drawing 117 with independent
material probes. Read-only STEP inspection of retained revision 4 identifies
its bottom cylinder radius as 39.99999999999997 mm, with perpendicular center
(110.00000000000003, −33.00000000000001) mm. Its original native artifact and
delivery record remain unchanged. Full drawing and workflow acceptance remains
part of the next phase.

SolidCraft 0.30.1 accuracy and Windows native execution require their own
qualification. The earlier 0.30.1 open/save/reopen check covers file compatibility.

Local qualification: 90 tests passed across provider selection, measurement references, sections,
analytic surfaces, requirement calculations, workflow, worker integration and
the native adapter. The reference-solid tests also pass independently.

## Drawing 117 frontend probe

On 2 November 2026 the retained drawing was resumed through the Atelier button
on server 3134. The stricter sketch gate requested a construction correction.
One Codex Sol 6.1 low call completed in 20.375 seconds; revision 5 then passed
all 54 recorded checks. Six sketches report solved, zero remaining degrees of
freedom, and observed dimensional constraints. The published native and STEP
hashes match their recorded measurement sources.

The result uses native cylinder measurements and OpenCascade volume, bounds,
vertex and solid-validity observations. Dimensions are 170 × 66 × 80 mm and
volume is 409983.253729074 mm³. The chosen R25 interpretation and nominal H8
boundary continue to define this trial's scope.

A separate disposable copy changed parameter L from 170 to 180 mm. The body
length became 180 mm, all six sketches remained solved with zero freedom,
and the history reported no errors or warnings. The original revision stayed
unchanged.

Evidence directory: `/home/kwestog/Documents/code/tests/cad-drawing117-live-20261101/`.
The inference ledger is `calls-metrology-20261102.json`; the screenshot is
`measurement-provider-live-revision5.png`; edit evidence is
`measurement-provider-edit-check.json`. The revision's `criterion-observations.json`,
`design-quality.json` and `measurement-inspection.json` contain the detailed checks.
