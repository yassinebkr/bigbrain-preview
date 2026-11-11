# Hosted CAD Worker in the Atelier

## Execution and presentation

The hosted distribution uses a Worker as the editable SolidCraft session. The
Atelier iframe presents evaluated checkpoints using the matching SolidCraft
build. The server accepts each operation against its revision, hash and lease
before the viewer receives its bytes. Rejection preserves the previous view.
A presentation error leaves the server's accepted checkpoint recoverable.

Initial native documents may need evaluation in the Worker. Its cache-enriched
presentation copy leaves the retained native checkpoint unchanged. Later
checkpoints reach the same iframe through a cache-only import. Missing or
incompatible evaluated geometry produces an explicit error. Hosted startup
skips SolidCraft's separate browser autosave and recovery dialog.

Stopping revokes the server lease first, terminates the active Worker, and
restores the accepted checkpoint. A late completion cannot publish a revision
under the revoked generation. The hosted view locks native editing controls;
the ordinary SolidCraft distribution retains its existing manual editor.

## Qualification

The actual Atelier on a disposable copy of drawing 42 accepted and displayed
revision 1 after changing flange thickness from 50 to 51 mm. The same iframe
remained mounted. The renderer reported 12,184 triangles through GL/ANGLE on
the RTX 3070 Ti in the integrated Chromium browser. This run exercises the
Worker, server journal and viewer together. The earlier Vulkan-profile WebGPU
result is separate.

The measured operation took 37.577 s. A host control responded during the
operation, with 5,360 sampled frames and a maximum interval of 187.7 ms. The
long synchronous reconstruction no longer blocks the host in this case. The
remaining frame gap is perceptible and leaves room for presentation optimization.

Evidence: `/tmp/cad-atelier-browser-vyrgeodm/worker-atelier-report.json` and
`/tmp/cad-atelier-worker-verified.png`.

## Reproduction and limits

The Atelier keeps one `Aperçu / SolidCraft Web` selector in compact and expanded
views. Native desktop opening is a secondary action in the download menu.
The hosted toolbar contains ownership controls and one camera-view menu. A
viewport overlay forwards orbit/zoom exclusively through `ui.camera`; geometry
tools in the native iframe remain locked. Native manual editing transfer remains
an open implementation item. Static bridge responses use `no-store`, and the
frontend pins the hosted-camera bridge revision to prevent an older cached
module from retaining obsolete interaction behavior.

1. Start from SolidCraft commit `ee6b85605a32948bcbd9ae437a564cab826689ec` in an
   isolated Git checkout. Apply `tools/solidcraft-hosted-cache-v1.patch` and copy
   `tools/solidcraft-worker-probe` to `apps/bigbrain-worker-probe` in that checkout.
2. Build the web application with Trunk. Build `bigbrain-worker-probe` for
   `wasm32-unknown-unknown` and generate web bindings with the matching
   wasm-bindgen CLI into the final web distribution's `worker` directory.
3. Generate a manifest with `tools/build_cad_hosted_manifest.py`. Serve the
   distribution and manifest via `tools/serve_cad_atelier.py` and point Vite at
   that fixture server. Open `cad-browser-qualification.html?worker=1`, expand
   the Atelier and start the Worker qualification on drawing 42.

The local build is isolated; the installed engine and configured application
retain their current settings. The hosted path requires the explicit distribution
and manifest configuration. Existing document journals pin their capability
identity; switching an existing working copy to another build requires an
explicit migration decision. The current cached-view transport admits checkpoints
up to 3 MiB. Full native manual tool dispatch through the Worker, compact
construction views and Windows qualification remain outside this result.
