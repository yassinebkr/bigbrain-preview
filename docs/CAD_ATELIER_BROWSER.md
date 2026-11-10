# SolidCraft in the Atelier

The CAD surface provides an **Aperçu / SolidCraft** selector. Opening SolidCraft
loads the qualified browser distribution on demand inside the Atelier. The editor
has an expanded view, a manual checkpoint save and the bridge's pause/stop controls
when the browser document belongs to the agent.

## Build configuration

Configure these server environment variables:

```dotenv
BIGBRAIN_SOLIDCRAFT_WEB_DIR=/absolute/path/to/qualified/web
BIGBRAIN_SOLIDCRAFT_WEB_MANIFEST=/absolute/path/to/build-identity.json
```

The asset adapter accepts the recorded pristine 0.28.0 source revision and verifies
the distribution files against the manifest before serving them under
`/cad-engine/`. The local environment points to the Phase 1 distribution on the
cold HDD. Deployment paths remain server configuration. A missing or mismatched
build produces an actionable editor error. The helix-patched native build retains
its separate qualification scope.

## Document and UI lifetime

The iframe remains under a stable DOM parent. A fixed host follows the Atelier
slot, including scrolling, resizing and expanded layouts. This avoids iframe
reloads caused by DOM reparenting. Switching to the preview or another surface
parks the host offscreen and disables its input. Returning to the document
reattaches the existing host and preserves the browser instance.

The cache retains at most two documents. An idle, detached, clean document can be
evicted when another opens. Dirty, loading, executing and agent-owned documents
retain their state. If both retained documents require preservation, opening a
third asks the user to save and close one. A full page reload restores the saved
server checkpoint through the Phase 2 protocol.

Manual saves create working checkpoints. The dimensions and checks beneath the
editor identify the stored publication they describe. Publishing a modified copy
requires the existing contract and independent measurement gates. A changed
publication baseline requires reconciliation with the retained working copy.

The native CAD workflow remains available through the existing desktop action.
Its execution locks access to the embedded working copy from the CAD surface.
The browser bridge's command queue and ownership controls are available to its
host; automatic CAD-brain execution still uses the native execution adapter.
Moving the complete worker to browser execution requires connecting its existing
contract, cut-safety and measurement stages to this transport.

## Qualification

`tools/serve_cad_atelier.py` copies one retained revision into temporary owned
storage and exposes the normal CAD and browser APIs. The Vite qualification entry
mounts the real `ContextWorkspace` and `CadPanel`. Its project-switch action
unmounts the workspace, exercising retained editor lifetime.

```sh
PYTHONPATH=. .venv/bin/python tools/serve_cad_atelier.py \
  --document /absolute/path/to/retained/document \
  --build /absolute/path/to/qualified/web \
  --manifest /absolute/path/to/build-identity.json --port 3140
```

Start the frontend with `BIGBRAIN_DEV_BACKEND=http://127.0.0.1:3140`, then open
`/cad-browser-qualification.html` on its development port. The backend parameter
also proxies the bridge script and engine distribution through the same origin.

The backend qualification covers build admission, tampered assets, changed
publication lineage, checkpoint ownership and the existing WebServer routes:
82 tests pass. The frontend suite passes: 168 tests. The production
frontend build succeeds. These checks establish code and contract behavior;
browser observations are recorded separately below.

### Observed Atelier route

The real Atelier fixture loaded a disposable copy of drawing 42, publication
revision 14, with its named history. The stable final run used a fresh tab after
development replacements were complete. It retained one browser editor.

| Interaction | Observation |
| --- | --- |
| Preview to editor and back | Same iframe URL and browsing context retained |
| Return from preview | Host attached at the next animation frame in 4.1 ms |
| Switch to another project and return | Editor selection restored; same iframe URL; host attached in 44.9 ms |
| Expand and reduce | Full toolbar, history and model displayed without recreating the iframe |
| Save working copy | Browser checkpoint advanced from 0 to 1; both native snapshots retained |

The two attachment timings are individual observations of host placement. They
exclude cold initialization, geometry reconstruction and GPU completion. The
native recovery prompt was dismissed explicitly for this artificial test copy.
No model calls were used. Screenshot: `/tmp/cad-atelier-phase3.png`. The isolated
copy and journal are under `/tmp/cad-atelier-browser-a9buo0lt/`.

## Remaining qualification limits

Observed platform coverage remains Linux Chromium. Windows and actual WebGPU
coverage remain open. SolidCraft's synchronous reconstruction can block the
browser thread on the retained drawing 42; Phase 1 measured roughly 36 seconds.
The bridge avoids rebuilding the same checkpoint twice during connection.
Execution isolation remains necessary for responsive host controls during a long
geometry calculation. Warm view switching preserves an already loaded runtime.

SolidCraft's native OPFS recovery dialog can appear after an unsaved runtime is
closed. It is independent of BigBrain's accepted checkpoints. The qualification
encountered this prompt on its disposable copy; reconciliation between these two
recovery systems remains open. The host currently leaves this choice visible.
Development module replacement now releases its retained iframes and command
pumps; ordinary production view switches retain them.
