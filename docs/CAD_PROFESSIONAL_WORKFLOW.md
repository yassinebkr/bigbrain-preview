# Parametric CAD workflow

## Qualification status

SolidCraft 0.28.0 on Linux supports the required native construction tools.
The design-intent gate passes direct native and worker edit qualification.
The worker preserves the latest delivered revision when design intent fails.
The staged drawing route passes deterministic-provider qualification with the
native engine: confirmation precedes construction and inspection receives the
captured artifact hash and native body topology.
Windows native qualification remains open.

| Capability | Evidence |
| --- | --- |
| Named parameters, expressions and canonical units | Native parameter import and dependency graph |
| Constraint solver | Both plate sketches report solved, zero remaining degrees of freedom |
| Constraint rejection | Native audit rejects redundant and conflicting constraints while preserving the sketch |
| Unit and dependency integrity | Native audit rejects incompatible units and cyclic parameter definitions |
| Editable history | Parameter edit preserves the four feature IDs and names |
| Organization | Saved native document contains exact history, sketch and body group membership |
| Persistence | Reopened second revision passes the same design-intent checks |

## Runtime sequence

```text
Confirmed dimensions and design intent
                  |
       Atomic native parameter import
                  |
       Profile and geometric relationships
                  |
       Functional driving dimensions
                  |
   Finish sketch, inspect native solver
                  |
       Extrusion or next feature
                  |
   Solver + dependency + inventory checks
                  |
  Resolve native IDs, group, hide profiles
                  |
       Save exact candidate artifact
                  |
   Saved membership + geometry inspection
                  |
      Delivery gate / bounded repair
```

`CadWorkflow` records parameter provenance and dependencies, sketch freedom,
feature purposes, body names and group membership. Zero degrees of freedom is
the default; intentional freedom requires an explanation. Fixed curves fail
the quality gate. Primitive-only construction requires a rationale.

The runtime checks native parameter expressions and values, graph errors,
sketch solver state, active history and named inventories. It inspects group
membership inside the saved `solidcraft/45` artifact. Sketch browser groups use
string feature IDs; passing sketch names can silently produce an empty group.

## Sketch construction checkpoints

The construction guidance orders profile geometry, independent geometric
relationships and functional driving dimensions. Drawing helpers already create
constraints; construction recipes must account for those relationships before
adding dimensions. Derived annotations use reference dimensions.

`SolidCraftSession.construct` validates the complete command inventory, then
executes through each `sketch.finish`. It observes the native sketches and checks
solver status, remaining freedom, curve fixation and dimensional intent before
continuing to the next solid operation. A rejected checkpoint supplies a
`sketch_quality` diagnostic to the existing candidate repair loop.

Each segment retains native batch rollback. Earlier successful segments belong
to the private candidate; repair starts in a fresh session from the original
revision. The delivered revision changes only after the delivery checks pass.

Coordinate expressions alone no longer satisfy dimensional intent. A fully
constrained drawn profile requires an observed driving dimension or projected
reference. This is a minimum structural check: the later geometry inspection
still establishes whether every required dimension and local feature is correct.

The native plate qualification changes length and hole diameter, verifies the
hole position and radius, preserves feature identity and organization, then
saves and reopens the result. Additional tests verify that an underconstrained
profile stops execution before extrusion and that coordinate-only profiles fail
the dimensional-intent check. These checks qualify the construction mechanism;
the drawing 117 candidate and measurement tools retain their separate gates.

Phase 1 focused qualification on Linux: 30 tests pass across
`test_cad_workflow.py`, `test_cad_integration.py` and `test_solidcraft.py`.
The native tests use the currently integrated SolidCraft 0.28.0 installation.
SolidCraft 0.30.1 migration and Windows execution remain separate qualifications.

## Reproducible edit qualification

Run `pytest tests/test_cad_workflow.py`. The native edit test performs the
following sequence:

1. Build a constrained 60 × 40 × 6 mm plate with an 8 mm through-hole.
2. Save and reopen its native document.
3. Change the length to 80 mm and the hole diameter to 10 mm through parameters.
4. Observe the hole center at (40, 20) mm and its radius at 5 mm.
5. Verify feature identity, exact group membership and solved sketches.
6. Save and reopen the edited artifact and repeat the quality checks.

The suite also rejects unexplained freedom, incomplete grouping, unknown or
cyclic dependencies, incompatible native units, fixed-curve observations and
unexpected remaining degrees of freedom. Its worker test confirms that a failed
quality gate preserves the latest delivered revision. The staged drawing test
uses deterministic model responses and actual native geometry; model reliability
on drawing 117 remains part of the subsequent recovery plan.

## Qualification results

The full backend run completed with 2,236 passed and eight optional extractor
tests skipped. The final proposal-enforcement change has additional focused CAD
coverage: all 155 CAD and native-adapter tests pass on the final changes.
Frontend qualification: 163 tests pass and the production build succeeds.

Fresh runtime proposals require workflow design intent, including natural-language
requests. Retained contracts and explicitly precompiled test recipes remain
readable through the lower-level recipe parser.

Existing geometry-measurement fixtures explicitly request their precompiled
recipe path. Their native geometric assertions remain unchanged.

The three prerequisite gates are complete: capability audit, runtime design
rules and saved/reopened parametric edit qualification. Resume the drawing 117
recovery plan next. Manufacturing
tolerance certification, general topology-stable face references, a visual
contract redesign and native Windows qualification remain later work.
