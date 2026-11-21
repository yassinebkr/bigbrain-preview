# CAD construction in the Atelier

## Delivery scope

The Atelier follows accepted construction checkpoints in two compact modes.
The solid view shows the developing geometry. The construction view additionally
shows sketches, reference planes and construction elements. A separate action
opens the full SolidCraft interface in the main workspace.

The conversation owns the execution, document, revisions and evidence. Published
delivery checks remain attached to the exact verified source hash.

## Milestones

1. Persist the working presentation identity before broadcasting progress.
   Resolve its native artifact through the accepted checkpoint chain and enforce
   conversation ownership and artifact hashes on every read.
2. Present accepted checkpoints during real CAD brain construction. Preserve the
   camera and responsiveness while preparing the next geometry in a worker.
   Coalesce superseded presentation requests and reject stale completions.
3. Provide solid and construction preview modes, plus the full editor action.
   Keep one document identity across these surfaces and retain exclusive editing
   ownership during agent construction.
4. Restore the conversation's CAD runs and Atelier after server restart. Expose
   CAD checks and retained attempts through Evidence. Qualify this through the
   normal application entry point.

## Current implementation evidence

The first increment records `working-state.json` under the owned document before
progress reaches subscribers. It carries the execution context and presentation
state. Accepted checkpoint resolution validates the engine and contract lineage
and verifies observation hashes. The working artifact endpoint requires the
explicit current checkpoint and uses the existing owned-artifact reader.

The native session exports a presentation mesh while the accepted geometry is
already evaluated. The checkpoint records its hash, size and native source hash.
The solid preview reads that mesh through the conversation-owned artifact route.
A persistent Three.js viewport replaces the geometry and retains the camera,
world origin and GPU resources. Removing the final solid clears the viewport.
Published deliveries select their independently inspected published export.

```mermaid
flowchart LR
    Commands[CAD command group] --> Native[Evaluated native document]
    Native --> Checks[Intermediate checks]
    Checks --> Checkpoint[Native checkpoint and bound mesh]
    Checkpoint --> Three[Persistent Three.js solid preview]
    Checkpoint --> Worker[Qualified geometry Worker]
    Worker --> Cache[Evaluated viewer cache]
    Cache --> Construction[Native construction view]
```

Construction mode uses the qualified worker and retained native viewport to show
sketches and dimensions. Earlier checkpoints whose records contain no mesh use
the worker fallback for their solid view. Native chrome stays cropped during
view changes and appears when the full editor opens. Worker preparation remains
serialized and coalesces superseded checkpoints.

The 3D preview has separate recenter and fullscreen controls. Fullscreen contains
the model viewport and its navigation controls. SolidCraft Web expands the Atelier
and opens the interactive editor. The existing browser execution bridge controls
ownership, saves and reconnection. Hosted saves serialize the open native session.
Hosted mode delegates file persistence to BigBrain. Asset URLs include the
qualified build identity, and hosted HTML delegates update selection to BigBrain.

Live progress follows accepted command groups. Each group can contain several CAD
operations. A mesh replacement preserves camera state and the document origin.
The viewport tests cover repeated updates, malformed input, removal of the last
solid, graphics context loss and restoration, and resource disposal. Geometric
interpolation between changing topologies remains a later presentation extension.

The capability response exposes editor availability and worker preview
availability independently. A configuration diagnostic identifies a missing
qualified worker distribution. Mesh preparation errors reach the preview footer.
The existing displayed geometry remains available when a replacement is rejected.

CAD model decisions now retain a transport trace ID and duration. Inference
records identify the document, checkpoint and decision. Successful native tool
observations include their elapsed duration. The global CAD execution deadline
reports its phase and accepted checkpoint count through the normal failure and
recovery path.

Each run has a retained presentation record. Conversation history supplements
the bus journal from these records and marks pre-restart work interrupted.
Terminal CAD outcomes publish immutable manifests into the common evidence
repository with their source hashes and measured criteria.

The preview host remains mounted across overview, part and full observation
surfaces. Its camera and compact mode survive these transitions. CAD overview
widgets use one full-width column, with verification following the model.
CAD navigation exposes one primary Piece tab and a Verification tab when checks
are available. Previously retained CAD and overview routes resolve to the same
piece presentation. Preview mode selection stays visible in compact and expanded
layouts, including a return from the full observation shell.

## Qualification

The normal web application was exercised with an artificial constrained plate
and recorded provider decisions. CadBrain executed four native groups, including
the hole sketch and through cut. The browser displayed the third accepted group
while construction was still running, including the sketch and driving dimensions.
The resulting delivery passed its envelope, cut-safety and design-quality checks.
This campaign exercised transport and presentation with recorded decisions.
Model interpretation quality remains covered by the earlier CAD qualification.

After the server process ended, a new process opened the same retained stores.
The conversation reopened its Atelier and the Evidence page displayed the CAD
run and checks. Switching overview, part and full observation preserved the same
native iframe identity. The selected Construction mode survived the round trip.
DOM measurements confirmed equal model/verification widths and a verification
card below the model. Browser screenshots are retained locally under
`/tmp/cad-live-intermediate.png`, `/tmp/cad-live-construction-after-restart.png`
and `/tmp/cad-atelier-stacked-verification.png`.

The preview controls were subsequently exercised through the normal Atelier.
The 3D viewport entered fullscreen, recentered and returned to the page. The
interactive native editor opened its Create Sketch tool and saved working
revision 1 through BigBrain. Browser screenshots are retained locally at
`/tmp/cad-three-fullscreen.png` and `/tmp/cad-editor-integrated.png`.

The frontend suite passes 203 tests across 25 files and its production build
completes. The aggregate CAD, front-decision, model-role, conversation and trace
suite records 506 passing cases and three native qualification failures. The
same results were obtained with the configured isolated 0.28.0 executable used
by the server and with the PATH installation. The section/metrology/workflow/
integration/recovery subset passes 74 tests.

The normal-server drawing 42 candidate reached 26 accepted construction groups.
Revision 10 passed all 66 piece checks and the delivery gate. The inspection
recipe was reused after validating its construction identity. The replay added
zero model calls. The retained initial inspection attempt recorded 253.410 s
of backend elapsed time. The successful replay recorded 18.592 s. Their native
tool observations totalled 3.509 s and 2.999 s respectively. This comparison
combines recipe reuse and the analytic section provider. Their separate effects
require a controlled comparison. Browser presentation preparation has its own
timing scope.

After a complete server stop and restart, the normal interface retained the
piece, exports, verified status, seven historical attempts and recorded evidence. A second retained drawing is being qualified through the same
interface. Final aggregate regression remains pending.

| Native case | Observed failure |
| --- | --- |
| Quarter-bend pipe/flange union | Native union returns no result |
| Flush cutting tool at 60° | Native pipe cut returns no result |
| Extended cutting tool at 60° | The inlet opening fails the outward material boundary check |

The parameterized coil case passes in both latest aggregate runs. An earlier
campaign recorded a volume discrepancy for that case. These observations remain
associated with their recorded builds and artifacts.

Visual Front Brain intake has a separate 300 s completion window. The drawing 49
retry completed in 128.506 s with 4,932 output tokens, including 75 reported
reasoning tokens. The typed drawing dossier contributes to response latency.
The initial 120 s attempt ended before a valid decision. The second drawing
currently awaits clarification of its R8 underside relief depth.

The full native editor uses its available viewport height without flex shrinkage.
Its ribbon, document browser and native parameter dialog remain inside the
expanded Atelier surface.

## Remaining integration boundaries

The interactive editor opens after the retained run stops. Live previews retain
observation ownership during construction. Manual edits belong to the separate
browser working revision and require geometry checks before publication. The
browser campaign was observed on Linux. Windows execution remains
to be qualified against the shared behavior and storage contracts.

The existing hosted viewer and worker changes are prerequisites already present
in this worktree. The completed branch will receive one final push. Merge follows
the repository owner's subsequent review.

## Sol 6.2 stopped run recovery

Two independent Linux processes started the normal BigBrain WebServer over
one disposable copy of the bounded Drawing 42 probe. Each process served the
same conversation through the WebSocket `chat.history` request and stopped
cleanly. The second process restored the same 13 named accepted operations,
the same working checkpoint and a byte-identical STL from
`/api/cad/working-artifact`. The evidence list exposed the CAD run. This
checks recovery of incomplete construction through the product server.
The check used an HTTP/WebSocket client and did not measure browser rendering.

The production frontend build was then served by a fresh BigBrain WebServer
process over the same copied stores. From History, the browser reopened the
test conversation, showed the incomplete delivery state and restored all 13
accepted steps. The Construction control displayed the interactive Three.js
canvas and the sketch dimensions disclosure. This reused the bounded run
data and a synthetic conversation message, with zero provider calls.

## Delayed mesh response in Chromium

On Linux, headless Chromium with ANGLE SwiftShader mounted the product
`CadMeshViewer` component and rendered synthetic STL files through its
Three.js viewport. A browser fixture held the second checkpoint's HTTP
response, advanced to the third checkpoint, then released the obsolete
second response. The displayed sketch stayed with the first mesh while
the second request was pending. The third mesh and sketch then appeared
together, the obsolete result produced no update, and the canvas element
survived both transitions. A fourth checkpoint with no solids or sketches
cleared the preview.

This test exercised React, Three.js and the product mesh decoder with a
controlled HTTP transport. Whole-application qualification still covers a
real connection interruption, camera interaction and performance on a
large part using the machine's production graphics backend.

## Open Atelier during a product server restart

The current production frontend build reopened the Drawing 42 conversation
from History in Chromium on Linux. Its Construction view displayed the
interactive Three.js canvas, thirteen retained steps and the incomplete
delivery status. The process serving BigBrain was then stopped and replaced
with a second process using the same disposable stores. Observations before,
during and after the interruption showed the same Construction view, canvas
and retained checkpoint count in the tab, with zero provider calls. The
browser used ANGLE SwiftShader. This run interrupted a retained construction
view at rest. Interruption during a pending geometry change remains a
separate acceptance case.
