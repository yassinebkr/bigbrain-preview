# CAD from dimensioned drawings

The front brain reads the drawing and coordinates an editable SolidCraft piece.
Dimensions retain image provenance, derivations and uncertainties throughout the
contract, execution and verification path. Existing-component portability work
follows this cycle.

```text
Image + question → vision interpretation → dimension specification
                                             ↓
                         clarification ← unresolved critical dimensions
                                             ↓
                             proposed recipe + feature criteria
                                             ↓ user confirmation
                               model → measure → bounded repair
                                             ↓
                          verified revision → Atelier + native GUI
```

| Phase | Deliverable | Completion evidence |
| --- | --- | --- |
| 1 | Versioned interpretation with source hashes, view descriptions, dimensions and questions | Explicit, derived, missing, conflicting and illegible dimensions exercise the clarification gate |
| 2 | Vision handoff and editable CAD planning | Drawing requirements bind the immutable recipe; uncertainty reaches the user before execution |
| 3 | Feature measurements and bounded repair | Hole/recess position and size checked on captured geometry; repair preserves the confirmed criteria |
| 4 | Representative validation | Clear and degraded drawings, stepped/drilled geometry, unit/conflict cases and recovery, followed by bounded browser probes |

Commits and pushes follow each completed phase. CI is reviewed before merging.
Each measurement states its actual coverage. Native Windows qualification remains
separate from shared contract tests. Detailed work and evidence are recorded below.

## Phase 1

`DrawingSpecification` records source attachment hashes and normalized image
regions, views, dimension semantics, units, annotations, derivation dependencies
and explicit clarification issues. Acyclic references and source bindings are
validated. Critical unresolved dimensions and blocking issues prevent planning.
Engineering reasoning remains a model interpretation pending geometric checks.

Perspective imagery contributes shape context; quantitative acceptance uses
dimensioned views. Low-resolution annotations require a clearer source or an
explicit answer. Approximation requires its own user-visible contract. Fits,
surface finishes and manufacturing requirements require supported checks.

Phase 1 defines the shared contract; phases 2–4 connect it to the live pipeline,
geometry evidence, repair and representative end-to-end validation.

## Phase 2

The vision message includes runtime-computed attachment identity and SHA256.
The front decision carries the drawing specification in the typed CAD input.
Before delegation, each source must match an image attached to the current turn
and its stored bytes. Unresolved critical dimensions require clarification.
The CAD planner receives the interpreted specification, while the runtime binds
the original interpretation to the resulting recipe and immutable proposal.
The proposal displays the drawing dimensions together with measured criteria.

The current source scope requires attaching the drawing to the modeling turn.
Resuming image interpretation across turns will require a conversation-owned
attachment inventory. Feature verification and repair follow in phase 3.

## Phase 3

Critical linear dimensions bind directly to measured envelope components or
material-section endpoints, lengths and gaps. Runtime validation checks the
expected value against the drawing, including inch-to-millimetre conversion.
Missing bindings block the recipe. Angular and manufacturing criteria require
additional measurement support and clarification.

Sections intersect the captured binary STL with axis-aligned lines. They check
local material and void intervals for hole position, diameter, depth, recesses
and stepped profiles. Samples retain the STL hash and native revision hash.
Triangle and interval counts are bounded. Ambiguous intersections produce an
inconclusive result. Sampling covers the specified lines; exhaustive topology
and manufacturing qualification require additional checks.

Confirmed proposals authorize at most two repairs within 120 seconds. Each
candidate begins from the approved original and receives a fresh capture.
Repair inference can change recipe commands; dimensions, source provenance,
measurement targets and export requirements remain fixed. Reproduced failures
trigger repair; inconclusive evidence stops execution. Publication occurs after
every required criterion passes. Older proposals default to zero repairs.

The planner receives the installed engine's command reference for editable
sketches, extrusions, chamfers and fillets alongside primitive operations.
Independent tests move a hole while retaining equal volume: global checks agree,
while the local section detects the incorrect position. Repair tests exercise
both successful correction and persistent failure without publication.
