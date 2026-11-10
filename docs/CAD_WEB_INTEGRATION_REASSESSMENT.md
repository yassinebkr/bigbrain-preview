# CAD browser integration reassessment

## Corrected presentation contract

The compact Atelier provides full 3D and construction context showing sketches,
dimensions and related 3D geometry. Both display observed construction evidence.
The full SolidCraft interface occupies the expanded workspace directly. Agent
ownership allows pause and stop; manual editing starts after execution pauses.

## Established findings

| Issue | Evidence |
| --- | --- |
| Browser cache reuse disabled | The source archive lacks Git metadata. Browser roundtrips contain `evaluation: unknown/wasm32-`. SolidCraft's cache reader explicitly rejects unknown source identities. |
| Blank application startup | Fresh diagnostic origin: API ready in 910.5 ms; WASM transfer 246 ms for 97,182,412 bytes; maximum host frame gap 618.7 ms. |
| WebGPU admission | Secure context with `navigator.gpu` present; `requestAdapter` returns null. SolidCraft selects GL/ANGLE on the RTX 3070 Ti. |
| UI blocking | The web API queues engine commands into the application logic loop. The current iframe shares the host's JavaScript thread. |
| Competing recovery | Full SolidCraft starts OPFS storage and its recovery prompt while BigBrain also retains native checkpoints in its journal. |

`crates/io/build.rs` derives cache identities from Git. The current build originated
from an archive, so an external manifest naming the source commit does not establish
the identity embedded in the runtime. The native-to-browser first import also
crosses platform cache identities and requires its own measurement.

The official app's public WASM response uses gzip and caching, with an encoded
length of 32,306,837 bytes. Its deployment has not been qualified against the same
retained document. Blank startup and document reconstruction need separate results.
### Linux WebGPU adapter selection

The user supplied Chromium 154.0.8037.92's GPU report, source revision
`334b65d254ccc35df4fca82706d1753227b01039`. It lists the NVIDIA adapter through
OpenGLES in Compatibility Mode. Its only Vulkan adapter is SwiftShader, explicitly
blocklisted as a CPU adapter. The regular page requests for default, core and
compatibility adapters all returned null on this browser. The integrated test
browser reports Chrome 155 and also returns null for all three requests.

The [exact Chromium decoder source](https://chromium.googlesource.com/chromium/src/+/334b65d254ccc35df4fca82706d1753227b01039/gpu/command_buffer/service/webgpu_decoder_impl.cc)
selects Vulkan on Linux when the applicable Vulkan context/interop conditions
hold; otherwise it selects the Null backend, with the explicit comment
`Deliberately disable compat on linux` (lines 1754–1762). Consequently, the
OpenGLES adapter advertised by Dawn remains unavailable through default Linux
web-page selection. Requesting compatibility alone leaves this backend selection
unchanged. The report's accelerated WebGPU headline is insufficient admission
evidence. The supplied data establish the selection mismatch; they do not measure
whether a different supported Vulkan configuration can create a working device.

No browser security flags, adapter blocklists or driver settings were changed.
Qualification still requires a successful device and an actual SolidCraft frame
using that device. GL fallback remains identified explicitly.

Host-side Vulkan enumeration on 2026-11-10 succeeds (`vkCreateInstance: 0`) and
finds the NVIDIA GeForce RTX 3070 Ti as a discrete GPU with Vulkan 1.4.325.
`nvidia-smi` confirms driver 590.48.01. This separates host-driver capability from
Chromium's backend admission. A temporary Chromium profile using
`--enable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan` is the next controlled
qualification. Sandbox and adapter blocklists remain enabled. This configuration
is experimental pending adapter/device creation, rendered output and stability
checks; it must remain separate from the normal browser profile until qualified.

### Observed Vulkan-profile run

The user-run Chromium 154 profile with those Vulkan features creates NVIDIA
Ampere WebGPU devices for default, core and compatibility requests. Blank
SolidCraft reports `BrowserWebGpu` and reaches API readiness in 688.2 ms.
The retained drawing 42 campaign at `/tmp/cad-webgpu-piece-MIAwOR` subsequently
records a 37,612 ms load and successful front/right/home observations using
`BrowserWebGpu`: 7,120 / 7,120 / 7,360 rendered triangles, with reported frame
times of 3 / 2 / 2 ms. Initial geometric inspection completes in 5,438 ms.

The user reports an unresponsive-page warning. The last persisted boundary
precedes completion of the parameter edit. The run has no terminal result yet;
saved-file, undo/redo and independent STEP comparisons remain unverified for
this Vulkan-profile campaign. These measurements establish WebGPU rendering on
the retained part while leaving synchronous reconstruction responsiveness open.

## Correction sequence

Isolated computation evidence: [Geometry worker qualification](CAD_WORKER_QUALIFICATION.md).

1. Diagnose WebGPU admission before interpreting GPU performance. The Linux
   selection mismatch is established above; successful WebGPU rendering remains
   an open qualification gate.
2. Rebuild pinned 0.28.0 from its exact Git revision in isolation. Verify identities
   inside a browser-saved document. Preserve cache trust checks. Measure native
   import, browser save/reopen and dimensional edit separately on the same case.
3. Establish BigBrain as the hosted document's recovery authority. Add explicit
   native import/export and hosted recovery behavior to the browser interface.
   Qualify interrupted manual edits, saves and agent commands.
4. Qualify actual execution isolation with a small expensive operation. Measure
   host frame gaps and pause/stop responsiveness. Async wrappers and an iframe
   alone do not demonstrate isolated computation.
5. Implement the corrected observation views and open the real editor directly
   in the expanded workspace. Bind views, recovery and ownership to the same
   checkpoint.
6. Qualify WebGPU on a browser that grants an adapter, including rendered output
   and device failure behavior. Rendering acceleration does not establish faster
   CPU geometry evaluation.

## Evidence and status

Diagnostic driver: `tools/serve_cad_browser_diagnostics.py`.
Observed report: `/tmp/cad-browser-diagnostics-vbqbrd4t/report.json`.
Inspected saved browser cache:
`/mnt/cold-hdd/bigbrain-local/solidcraft-web-028/qualification/drawing42/drawing42-roundtrip.sc`.
Official deployment headers: `/tmp/solidcraft-official-headers.txt`.

The recorded geometry/history roundtrips retain their evidence. Cache reuse,
execution isolation, unified recovery and the corrected presentation remain open.
Phase 3 requires these corrections before closure. The full editor now mounts
only inside the expanded Atelier; its nested expansion modal was removed. The
compact construction observation view, cache, isolation and recovery changes
remain open. No model calls were consumed.

Latest UI check: the retained drawing 42 copy opens inside the expanded Atelier
without a nested expansion dialog. The native recovery prompt appears over the
editor, confirming the remaining recovery-authority conflict. Screenshot:
`/tmp/cad-atelier-direct-workspace.png`. All 169 frontend tests pass. These results
leave the integration milestone open.
