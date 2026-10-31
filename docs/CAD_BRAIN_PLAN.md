# CAD brain and Atelier integration

30 October 2026. Implementation on `feat/cad-brain`.

## First deliverable

A dedicated CAD brain uses the qualified SolidCraft engine to create and edit
small dimensioned parts headlessly. The Atelier shows the actual piece, its
revision, dimensions, checks and artifacts. Native documents retain editability;
The Atelier can enlarge a revision-bound PNG and download its native document.
Direct desktop GUI launch and an orbitable 3D viewer remain extensions.

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

## Implemented journey

```text
Chat request → typed CAD route → measured recipe and criteria
                                      ↓
                            immutable contract / user decision
                                      ↓
                    bounded SolidCraft headless session
                                      ↓
             native save + geometry measurements + STEP/STL + PNG
                                      ↓
                    criterion checks → revision publication
                                      ↓
                  Atelier piece surface / scoped downloads
```

The dedicated CAD brain executes the recipe stored in the selected contract.
An edit reopens the exact native revision, checks its hash and publishes through
a revision comparison. Failed checks preserve the previous published revision;
engine and criterion observations remain available in the capture directory.
Conversation-scoped `cad.list` and `cad.read` provide focused lookup.

`BIGBRAIN_SOLIDCRAFT_CLI` selects the engine executable. `BIGBRAIN_CAD_DIR`
selects the application-owned artifact store. Sessions serialize engine calls,
bound their duration and output, and retire the subprocess after cancellation
or a transport failure. The worker has a 120-second execution deadline.

### Verification checkpoint

- Backend campaign: 2,132 passing tests and eight skips across two groups.
- Final CAD supplement: 57 passing contract, adapter and integration tests.
- Frontend: 146 passing tests; production build succeeds.
- Actual SolidCraft 0.25.1: plate, enclosure, parameter edit, failed batch
  rollback, native reopen and STEP round trip exercised on Linux.
- Browser: contract decision, actual piece rendering, enlargement, STEP download
  and history restoration after server restart exercised in isolated stores.

### Model-led browser probe

On 30 October, an isolated browser journey used Codex Sol 6.1 low with a
three-call, three-minute ceiling. Two model calls selected `cad_brain` and
prepared a parametric recipe for a new 60 × 40 × 6 mm plate. After the contract
decision, SolidCraft created one closed body with measured volume 14,400 mm³.
All four proposed geometric criteria passed. Native, STEP, STL and PNG artifacts
were published and the Atelier displayed the actual revision. Confirmation in
the chat required no additional model call.

Evidence root: `/tmp/bigbrain-cad-ui-x8o9k1my`; screenshot:
`/tmp/bigbrain-cad-live-atelier.png`. The front decision took 7.7 seconds and
reported 7,607 input / 179 output tokens with zero cached input. Planner token
usage was not persisted by this harness, so complete probe usage remains unknown.
The initial harness launch lacked the Codex executable on PATH and stopped
before inference; selecting the installed extension binary resolved that setup
issue. The isolated server uses a synthetic bus configuration; authenticated
production bus behavior remains covered separately by the backend suite.

### Current limits

Qualification covers Linux and small dimensioned solids. Windows subprocess
support requires native qualification. The current document store owns newly
created CAD projects; importing attached CAD documents requires a separate access
contract. Photos, uncertain dimensions, wall-thickness analysis and physical
strength checks require additional capabilities. Failed jobs stop with evidence;
automatic CAD repair, storage quotas and capture cleanup remain future work.

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
