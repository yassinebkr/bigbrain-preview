# Conversational CAD qualification

This cycle extends `feat/cad-drawings` to natural-language requests, sketches,
dimensioned drawings and photographs supplemented by user measurements.

## Phases and gates

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 1. Source continuity | Conversation-owned image inventory, original hashes, persisted attachment references and versioned clarification dossier | Restart/reload retains sources and answers; another conversation receives neither |
| 2. Progressive definition | Acquired/unresolved dimensions, literal user quotations, explicit contradiction handling and one authoritative drawing specification | Resolved definition reaches the recipe; critical omissions, changed sources and unsupported measurements block publication |
| 3. Interface | Expandable thumbnails in composer/history, design dossier in the Atelier, acquired dimensions and current question | Inspect the image and pending question after reload; review the contract through one Atelier action |
| 4. Qualification | Offline boundary cases, native geometry and bounded frontend probes | Record outcomes, defects, costs where available and remaining coverage; inspect CI before proposing a merge |

## Data flow

```text
image upload ──> conversation inventory (attachment ID + original SHA256)
                         │
user answers ──> front brain + verified images + saved design dossier
                         │
                clarify ─┴─> next question + versioned dimensions/exchanges
                         │ resolved
                         v
           immutable drawing interpretation
                         │
              construction recipe only
                         │
           measured contract ──> user confirmation
                         │
                native CAD + bounded repair
                         │ all required checks pass
                 editable part + exports
```

The session file stores original attachment references and image hashes. The
front brain restores its dossier independently of the rolling 20-message model
window. User-provided dimensions retain the exact message ID and literal quote;
unit conversion may carry an explanatory note. Geometric derivations retain
their dimension dependencies. Critical identifiers remain stable during a
clarification sequence. Changing an acquired value requires a sourced user
correction, an unresolved contradiction, or an updated derived dependency.
Origin-specific native schemas expose the required quotation fields and the
empty dependency list for direct measurements. Arithmetic derivations use a
separate variant with required inputs and reasoning. Revision comparison rejects
late responses against a newer dossier. A proposed dossier binds to its exact
run before the Atelier displays it beside the contract.

The planner receives the resolved interpretation and outputs `CadRecipe`.
`CadPlan` adds the runtime-owned drawing and validates measurement bindings.
An invented dimension identifier or replacement interpretation is rejected.
Images are rechecked against their uploaded hashes before inference and CAD
delegation. A fresh upload can recover an unavailable source using a new identity.

## Bounds and remaining scope

- Each inference can include up to eight relevant images. The dossier keeps up
  to 64 exact exchanges; reaching a bound produces an explicit diagnostic.
- Photographs supply shape context. Exact sizes require visible annotations,
  a user-supplied scale or measurements. Perspective pixels provide no metric
  authority. Ambiguous or unsupported details require clarification.
- Geometry qualification retains the existing linear measurements, sampled
  sections, closed-body and volume checks. Arbitrary topology, manufacturing
  tolerances, fits and angular qualification need additional measurement tools.
- Attachments sent before reference persistence was implemented may require
  uploading again. Their original bytes cannot be authenticated retroactively
  from a filename alone.
- Shared session/evidence formats use portable filesystem APIs. Windows native
  SolidCraft qualification remains open in the portability backlog.
- `tools/serve_cad_clarification_probe.py` isolates all application data and
  retains its call report across restarts. Its campaign limit is ten model calls
  and ten minutes of accumulated inference, with a 90-second per-call ceiling.
  An explicitly authorized four-call extension can raise the campaign ceiling
  to fourteen through `CAD_PROBE_MAX_CALLS=14`.

## Qualification status — 1 November 2026

Phases 1–3 are implemented and covered by isolated regression tests. Phase 4
remains open for final frontend qualification. CI review is deferred at the
user's request; the workflow currently runs on main and pull requests, and this
cycle has no pull request or merge.

| Case | Observed result |
| --- | --- |
| Dimensioned drawing with two requested changes | Height and hole diameter were requested separately. The source survived browser reload and server restarts. The resulting 80 × 40 × 25 mm stepped support with Ø8 through-hole passed all 11 checks in the Atelier. |
| Natural-language annular spacer | The complete request reached confirmation and native construction. The volume check failed, and the part remained incomplete. One repair retained the volume discrepancy; the campaign ceiling stopped further calls. |
| Unscaled artificial render plus explicit measurements | The first response used geometric relationships in arithmetic dependency fields and was rejected. Origin-specific schemas now encode the constraints. The final resumed trial has an unobserved outcome following an execution-environment renewal. |
| Missing, replaced or changed image | Isolated tests verify an explicit stop before inference, new-upload recovery and original hash validation. |
| Cross-conversation and stale-response isolation | Isolated tests verify source/quotation ownership, revision conflicts, preserved pending questions and run-bound dossier display. |

The spacer's expected volume was 2,243.097154663112 mm³ (714π). SolidCraft
reported 2,242.9876432870474 mm³, an approximately 0.00488% discrepancy, exceeding
the confirmed 0.001% relative tolerance. Its other ten checks passed. A second
construction recipe retained the discrepancy. Qualification of the engine's
mass-property precision and suitable measurement contracts remains necessary;
the existing candidate's acceptance criteria remain unchanged.

The live campaign used Codex Sol 6.1 low. Eleven completed calls were observed
before the last resumed trial. That trial and any downstream calls could have
consumed the remainder of the fourteen-call ceiling. Its temporary server,
call report and captures became unavailable in the renewed execution environment.
The automation tool then rejected access to the existing browser tab through
its URL policy. Further paid calls remain suspended until their budget and
browser access can be re-established. Monetary cost and the final trial's
token usage remain unknown.

The final standalone backend run passes 2,194 cases with eight optional skips.
An added volume-tolerance regression passes separately. Targeted CAD/session
coverage passes 63 cases; the frontend build and all 159 UI tests pass. An
earlier concurrent run hit the five-second deadline in the existing
high-event-throughput test; its isolated recheck and the standalone suite pass.
The final backend log is preserved outside temporary storage at
`/home/kwestog/Documents/code/tests/cad-conversation-qualification-20261101/backend-current.log`.

### Remaining completion gate

Verify the final schema and source-retry path through the browser, enlarge a
persisted image, confirm the correct run-bound dossier, and construct the
unscaled-image candidate after reviewing its measured contract. Retain a fresh
trace and screenshot outside temporary storage. Add a successful fresh
language-only delivery alongside the already observed incomplete spacer case.
CI review and merge remain separate, deferred actions.
