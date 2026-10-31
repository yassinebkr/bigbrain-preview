# CAD artifact and lifecycle contract

30 October 2026. First integration milestone; runtime wiring follows separately.

## Identity and observations

| Record | Required content |
| --- | --- |
| Document revision | Project ID, document ID, increasing revision, native artifact hash, engine/version and units |
| Artifact | Project-relative canonical path, format, byte size and SHA-256 |
| Geometry observation | Matching native hash, body count, closed-solid status, bounds in mm and volume in mm³ |
| Criterion observation | Criterion ID, outcome, diagnostic and evidence reference bound to the same native hash |
| Preview | Matching document/revision/hash, image artifact and render dimensions |

The runtime assembles observations from actual tool responses and captured files.
Schema validation checks consistency; engine measurements and artifact reads
establish the evidence. The initial runtime owns new CAD documents and scopes
artifact access to their conversation. Attached-document imports require the
project broker integration planned for a later cycle.

## Lifecycle

`queued → modeling → checking → ready`

Active work can end as failed, cancelled or blocked. A checking failure can return
to modeling within the existing run budget. A new user request creates a new run
bound to the previous document revision. Terminal runs retain their outcome.

Successful mutations advance document revision. Failed or interrupted mutations
require state inspection before another mutation; uncertain state blocks the run.
Publication uses a CAD revision comparison and an atomic current-revision pointer,
preserving prior revisions in the application-owned store.

## Delivery gate

For the initial closed-part scope, a ready result requires:

- An editable native document and observed geometry for its exact hash.
- At least one body, closed-solid status and positive finite dimensions/volume.
- Exactly one passing observation for each required criterion, with evidence.
- Every contract-required export captured and bound to the delivered revision.

Preview availability has its own state: current, stale, pending, failed or absent.
A preview becomes current only when its revision and source hash match the piece.
The Atelier can retain an older image with a visible stale indication during edits.
Rendering failures remain visible alongside the geometry and delivery outcome.

## Tools and platform boundaries

- Read actions inspect commands, document state, measurements and existing artifacts.
- Mutations use typed SolidCraft commands in bounded batches with strict parameter checks.
- Save, export and render paths are allocated inside runtime-owned scratch storage.
  Attached-project publication remains a later integration with project grants.
- Direct GUI handoff requires a platform adapter in the next CAD cycle.
- Timeouts and Stop terminate owned work and trigger state reconciliation.
- Linux and Windows use the same artifact, lifecycle and evidence contracts.
  Native launcher/isolation capabilities require separate platform qualification.

## First acceptance cases

Dimensioned plate, enclosure, parameter edit, invalid-operation rollback, native
save/reopen, export round trip, stale preview, interrupted work, failed criterion,
revoked access and task-switch/reload continuity. The offline contract gate covers
identity and lifecycle rules; adapter and UI gates exercise actual geometry.
