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
