# CAD web integration and qualification

The corrected observation/editor contract and newly established blocking causes
are recorded in [Integration reassessment](CAD_WEB_INTEGRATION_REASSESSMENT.md).
Phase 3 remains open under that corrected contract.

## Scope and order

1. Integrate the pinned SolidCraft 0.28.0 browser application into BigBrain.
2. Qualify one or two additional user-supplied drawings.
3. Qualify simple assemblies.

Multi-user infrastructure, billing, administration and product pricing remain a
separate architecture discussion. See `MAKER_PRODUCT_DIRECTION.md`.

## Phase 0 — Close the tracking change

Review the existing tracking changes and evidence. Confirm that current delivery,
global status and attempt history agree after reload and event replay. Preserve
unrelated working-tree changes. Prepare the commit and push; merge follows the
user's explicit instruction.

Milestone: a recorded baseline with passing frontend checks and the scope of the
reconstructed browser fixture stated explicitly.

## Phase 1 — Qualify browser execution

Recorded results and open limits: [Phase 1 qualification](CAD_WEB_PHASE1_QUALIFICATION.md).
The two document round trips pass; synchronous UI blocking and actual WebGPU
qualification require resolution before seamless integration.

Build a version-pinned 0.28.0 browser distribution in an isolated location. Record
source revision, patch set and build identity. Serve assets locally and run the
engine on the client. Use disposable copies of the validated plate and drawing
42 documents. Compare native and browser load, feature history, parameter edit,
undo/redo, save and reopen. Compare geometry through the established measurement
adapter. Check the native helix patch separately if included in the web build.

Measure cold startup, warm activation, document loading, peak memory and visible
responsiveness on the reference machine. Check WebGPU and available WebGL2
fallback behavior; report actual platform coverage.

Milestone: the browser edits and round-trips these documents with preserved
history and measured geometry. A failure produces an isolated compatibility case
before wider integration. Agree performance thresholds from these measurements.

## Phase 2 — Define the document bridge

Implemented bridge and recovery evidence: [Browser execution bridge](CAD_BROWSER_BRIDGE.md).
The isolated browser campaign covers command execution, lost acknowledgements,
full page reload, manual save/resume and stop. The Atelier host and CAD-brain
workflow integration follow in Phase 3.

Production direction: BigBrain orchestration, model access, planning, repair
policy and proprietary decision logic run on the server. The client browser
executes SolidCraft geometry commands through WebAssembly and renders through
WebGPU, with the supported fallback. The server sends scoped command requests;
the browser returns observations and revision identities. Keep the client bridge
small and expose only what local execution requires. Commands and client-side
code remain inspectable. Account authorization and credit accounting stay under
server authority.

Browser suspension or disconnection can interrupt CAD execution. Persist accepted
checkpoints and resume through an explicit acknowledgement protocol. The existing
native adapter provides qualification comparisons and a development fallback.
The placement of independent metrology requires capability qualification and an
explicit decision; client-reported checks alone cannot establish server-trusted
verification in an adversarial environment.

Use a shared adapter contract for load, inspect, execute, observe, checkpoint and
save. Keep document identity, revision and hash in every relevant exchange.
Declare capabilities for native and browser implementations.

Target boundary: server-directed agent work and manual editing share one browser
document with explicit ownership. Manual editing obtains ownership after agent
execution pauses. Saving produces a new candidate revision for verification.
Qualify the browser execution adapter before transferring the agent workflow.

Handle outdated responses, cancellation, reload, interrupted saves and attempts
to edit concurrently. Validate message origin and the session/document scope of
the bridge. Keep application state across ordinary workspace switches. Account
for browser suspension rather than assuming background execution continues.

Milestone: one authoritative document revision, explicit edit ownership and
recovery of the last accepted checkpoint under injected interruption cases.

## Phase 3 — Embed SolidCraft in the Atelier

Implementation and qualification boundaries: [Atelier browser editor](CAD_ATELIER_BROWSER.md).

Provide a compact switch between the Atelier preview and the full editor within
BigBrain. Preserve document, camera and UI state during normal switches. Load the
web application on demand and retain the initialized instance within an explicit
memory policy. Show loading and actionable errors when initialization fails.

Test compact and expanded layouts, keyboard focus, resize, switching between
projects and returning to the chat. Measure warm switching against the agreed
threshold. Verify Linux and Windows browser behavior on available hosts.

Milestone: direct access to the correct editable document in BigBrain, with
consistent state after repeated switches and a documented platform matrix.

## Phase 4 — Progressive 3D and sketch views

Visual continuity is a requirement. Keep the viewer mounted, preserve the camera
and user interaction, and prepare incoming geometry before an atomic scene update.
Reuse stable scene objects where identity permits. Animate additions and removals
with short transitions; avoid whole-scene clearing, camera resets and visible
blank frames. Topology changes require a geometry-aware transition or a restrained
fade; interpolating arbitrary vertex arrays can create misleading intermediate
shapes. Animation is presentation and carries no measurement evidence.

Use local animation frames independently of agent turn cadence. Show available
accepted operation observations progressively; batching must not imply access to
unobserved intermediate geometry. Keep transitions interruptible and coalesce
obsolete observations. Respect reduced-motion preferences. Record frame times,
input responsiveness and update latency on reference hardware and representative
models, and agree numeric targets after the browser baseline measurements.

Publish observations after accepted construction steps. Bind mesh, sketch data,
feature name and progress to the same checkpoint identity. Provide the requested
discrete 3D / sketches + 3D switch. Intermediate construction remains visibly
in progress; final delivery uses the existing verification gate.

Coalesce obsolete preview work to prevent rendering from delaying construction.
Retain the last accepted observation on failure and explain rollback. Establish
whether the pinned engine exposes the required sketch representation; qualify
that capability before promising all sketch views.

Milestone: replay real retained steps, then run a small live construction. The
visible part evolves smoothly, view modes refer to the same step, and
reconnect/rollback preserves coherent state. Verify camera continuity, absence of
blank frames, interaction during updates and reduced-motion behavior. Record
observation overhead and frame-time measurements.

## Phase 5 — Additional drawing campaign

Choose one or two of the drawings already supplied. Proposed pair: drawing 83
and the rectangular elbow, covering different features and hollow geometry.
Drawing 90 remains a separate helix case with its interpretation requirements.
The user confirms selection and any missing dimensions before execution.

Freeze each contract and use the normal UI path. Record model usage, accepted
steps, interventions, failures and final measured results. Diagnose and replay
each failing case locally before another paid attempt. Preserve tolerances,
requirements and editable feature history.

Milestone: each selected case has a traceable verdict on required dimensions,
local details, topology, exports and editable history. Report operator assistance
separately from autonomous completion. Explicitly record any unresolved case.

## Phase 6 — Simple assemblies

Qualify the pinned engine's component, instance and placement-constraint tools.
Start with an enclosure, lid and repeated fasteners. Preserve reusable component
definitions, per-instance transforms and source revisions. Verify placement,
specified clearance, interference and propagation of a dimensional change.
Prepare the data model for joints; qualify articulated mechanisms subsequently.

Milestone: an editable assembly that survives save/reopen and a component change,
with reproducible placement and interference evidence.

## Execution discipline

Use offline qualification and retained checkpoints before paid campaigns. Define
each live batch from the work remaining and retain a repair/inspection margin.
Stop repeated failures that provide no new evidence and isolate their cause.
Changes to scope, engine version or document authority require an explicit
decision. Keep documents and code comments in English. Preserve the native and
browser adapters as replaceable implementations of shared contracts.
