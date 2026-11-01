# CAD from dimensioned drawings

The multi-turn extension is tracked in [Conversational CAD qualification](CAD_CONVERSATION_PLAN.md).

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
Before delegation, each source must match an image owned by this conversation
and its stored bytes. Unresolved critical dimensions require clarification.
The CAD planner receives the interpreted specification, while the runtime binds
the original interpretation to the resulting recipe and immutable proposal.
The proposal displays the drawing dimensions together with measured criteria.

The conversation-owned attachment inventory now restores drawings across
clarification turns. Its original hashes, exact exchanges and versioned
dimension snapshots survive reload and restart. See the conversation cycle
for qualification and bounds. Feature verification and repair follow in phase 3.

## Phase 3

Critical linear dimensions bind directly to measured envelope components or
material-section endpoints, lengths and gaps. Runtime validation checks the
expected value against the drawing, including inch-to-millimetre conversion.
Missing bindings block the recipe. Angular and manufacturing criteria require
additional measurement support and clarification.

Bindings can subtract another section quantity. Both independently measured
sections must pass, and their expected difference must match the source dimension.
This covers dimensions such as step rise = total height − base thickness.

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

## Phase 4 evidence — 1 November 2026

The artificial drawing fixture `tests/fixtures/cad/stepped-support.svg` defines
an 80 × 40 mm base, 8 mm thick, a 20 mm long raised step reaching Z=20 mm,
and a through-hole Ø6 at X=60, Y=20. Its expected geometry is independent of
the model output. The native regression campaign also covers rounded outlines,
equal-volume hole relocation, ambiguous boundary sections, invalid STL records,
unit conversion, missing/conflicting dimensions and stale image hashes.

The Codex adapter now sends image blocks as native app-server image inputs.
Earlier code serialized multimodal blocks into text despite declaring vision.
RPC regression tests cover image ordering, text accounting and rejection of
remote/file URLs. Text-only conversation reuse retains its existing format.

The model-led validation ran in stages, using Sol 6.1 low through Codex:

| Stage | Observed result | Calls | Reported input / output / cached tokens |
| --- | --- | ---: | --- |
| Browser drawing upload, front interpretation and first proposal | Dimensions read correctly; missing measurement binding for derived step rise blocked the proposal | 2 | 22,543 / 4,809 / 3,584 |
| Targeted proposal continuation | Corrected contract generated; the browser driver exhausted its remaining observation window | 1 | 16,101 / 2,631 / 3,584 |
| Local proposal replay and Atelier confirmation | Confirmation reached the worker; the engine rejected a symbolic sketch-circle diameter | 0 | — |
| Authorized native repair of the recorded candidate | One correction, fresh candidate, 13 passing criteria and publication in 9.05 s | 1 | 9,514 / 363 / 3,584 |

The repair retained all confirmed dimensions and measurement targets. It changed
the sketch-circle diameter from the expression `D` to numeric 6, as required by
the installed engine. Completed command rejections enter the bounded repair
loop; transport uncertainty stops the run. Command diagnostics remain available
beside the candidate evidence. The native document was independently reopened:
the cylinder radius is 3 mm at X=60/Y=20, base and step faces lie at Z=8/20,
and the editable sketch and feature history remain present.

Measured volume is 34,973.84290071026 mm³. Its native SHA256 is
`878777d61a45ea3f738072d3ff17dcf9ab7539bc134d03eee762eb897bd41295`.
The final repair report is temporarily available at
`/tmp/cad-repair-live-dwx9igu_/report.json`; earlier browser/call records are under
`/tmp/bigbrain-cad-drawing-probe-wb7d5b5l/`. Temporary files can disappear after
cleanup or reboot. Subscription usage was observed; monetary cost is unknown.

Local verification: the full backend run passes 2,170 tests with eight optional
extractor cases skipped. Six stricter axis-type cases were added after that run's
collection; all eighteen section tests then passed. The frontend build and all
153 Vitest cases pass. The first full run exposed a CAD diagnostic-prefix
compatibility regression and two timing-sensitive failures. The prefix was
restored; isolated rechecks and the subsequent complete run pass. CI is deferred
until the pre-merge review as requested.

An additional uninterrupted browser run completed on 1 November through the
3134 demo server, in conversation `sess-96aa155be0da`. The artificial drawing
was uploaded through the attachment picker, interpreted by the front brain,
and converted into a proposal. Confirmation in the Atelier launched SolidCraft
0.28.0 and published revision 1 with all 16 required checks passing. The browser
displayed the stepped solid and through-hole, readable measurement details,
the native-editor action and the export menu. Mouse-wheel zoom updated the
interactive preview. This candidate succeeded on its first execution; repair
behavior is covered by the earlier recorded candidate and regression tests.

The resulting document ID is `0d15e364d72543399336061e4bf143e0`, with native
SHA256 `209dc6afdac4fef6945c893bec70bbd25256b8e75571e7e78c7f607c10bcbfc1`.
Dimensions are 80 × 40 × 20 mm and measured volume is 34,973.84290071025 mm³.
The bus trace is under `/tmp/cad-interactive-qa-ezwuatyy/logs/`; the browser
capture is `/tmp/cad-drawing-ui-live-success.jpg`. The generated title retains
proposal wording after completion, a presentation limitation visible in this run.

Windows native behavior, arbitrary topology, fits
and manufacturing tolerances remain follow-up work. Existing-component
portability follows this CAD cycle.
