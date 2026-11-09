# CAD capability coverage

## Objective

Cover the installed SolidCraft command surface and qualify representative
operation families. Supplied drawings exercise complete workflows after the
family checks. Extend the inventory whenever the native catalog changes.

## Execution checkpoint — 3 November 2026

The current integration remains on SolidCraft 0.28.0. Engine migration and
comparisons with the prerelease kernel are deferred by the user.

The refreshed installed inventory contains 553 commands, with 193 in worker scope;
all 553 native descriptions were retrieved. Discovery coverage does not establish
execution coverage. Machine-local evidence is retained under
`/mnt/cold-hdd/bigbrain-local/cad/`:

| Evidence | Result and scope |
| --- | --- |
| `m1-inventory-20261103/inventory.json` | Complete installed discovery inventory |
| `m1-m2-run-20261103.xml` | 24 passed, 3 failed native operation cases, including parameter edits in successful cases |
| `m1-recovery-20261103.xml` | 2 passed: save/reopen of constrained profile and parameters, downstream rebuild, restoration and changed-byte rejection |
| `m2-rect-bend-20261103.xml` | Curved rectangular-section sweep and bend-radius edit passed after correcting unsupported expression coordinates in the fixture |
| `m2-mouth-20261103.xml` | Bore-mouth native chamfer and distance edit passed against analytic removed-volume expectations |
| `m2-coil-rebuild-20261103.xml` | Coil builds and pitch editing complete, but the strict analytic-volume assertion fails at both values |
| `m3-boundaries-20261103.xml` | 33 passed: execution-store recovery boundaries, cut guards and native reference contracts |
| `m1-m3-regression-20261103.xml` | 36 passed: final execution-store checks, native checkpoint round trips, existing worker integration and design-quality gates |

The three failures in the 27-case native baseline are the curved hollow
pipe/flange union, a native Boolean cut rejection for the flush R60 cutter, and
the strict opening-boundary guard for the extended R60 cutter. The aligned,
extended alternatives pass within that run.
Preserve the failing cases and the pre-mutation guards.

### Helical volume discrepancy

The original coil expectation assumed a section normal to its helical centerline.
Pinned native source establishes a screw sweep preserving an axial section:
[`crates/kernel/src/helix.rs` at v0.28.0](https://github.com/tangency-labs/solidcraft/blob/v0.28.0/crates/kernel/src/helix.rs).
The corrected independent expectation is section area multiplied by angular
travel and centroid radius.

For diameter 20 mm, circular section diameter 2 mm and two turns, expected volume
is 394.7841760435743 mm³. Measured STEP volume is 394.77209972864836 mm³ at pitch
10 mm and 394.7720997286416 mm³ at pitch 12 mm: relative error about 0.00003059.
The 0.00001 qualification threshold remains unchanged. Native source constructs
interpolated B-spline walls. Integration targets from 1e-6 to 1e-12 converge to
the same discrepancy: the last two volumes are 394.77209972864836 and
394.7720997142569 mm³. The cause therefore precedes this numerical integration,
in construction or export. A failed volume assertion alone cannot
establish the maximum positional error or disqualify every helical configuration.
Neither dimensional qualification of drawing 90 nor a production workaround has
been established by this case.

The native alternatives in `tools/cad_coil_diagnostics.py` were run explicitly
and retain strict failed assertions: quarter-turn construction and composition
(`coil-quarters-20261103.xml`), and four/eight-arc custom sections
(`coil-profile-arcs-qualified-20261103.xml`). These experiments do not resolve
the volume error. The user subsequently requested an isolated native-source
correction of 0.28.0. The source-built baseline reproduces the installed volume
exactly (`coil-source-baseline-rerun-20261103.xml`). Candidate qualification is
separate from selecting a new runtime for BigBrain; the installed binary remains
the application baseline during these checks.

#### Isolated 0.28.0 native correction

The correction and reproduction instructions are retained in
[`tools/native`](../tools/native/README.md). The source is pinned to
`ee6b85605a32948bcbd9ae437a564cab826689ec`. The candidate uses 24 samples per
profile segment and 48 stations per turn, retaining the existing station cap,
native feature history and file format. The source-built unmodified baseline
reproduces the original discrepancy exactly. Both interpolation directions
contribute error. A first 24/24 candidate passed the external matrix but failed
the additional angular-area regression at three turns; its evidence remains in
`coil-candidate-24-20261103.xml`.

The final candidate passes three native kernel tests, including the section and
angular-area regression. `coil-candidate-48-20261103.xml` has 10 passing tests:
seven circular-section configurations, the original coil regression and two
checkpoint-integrity cases. The matrix covers 0.25, 0.5, 1.25, two, three and seven
turns, differing diameters/sections and both pitch signs. Each matrix case checks
construction, pitch editing and native reopening using independent STEP volume,
one closed solid and the unchanged relative 1e-5 threshold. On the original case,
the measured volume becomes 394.78389735106896 mm³, relative error 7.0594e-7.

`coil-candidate-integration-20261103.xml` has 14 passing tests: progressive
controller cases, aligned guarded bore paths, curved rectangular sweep and bore
mouth finishing. These cases use the candidate only through process-local
executable selection. The candidate SHA-256 is
`866a8ded1f66e0fbd6f01d6046502b2a62e98da6403c127edfdbce8a8e7a549e`.
The machine-local source/build manifest is
`/mnt/cold-hdd/bigbrain-local/solidcraft-helix-028/qualification.json`.

Precision has a measured execution cost: the seven-turn case takes 156.5 seconds
for all three captures, including editing and reopening; the complete ten-test
campaign takes 383.9 seconds. High-turn performance, other section families,
complete drawing 90, full upstream CI and Windows execution remain open. The
machine-local configuration now selects the corrected headless executable for
new server processes. Existing servers require a restart; the original
installation and desktop GUI remain available. The desktop kernel retains its
original interpolation and needs separate helical editing qualification.

### Executable-bound recovery

The shared adapter fingerprints the executable before launch and verifies it
again after initialization. Checkpoints bind their accepted native prefix to
that SHA-256 and native version. Recovery and execution reject another build
before accessing the native document. Captured revisions carry the same identity;
automatic editing checks it before reopening the retained revision. Existing
records remain readable; execution of records without a build identity requires
a fresh candidate. No implicit rebinding or rewriting of accepted evidence occurs.

`engine-build-installed-gates-20261103.xml` has 106 passing tests on the stable
isolated installation, covering contracts, execution, controller, checkpoint
round trips, worker integration and native transport/captures. The published
revision cases include missing and mismatched fingerprints with preservation of
the prior piece. `engine-build-native-20261103.xml` passes the actual original/
corrected binary comparison: cross-build recovery is rejected, then the original
binary successfully recovers its checkpoint. Version-scoped guidance now also
uses executable identity to distinguish the qualified helix build. Frontend tests
remain 165 passing; type-check and production build pass. Windows execution
evidence remains pending.

### Remaining operation paths

The four supplied complex drawings require additional variants and interactions:
rounded flange profiles, finishing around actual curved junctions, reinforcing
ribs and their joins, hollow rectangular ducts and flanges, and drawing 90's
helical profile/runout/root finishing. Simple-family successes remain reusable
baseline evidence. These complete paths are still open.

## Progressive construction and Atelier integration

The [drawing 42 live report](CAD_PROGRESSIVE_LIVE_20261104.md) records five accepted
native steps, the corrected authorization/reference/workflow handoffs, the native
axis-origin parser defect, and the measured datum-axis alternative. Complete-part
qualification remains open; the retained candidate exhausted its confirmed native
repair allowance.

New confirmed CAD definitions now use `cad_controller.py` in the worker.
Retained legacy recipes and existing-document edits keep their recorded entry
path. A resumed progressive candidate retains its accepted native prefix,
including when interrupted after inspection planning.

```text
Confirmed definition + versioned native references
                    |
             Model decision
          /         |          \
     read tools   observe     execute group
          \         |          |
             next decision     solver/provenance/cut checks
                               |
                         native checkpoint
                               |
                  revise ancestor / next group / complete
                               |
                 independent whole-part inspection
                       /                 \
                measured failure       all checks pass
                       |                 |
              same step controller    delivery + Atelier
```

The protocol supports reference reads, revision-bound observations, execution
groups, ancestor revision, completion and explicit blockage. Sketch groups end
at solver checkpoints. Finishing groups contain one operation; fillet, chamfer,
shell and draft require current body-topology observations. Changing an accepted
driving parameter or editing an accepted sketch requires explicit revision. Root
revision rebuilds the sequence and preserves earlier evidence. Tool references
persist with the native catalog digest.

The execution store binds native states to the contract and engine, rejects stale
bases, checks native bytes and observed identity on recovery, and requires recovery
after failed or interrupted execution. Timeline execution time (`ms`) is excluded
from identity comparison; raw traces retain it. Native command failures and measured
inspection failures return to the same controller within the cumulative repair
allowance. The complete-part delivery gate remains enforced.

Decision context retains confirmed dimensions and unresolved requirements,
accepted-step purposes, parameters and solver summaries. Full native design and
body-topology observations are available through read decisions. Current limits
are 64 cumulative construction commands, 64 driver decisions, a 256 KB decision
packet and the confirmed worker deadline. Resumptions retain consumed decision
and repair counts. Broader workload qualification remains open.

`cad_native_compat.py` exposes version-scoped alternatives, qualified examples,
invariants and retirement cases. Its scope is the observed configurations.

The Atelier receives construction phases, current step purpose, accepted-step
count and checkpoint identity through normal run events. It distinguishes ongoing
work, retained intermediate states and final verification. The revision preview
remains tied to captured geometry. Running servers need a backend restart to load
the changed worker.

Qualification uses prepared model decisions with the actual native engine.
`progressive-qualification-20261103.xml` contains 77 passing backend tests,
including inspection interruption/resume and precise-geometry observations.
The full frontend suite has 165 passing tests, and type-check/build passes. Live model
efficiency and the remaining complex drawings still require qualification.
Windows native execution remains unqualified.

```text
Installed command catalog
        |
        +--> Native descriptions and typed schemas, where available
        |
        +--> Worker access policy and scope gaps
        |
        +--> Isolated operation cases --> Parameter-edit cases
                                          |
                              Interaction and failure cases
                                          |
                              Agent-driven drawing campaigns
```

## Evidence states

Track discovery and execution separately for each command. The inventory records
native presence, description availability, current worker scope, isolated
execution, geometric checks, parameter editing and combined execution. Every
execution claim needs a named case, native catalog digest, platform, expected
result, actual observation and artifact reference. A passing case supports its
tested configuration. Additional configurations retain their own evidence state.

Use `untested`, `passed`, `limited`, `failed` and `unavailable` for qualification
cases. An intentionally inapplicable check requires a reason. Engine diagnostics,
invalid harnesses and geometric failures must remain distinguishable. Preserve
prior failed cases when a correction passes.

## Milestones

| Phase | Deliverable | Completion evidence |
| --- | --- | --- |
| 1. Inventory | Every installed command, including excluded namespaces and unknown future namespaces | Catalog accounting, native descriptions, scope matrix and digest |
| 2. Access coverage | Classify geometry, inspection, organization, file access, desktop and application operations | Explicit access decisions and regression tests; mutation scope stays enforced |
| 3. Isolated qualification | Representative cases for every supported operation family | Independent geometry expectations, saved model, solver state where relevant and parameter-edit regression |
| 4. Interactions | Feature chains and object-reference lifecycle | Generated identities, renaming, suppression, rebuild, rollback and geometric boundary cases |
| 5. Agent qualification | The specialist chooses tools and builds from language and drawings | Observed discovery, complete measured result, usage ledger and accurate Atelier state |

## Family matrix

The native namespace inventory is exhaustive for the captured installation.
The families below organize execution cases. Their individual command variants
remain visible in the inventory, including those awaiting worker support.

| Family | Representative qualification obligations | Current evidence |
| --- | --- | --- |
| Sketch geometry | Lines, arcs, circles, conics, splines, closed/open profiles and 3D paths | Pending family-wide case set |
| Sketch constraints and dimensions | Independent constraints, driving/reference dimensions, remaining DOF, conflict diagnostics and edits | Existing workflow regressions; broader variants pending |
| Construction geometry | Offset/angled planes, axes, points and downstream references | 19 commands in worker scope; one offset-plane/sketch/extrusion edit case passes; remaining variants pending |
| Primitives | Box, cylinder, sphere, cone and torus; dimensions, analytic volume and edits | Five Linux isolated cases pass |
| Extrusion and revolution | Solid/hollow profiles, angle, axis, depth, direction and profile selection | Extrusion and full revolution cases pass with parameter edits; broader variants pending |
| Sweep, pipe and loft | Section/path alignment, hollow passages, continuity, wall thickness and edits | Straight profile sweep, straight/quarter-bend hollow pipes and two-section loft pass; curved pipe/flange union fails |
| Helical geometry and threads | Pitch, turns, handedness, section, runout and edits | Pending |
| Boolean operations | Join, cut and intersection, overlap, touching boundaries and rollback | Three box cases and a straight pipe/flange union pass; curved pipe/flange union fails |
| Patterns, mirrors and transforms | Feature/body variants, count, spacing, direction and identity preservation | Rectangular body pattern and body mirror pass with parameter edits; other variants pending |
| Holes and recesses | Placement, through/blind depth, counterbore/countersink and target selection | Drawing 42 exercises holes; naming lifecycle exposed a failure |
| Fillets, chamfers, shell and draft | Local radii/angles, thickness, edge selection and rebuild | Constant-radius edge fillet, equal-distance chamfer and open box shell pass with parameter edits; other variants pending |
| Ribs, webs, emboss and face edits | Thickness, termination, local geometry and preserved dependencies | Pending |
| Surfaces and repair | Patches, trims, offsets, joins and conversion/closure | Native surface namespace inventoried; worker scope pending |
| Sheet metal | Bends, thickness, relief, unfolding and refolding | Native sheet namespace inventoried; worker scope pending |
| Assemblies and motion | Occurrences, joints, constrained motion and contacts | Native namespaces inventoried; separate worker scope pending |
| Parameters, history and organization | Expression graph, names, groups, suppression and topology references | Existing workflow regressions; full interaction matrix pending |
| Inspection and artifact delivery | Local measurements, units, native save/reopen, STEP/STL and preview | Existing metrology and integration regressions; per-family coverage pending |
| Rendering and application services | Views, appearance, materials, files and diagnostics | Fully inventoried; access decisions remain capability-specific |

## Captured installation, 2026-11-02

- 553 commands across 41 namespaces; all 553 descriptions were read.
- 76 commands expose an input JSON schema. Other commands expose textual parameter docs.
- 174 commands passed the initial geometry/organization worker allowlist.
  Correcting the construction namespace brings the current count to 193.
- Catalog digest: `e8f51a4260742c89d2f95d269eaa7a49460dd60255894cf1d13123c9d4c5950d`.
- The native `construct.*` namespace replaces the erroneous `construction.*`
  worker prefix. Regression tests preserve the file-operation boundary.
- Native inventories and generated models live on this machine under
  `/mnt/cold-hdd/bigbrain-local/cad/`. Portable code uses explicit output paths.
- Windows native execution remains unqualified.

The initial nine isolated cases use independent analytic volume and extent
expectations. Each saves an initial and edited native candidate, verifies one
closed body and checks a parameter change. They cover five primitives, three
Boolean operations and an offset plane with a downstream dimensioned sketch and
extrusion. The latter also checks the absolute solid position after editing the
plane offset. Primitive fixtures exercise native operations; professional
construction retains its separate solver and design-intent obligations.

The first local runs passed 35 inventory/discovery/workflow/integration
regressions and nine measured native cases. The expanded operation set contains
21 cases: 20 pass, and the curved pipe/flange union fails. Machine-readable
results preserve both outcomes in the machine-local CAD evidence directory.
No model calls were required.

## Expanded operation results

The 20 passing cases cover the original nine cases, two hollow pipe paths, full
revolution, shell, a straight pipe/flange union, fillet, chamfer, rectangular body
pattern, two-section loft, straight profile sweep and body mirror. Every passing
case checks the initial geometry and a parameter edit against analytic volume
and extent expectations. The tests retain native models, exported geometry and
measurement provenance. Professional sketch constraint coverage remains a
separate obligation for cases built from direct coordinate expressions.

A first revolution fixture passed an expression directly to a rectangle point;
the native API rejected that input. The corrected fixture uses numeric seed
coordinates and a driving width dimension. Its geometric expectations remain
unchanged. Both test runs remain available.

### Curved pipe/flange union

The minimal failing case joins a hollow quarter-bend with a straight lead-in to
an annular flange overlapping that lead-in. A matching straight-pipe case passes.

| Check | Observed result |
| --- | --- |
| Pre-union native bodies | Two closed bodies |
| STEP validity and independent inspection | Passed before the union |
| Native 0.28.0, ordinary 30-second ceiling | Timeout |
| Native 0.28.0, isolated 120-second allowance | Union error after about 105 seconds |
| Native 0.30.1, same saved candidate, CLI comparison | Same union error after about 100 seconds |
| Independent OpenCascade union on the same STEP | Valid result in about 1.14 seconds |
| Independent result volume | 1982.7064938 mm³ |
| Analytic expected volume | 1982.7062734 mm³ |

This local comparison isolates a native Boolean/representation limitation for
the tested candidate. It provides no general verdict on all curved Boolean
operations. BigBrain continues to use the qualified 0.28.0 adapter; the 0.30.1
comparison uses the already downloaded binary separately. The independent union
is a diagnostic and has no production construction fallback role.

Evidence under `/mnt/cold-hdd/bigbrain-local/cad/`:

- `operations-qualified-20261102-results.xml`: 20 passing cases, with the failing
  curved union explicitly excluded from that run.
- `operations-curved-union-extended-20261102-results.xml`: failing curved case.
- `operations-curved-union-extended-20261102/test_native_pipe_flange_union_0/`:
  pre-union native model, STEP inspection, native tool trace and independent
  kernel diagnostic.
- The same case directory contains `native-0301-union-diagnostic.json`, recording
  the separate newer-engine comparison.

The full 21-case operation qualification remains failing until this case is
resolved. The failure stays asserted in the test suite.

### Follow-up: native feature-order workaround

The [Boolean investigation](CAD_NATIVE_BOOLEAN_LIMITATION.md) locates the native
intersection-loop failure and records a dimension-preserving native alternative.
Exterior-first union followed by an extended bore cutter passes at R30/R60 and
after edits to R36/R66, including local material probes and saved history.
The flush-ended bore alternative still fails at R60. The suite now contains
25 cases; original failing routes remain asserted. The specialist's automatic
choice of the successful alternative and the complete drawing remain open gates.

## Reproduction

Use a fresh output directory for every run to retain previous evidence.

```sh
PYTHONPATH=. .venv/bin/python tools/inventory_cad_capabilities.py --output /absolute/new/inventory
.venv/bin/python -m pytest tests/test_cad_operation_qualification.py -q -p no:cacheprovider --basetemp=/absolute/new/cases
```

Pytest owns and may clear its `--basetemp` directory. Reserve a new dedicated
directory for that command. Store personal models elsewhere.

Native operation tests require SolidCraft and the CAD measurement dependencies.
The generated inventory reports description failures independently of mutation
qualification. Reading a catalog neither changes the worker allowlist nor
establishes agent competence with the corresponding tools.
