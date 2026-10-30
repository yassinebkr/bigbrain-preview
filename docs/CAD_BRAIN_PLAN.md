# CAD brain and Atelier integration

30 October 2026. Next implementation cycle after attached local projects.

## First deliverable

A dedicated CAD brain uses the qualified SolidCraft engine to create and edit
small dimensioned parts headlessly. The Atelier shows the actual piece, its
revision, dimensions, checks and artifacts. Native documents retain editability;
GUI handoff opens an explicitly saved revision.

## Phases and milestones

| Phase | Work | Exit evidence |
| --- | --- | --- |
| 1 — Artifact and action contract | Define native document, units, revision, geometry checks, preview provenance, exports and bounded actions; reuse project grants and recipient/source consent | Versioned schemas and offline lifecycle tests, including stale previews and interrupted mutations |
| 2 — SolidCraft adapter and CAD brain | Persistent bounded headless sessions, typed commands, state inspection, cancellation, save/reopen and rollback; shared routing and evidence | Real plate, enclosure, parameter-edit and failed-operation cases; preserved prior revision |
| 3 — Atelier piece surface | Compact expandable piece preview, dimensions, current operation and verification; artifact actions and optional GUI handoff | Frontend tests and browser journeys with actual CAD artifacts; reload, task switching, failure and stale-state coverage |
| 4 — End-to-end acceptance | Model-led creation and modification through the frontend, with explicit criteria and scoped disposable projects | Dimensions, solid validity, export/reopen, preview/revision agreement, cancellation and recovery verified |

## Boundaries

- CAD has a dedicated brain and tool contract. Python and web brains retain their roles.
- Geometry claims require measurements from the actual engine result.
- Every preview references its document revision; pending or failed updates remain visible.
- Native platform operations use adapters under the shared Linux/Windows contract.
  Qualify each supported capability on its target operating system.
- Photos and diagrams require a later scale/uncertainty contract. Printer control,
  continuous GUI mirroring and broader shared-focus architecture remain deferred.

Existing engine evidence: [SolidCraft qualification](SOLIDCRAFT_QUALIFICATION_20261029.md).
Access foundation: [attached local projects](LOCAL_PROJECTS_PLAN.md).

## First milestone checkpoint

[Artifact and lifecycle contract](CAD_ARTIFACT_CONTRACT.md) defines document,
geometry, criterion, export and preview records. `bigbrain/cad_contracts.py`
implements their immutable schemas and delivery/state-transition gates.
The 48-case offline suite covers revision binding, missing or failed criteria,
invalid geometry, required exports, portable references, stale previews and
terminal outcomes. Adapter measurements and frontend acceptance follow in
phases 2–4.

## Deferred workspace redesign

The BigBrain workspace and local-folder workspace currently use inconsistent
visual languages. Both require a usage-led redesign; the current presentations
remain unsatisfactory to the user.

Scope: a shared design system, consistent project navigation and hierarchy,
readable permissions/status, coherent file and artifact actions, and domain-specific
surfaces for code, CAD and other deliverables. Preserve origin, identity and access
boundaries throughout the unified experience.

Schedule this as a separate UX cycle. The CAD cycle adds its piece surface within
the Atelier and records integration friction for that redesign.
