# Deep research — Generative UI, agents and morphable interfaces

State of the art as of October 17, 2026 · Research report (GPT-6 Thinking, high)
for BigBrain's "morphable UI" phase (roadmap item 7). Saved as-is minus
rendering artifacts. The French original lives at
[fr/morphable-ui.md](../fr/morphable-ui.md).

## Executive summary

The vision is technically feasible, but its three components do not carry the
same product value or the same level of risk.

The strongest idea is not the floating robot. It is the combination of a
contextual work surface, a controlled component catalog, and shared state
between the agent and the interface.

| Priority | Component | Verdict |
|---|---|---|
| 1 | Task-based templates + constrained components | High value, manageable risk. Build on stable surfaces, typed data, and explicit composition rules. |
| 1 | Contextual right-hand work surface | High potential for research, code and long operations. Main risk: spatial instability. |
| Experimental | Floating, mobile companion | Interesting visual differentiation, functional benefit undemonstrated. To be tested against a simple anchored presence. |

These priority levels are product-architecture judgments, not scientific
scores.

### A fundamental distinction: three layers, three responsibilities

| Layer | Reference technology | Responsibility |
|---|---|---|
| Communication & execution | AG-UI | Agent ↔ frontend flow, states, tools, interruptions |
| Interface description | A2UI or a proprietary schema | Declare what to display and which interactions are allowed |
| Spatial orchestration | Our reconciler | Decide where, when and how to display surfaces |

This decomposition is decisive: A2UI does not replace AG-UI, and neither
solves the morphable-layout problem alone.

Important finding: A2UI v0.9 is no longer the current production version —
v0.9.1 is production, v1.0 is a candidate. Examine the differences before
freezing an internal schema.

**Central recommendation: the agent chooses a presentation INTENT, never
screen geometry. The product keeps control of placement, visibility, focus,
transitions and permissions.**

## 1. State of the art: protocols, products and research

### 1.1. A2UI — the closest reference to our architecture

Public specification (Google / open source), v0.9.1 current. A2UI describes
interfaces as independent JSON messages, transportable over JSONL, WebSocket
or anything else. The renderer turns these descriptions into native
components. It is neither model-generated HTML nor arbitrary JS execution.

Server → client operations (v0.9):

| Operation | Function |
|---|---|
| `createSurface` | Create a surface with `surfaceId`, `catalogId`, optional theme |
| `updateComponents` | Add/modify the surface's components |
| `updateDataModel` | Update the values components are bound to |
| `deleteSurface` | Delete a surface and its content |

Components have stable identifiers and form a tree defined by id references.
Data is separated from structure and accessed via JSON Pointers. The renderer
can receive components and data progressively.

v0.9-conformant example:

```
{"version":"v0.9","createSurface":{"surfaceId":"run_evidence","catalogId":"https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"}}
{"version":"v0.9","updateComponents":{"surfaceId":"run_evidence","components":[{"id":"root","component":"Card","child":"status"},{"id":"status","component":"Text","text":{"path":"/run/status"}}]}}
{"version":"v0.9","updateDataModel":{"surfaceId":"run_evidence","path":"/run","value":{"status":"Analyzing"}}}
```

In our product, the `catalogId` would designate our own versioned catalog.

**Interactions and callbacks (the crucial point):**
- Server actions (`submit_form`) carrying `surfaceId`, `sourceComponentId`, timestamp, context.
- Local functions via `functionCall`, executed by the renderer only if registered in its catalog.
- Predefined local validations (`required`, `regex`, `email`).
- Optional `sendDataModel` — when active, the surface's full state is sent back with related client → server messages: recommend targeted events or minimal projections rather than systematic full sharing.

An A2UI action is NOT an agent tool call: the button emits an intent; the
server controller decides whether it triggers a tool, a state change or a
confirmation.

**Adopt / adapt / ignore:**

| Decision | Element | Rationale |
|---|---|---|
| Adopt | Identified, persistent surfaces | Several active spaces without confusion |
| Adopt | Server-validated catalog | Constrains the agent's vocabulary |
| Adopt | Component/data separation | No UI rebuild for a status change |
| Adopt | Incremental updates | Ideal for streamed code, results, evidence |
| Adapt | `createSurface` | Must not automatically mean "open a panel" |
| Adapt | `deleteSurface` | Hide or keep in history rather than destroy |
| Adapt | Client → server actions | Allowed-action registry + permission control |
| Adapt | `sendDataModel` | Share only the necessary fields |
| Defer | Multiple native renderers | Useless while we target React Web |
| Ignore | Mandatory A2A transport | Our WebSocket is enough |
| Avoid | Free generation of stylistic properties | The agent does not own our design system |

A2UI should be a **contract and interoperability inspiration**, not a
dependency imposed from the first phase. Prefer a reduced internal schema,
compilable to A2UI v0.9.1 when external compatibility becomes useful. The
v1.0 candidate introduces `actionId`, client-side `actionResponse` RPC,
surface evolutions — do not implement them as if they were v0.9.

### 1.2. AG-UI — the synchronization model to keep

An event-driven agent ↔ application protocol (it does not prescribe
appearance).

| Family | Useful events |
|---|---|
| Execution | `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR` |
| Steps | `STEP_STARTED`, `STEP_FINISHED` |
| Chat | `TEXT_MESSAGE_START/CONTENT/END` |
| Tools | `TOOL_CALL_START/ARGS/END/RESULT` |
| State | `STATE_SNAPSHOT`, `STATE_DELTA` (JSON Patch RFC 6902) |
| Activity | Subagent events, attribution |

**The "shared working memory"** is the most interesting part for our vision:
the agent exposes a structured state the interface can observe; the frontend
can evolve authorized fields. Snapshot → consistent base; deltas → targeted
changes; resynchronization is planned when patches become incoherent.

But bidirectional state ≠ undifferentiated ownership. Three recommended
domains:

| State | Primary authority | Example |
|---|---|---|
| Execution | Backend / orchestrator | Active step, status, artifacts, progress |
| Workspace | Frontend / user | Pinned panel, dimension, active tab |
| Collaborative | Shared, but arbitrated | Board selections, annotations, proposals |

A model that can read the layout state does not get the right to overwrite
it: it proposes, an application policy decides. AG-UI does not
automatically solve conflicts, permissions or persistence — its docs
explicitly recommend handling them.

**Decision: borrow the AG-UI vocabulary to normalize our existing bus; migrate
to its full runtime only if real interoperability requires it.**

### 1.3. OpenAI: what is actually shipped

- **Canvas** (Oct 2024) — side-by-side collaboration; the lesson stands:
  separate a persistent artifact from the conversational flow.
- **Apps SDK / MCP Apps** (2025–2026) — interactive chat widgets driven by MCP
  tools; a web UI in an iframe communicating with its host.
- **ChatGPT Work** (Jul 2026) — long tasks, artifacts, progress tracking,
  course correction, action approval.
- **Intelligent UI** (Oct 7, 2026) — THE major finding: streamable native
  components, an incremental compiler processing the interface during
  generation, and model training to decide organization, interactivity, and
  when plain text is enough. The key point: a good GenUI system learns
  **when not to generate an interface**. It validates the constrained
  catalog + incremental rendering pair; it does not demonstrate that the
  model should control the entire persistent organization of a workspace.

**Open-JSON-UI**: presented by AG-UI/CopilotKit as the standardization of
OpenAI's internal schema, but **no verifiable primary OpenAI source** of a
versioned normative schema exists. Verdict: a watchlist lead, not a
foundation. To implement today, A2UI and AG-UI are far better publicly
documented.

### 1.4. Apple: what to actually keep

- **Liquid Glass**: content/control hierarchy, translucent layers,
  contextualized navigation. Official guidance: reserve it for controls and
  navigation, avoid accumulation in the content layer. It is NOT a
  demonstration of generative-UI effectiveness — it is a visual language.
- **visionOS Ornaments**: the directly usable conceptual model for our
  companion — a secondary control can float near a window, stay **bound** to
  it and keep its position while content scrolls. "Visually floating,
  functionally anchored." Recommendations: limit window counts, avoid
  distracting peripheral movement.
- **Contextual Siri (App Intents, WWDC26)**: linking visible elements to
  business entities and actions ("the third one", "this conversation").
  Relevant to our board: the agent needs the **structured identifiers** of
  the current selection, not a screenshot. → Proposal: a **context registry**
  exposing selection, visible artifacts, active run. More innovative than a
  robot following the pointer.
- No Apple specification establishes an animated "spatial Siri" freely moving
  on a desktop as a proven pattern.

### 1.5. Academic research: favorable and unfavorable results

| Study | Result | Consequence for us |
|---|---|---|
| Chen et al., 2025 — Generative Interfaces for LMs | Human preference for generated interfaces in >70% of cases | Interactive presentation can genuinely beat linear chat |
| Cao et al., CHI 2025 — Generative and Malleable UIs | Continuity and control problems tied to UI regeneration | Evolving structures and data models, not full replacements |
| Peng et al., Apr 2026 — Efficient Personalization | 12,000 judgments; marked divergences between designers | The optimal layout is not universal: record preferences and corrections |
| Design Theater, Jul 2026 | Of 120 generated UIs, >25% of design rationales and 34% of functional requirements not reflected in the result | **Never validate a layout on the LLM's convincing explanation** |
| EvoGenUI-Bench, Aug 2026 | Best model: 74.9% per-turn success, only 37.3% of full five-turn episodes | The real problem is multi-turn stability, not initial generation quality |
| GenUI-Harness, Oct 2026 | Database workflows: average dialogue turns 3.4 → 1.2 | Structured representations reduce friction in specific workflows |

Nuanced conclusion: GenUI has empirical value, but models remain notably less
reliable when an interface must **survive several modifications**. This
strongly supports curated templates. The last three publications are
preprints describing their own benchmarks.

For the spatial side: "Context Matters!" (Oct 2026) proposes a
spatial/social/semantic framework for embodied agents — a preliminary AR
framework, not a validation of a desktop floating robot.

## 2. Task-type templates: critique and proposal

### 2.1. The trap: assuming one task = one template

It works for simple intents (research, code, writing, board) but becomes
ambiguous for multi-agent tasks ("Research Madgwick implementations in C++,
compare them, build a benchmark and add the conclusions to the board"). The
right unit of composition is not the overall task but **the active phase of
the workflow and the artifacts it produces**.

Two-level architecture: Task Intent (goal, work type, expected artifacts) →
Workspace Reconciler (permissions, focus, existing surfaces, preferences,
space) → Contextual surface (view of the active artifact). A template change
is a presentation-mode change, not a workspace replacement.

### 2.2. The templates to build

| Template | Main surface | Secondary elements | Trigger |
|---|---|---|---|
| `conversation` | Chat | Compact status | Simple question, discussion |
| `research` | Evidence / sources | Synthesis, citations, progress | Multi-source research |
| `code` | Editor / diff / run result | Tests, terminal, logs | Code being produced or executed |
| `document` | Editable artifact | History, comments, revisions | Writing or transformation |
| `board` | Structured canvas | Inspector, evidence, relations | Object manipulation and organization |
| `review` | Comparison / validation | Risks, changes, approval | User decision required |

Add a cross-cutting composition layer (e.g. an `EvidencePanel` shared by
`research` and `code`). Distinguish **visual** components (text, button, list,
tabs, container) from **business** components (`RunOutput`, `EvidenceCard`,
`DiffViewer`, `ArtifactPreview`, `ApprovalCard`, `BoardSelection`). Start
with the current catalog; add only the business components whose tests prove
value.

### 2.3. How the agent chooses the template

Do not ask the LLM "which interface should be displayed?" (too vague,
unstable across turns). Three steps: (A) intent detection — goal and expected
artifacts; (B) a **typed presentation proposal**; (C) deterministic
reconciliation — the frontend accepts, adjusts or rejects.

```ts
type TemplateId = "conversation" | "research" | "code" | "document" | "board" | "review";
type SurfaceId = "evidence" | "run-output" | "artifact" | "board" | "diff" | "approval";

type PresentationProposal = {
  proposalId: string;
  runId: string;
  template: TemplateId;
  primarySurface?: SurfaceId;
  secondarySurfaces: SurfaceId[];
  reason: "artifact-created" | "tool-running" | "evidence-ready"
        | "review-required" | "user-requested";
  urgency: "background" | "normal" | "blocking";
};
```

Deliberately missing: `positionX`, `positionY`, `width`, `height`, `zIndex`,
`html`, `css`. **The agent states the need; the renderer decides geometry.**
This separation is what makes the system predictable.

### 2.4. The reconciler: the true heart of the product

Five responsibilities:
1. **Validation** — schema, real artifacts, provenance, permissions.
2. **Resolution** — intent → configuration compatible with screen width, active template, user preferences.
3. **Conservation** — selection, focus, scroll position, forms being edited, pinned components.
4. **Application** — a coherent set of changes, not a succession of visible moves triggered by each event.
5. **Recovery** — replay the last valid configuration after an error, WS reconnection, or an invalid proposal.

```ts
function shouldApply(proposal: PresentationProposal, workspace: WorkspaceState): boolean {
  if (workspace.userLocked) return false;
  if (workspace.isEditing && proposal.urgency !== "blocking") return false;
  if (workspace.pinnedSurface && proposal.primarySurface !== workspace.pinnedSurface) return false;
  return true;
}
```

(Architectural pseudocode — the real version also checks permissions, run
identity, event ordering, surface existence.)

**Three levels of autonomy**: Automatic (update data of a visible component,
compact status) / Suggestion (new surface, template change) / Confirmation
(sensitive external action, overwrite, deletion). "An interface that changes
by itself is not necessarily an intelligent interface" (Horvitz, CHI 1999:
the costs of automatic initiative poorly synchronized with attention).

### 2.5. Free layout vs curated templates: verdict

Free layout can invent unforeseen compositions, but carries four serious
difficulties: ergonomics validation, cross-turn continuity, attack surface,
and the user's landmarks (CHI 2025, EvoGenUI-Bench).

**Retention: 80–90% of structure decided by our design system, 10–20% of
contextual composition driven by the agent.** (A design orientation, not an
experimental result.) The model must have enough freedom to choose what to
show, not enough to reinvent conventions.

## 3. The companion robot: interaction, attention and anthropomorphism

### 3.1. The best argument AGAINST the concept comes from research

Rickenberg & Reeves (CHI 2000): characters giving the impression of watching
the activity **increased anxiety and degraded performance**, while increasing
trust in the site. A character can make an interface more engaging or
credible **without improving work quality** — exactly our robot's potential
trap.

Calm technology (Weiser & Brown, 1995): information should move between the
center and the periphery of attention without constantly soliciting the
user. The robot should be an **informational peripheral**, not a character
seeking to be looked at.

### 3.2. The right behavior: a state machine

| State | Visual signal | Movement |
|---|---|---|
| `idle` | Minimal presence, possibly hidden | None |
| `working` | Discrete activity, current step | Very subtle local animation |
| `result-ready` | Result-available indicator | Short transition, only if useful |
| `needs-input` | Explicit attention request | Anchor near the action zone |
| `blocked` | Identified failure or conflict | Status signal, no agitation |
| `user-engaged` | Quick actions open | Immobility during interaction |

A robot that keeps moving to show it is working adds little over an animated
activity indicator. A robot that lets you understand which agent works, on
what, with what result and what intervention is expected can become a real
interface.

### 3.3. Movement policy

- **Justified movement**: user invocation, voluntary drag, requested re-anchoring.
- **Discreet transition**: a surface opens and the companion keeps a coherent visual anchor without covering content.
- **Forbidden**: following the cursor, crossing the chat, floating over code, repositioning on every subagent change, attracting attention for a minor result.
- **Simple rule**: no autonomous movement during precision interaction (writing, text selection, code editing, drag, evidence comparison).

Short framer-motion transitions, consistent easing, respect
`prefers-reduced-motion` (WCAG 2.2: risks of non-essential animations).
150–250 ms as a starting point to test.

### 3.4. Anchoring: three variants to test

Anchored (bottom corner, known persistent position) — **recommended default**;
Contextual (bound to the active surface by deterministic rules) — on demand;
Free — to evaluate. ISMAR 2026: no anchoring strategy dominates universally.
"Beyond Activation" (Oct 2026, AR): the most transferable finding is not
gaze as a trigger but **clarity of state transitions**.

### 3.5. Anthropomorphic signals

Appearance must match real capabilities. Expressive status iconography: yes.
Animations pretending to manifest emotion/worry/impatience: superfluous
staging. The robot represents system activity, not a human personality.
**Keep a "no companion" mode** offering exactly the same actions — essential
to determine whether the robot is functionally useful.

## 4. The right-hand surface: better use of available space

### 4.1. Appearance according to information value

"it's empty, so it must be filled" is dangerous: empty space participates in
concentration. Rule: **open an extra surface only when it lets the user act,
verify or compare more easily than in chat.**

Three states: **Focus** (chat alone, free space) → **Peek** (compact result
without imposing a layout change) → **Workspace** (open surface). Peek is
particularly interesting.

### 4.2. When to open, fill or close

| Event | Recommended behavior |
|---|---|
| Simple conversational reply | Open nothing |
| Research starts | Compact status |
| First useful source | Offer evidence access |
| Several items to compare | Open the comparison view unless user-blocked |
| Code execution | Show activity; detailed output only when it adds value |
| Failing test | Make the failure immediately accessible, higher priority |
| Generated document | Offer the editable document |
| Agent awaiting approval | Clear request in a stable zone |
| User pins a surface | Never replace it automatically again |
| Run finished | Keep the results; allow collapsing |
| New conversation | Restore or close per the user's workspace policy |

Two principles: never confuse **closing with destruction** (a panel can
visually disappear while keeping its state and artifacts); no automatic
disappearance by default (if the user is inspecting evidence, the end of the
run must not close the component).

### 4.3. The right surface must not become a second chat

The panel represents stable objects that linear text represents poorly:

| Domain | What the user manipulates |
|---|---|
| Research | Sourced evidence, excerpts, provenance, contradictions |
| Code | Diff, files, tests, stdout/stderr, artifacts |
| Writing | Editable text, history, accepted/rejected suggestions |
| Board | Nodes, links, selections, object properties |
| Multi-agent | Steps, delegations, result owners, blockers |

```ts
type Evidence = {
  id: string; runId: string; producerAgentId: string;
  sourceId: string; sourceUrl?: string; retrievedAt?: string;
  claim: string; excerpt?: string;
  verificationStatus: "unverified" | "supported" | "conflicting";
};
```

`verificationStatus` must come from the provenance pipeline, not from a free
agent claim — avoid presenting an agent result as verified evidence because
it sits in a nice card.

### 4.4. Responsive and spatial continuity

Wide desktop: resizable split-view. Intermediate viewport: single switchable
surface. Mobile: full-screen panel / drawer / explicit navigation. Thresholds
determined by the real minimum sizes of our components, not by the
mobile/tablet/desktop classification alone. WCAG 2.2: reflow without loss.

Rule: an open surface does not change identity because the agent switched
subtasks — new information in identified tabs, stable current selection.

## 5. Technical architecture and implementation plan

### 5.1. Target architecture for our stack

Do not replace React, Zustand or the WebSocket. Build a presentation
management layer ON TOP of the existing infrastructure:

```
Multi-agent backend + Event Bus
  (text deltas · run events · tool events · artifacts · UI proposals)
    → WebSocket Protocol Adapter (framing · sequencing · validation · reconnection · AG-UI compat)
    → Event Store (events · runs · states · artifacts)
    → Workspace Reconciler (policies · focus · permissions · proposals)
    → Zustand (state projection — NOT another event bus)
    → React 18 + TypeScript + Vite + framer-motion (Surface Renderer · Chat · Companion)
```

Flow: `WebSocket → validation → event reducer → normalized state → reconciler
→ renderer`. React components never interpret LLM messages directly. The
run's durable state lives server-side; Zustand is not the source of truth
for execution.

### 5.2. Multi-agent synchronization: identities and concurrency

```ts
type AgentEvent = {
  eventId: string; sessionId: string; runId: string; agentId: string;
  seq: number; type: string; payload: unknown;
};
```

`seq`: monotonic order per run (a timestamp does not suffice to order
asynchronous events). Strategy: idempotent events (no duplicates after
reconnection), snapshot + ordered deltas, sequence-gap detection +
resynchronization, state revisions against silent concurrent writes,
surface attribution to verified producers, resumable artifact inspection
after WS failure.

### 5.3. Security: the catalog is necessary but insufficient

A declarative interface constrains what the model produces; it does not
neutralize indirect injections (a malicious research document can ask the
LLM to create a deceptive component or an unauthorized action — OWASP
LLM01).

| Risk | Defense |
|---|---|
| Unknown component | Strict validation, reject |
| Unauthorized property | Closed schema |
| Arbitrary action | Action registry + server permissions |
| Fake privileged agent | Identity from the authenticated bus, not the payload |
| Injected HTML/script | Safe React rendering, strict Markdown/URL handling |
| Surface covering critical controls | Geometric constraints from the layout engine |
| Too many components | Depth, volume, frequency limits |
| Old event overwriting new | Revisions + sequence numbers |
| False success confirmation | Status derived from the real tool result |
| Exfiltration via URL | URL policy, origin control, destination validation |

Never may an agent modify permissions, hide a security control, or generate
an approval request outside the product's authorization mechanism. An
`ApprovalCard` is fed by a backend-authenticated request.

### 5.4. Four-phase incremental plan

**Phase 1 — Deterministic adaptive workspace** (foundations,
instrumentation). `WorkspaceStore`, `SurfaceRegistry`,
`WorkspaceReconciler`; three panel states (closed / peek / open). **No LLM
in interface choice at this stage** — trigger on existing events (artifact
created, run started, evidence ready). Testable: focus stability,
restoration after reload, responsive behavior, no artifact loss, render
performance. Risk: transitions that disturb even when the surface choice is
correct.

**Phase 2 — Curated templates and LLM proposals** (presentation
intelligence). Templates `research/code/document/board/review`; validated
proposal schema, priority rules, rejection mechanism. **Shadow mode first**:
the agent proposes, the reference UI does not change; compare against
expected scenarios, then progressively enable what is safe. Testable:
relevance, cross-turn stability, avoidable changes, reconciler rejection
rate, catalog conformance. Risk: mistaking a seductive proposal for a real
need.

**Phase 3 — Collaborative state and living evidence** (functional
advantage). Snapshots/deltas, durable artifact identifiers, shared
selection context, authorized frontend actions. E.g.: an evidence selection
on the board becomes a structured reference in the user's next request.
Validation cycles: action proposal → approval → execution → result → trace.
Testable: multi-agent sync, WS recovery, conflicts, provenance. Risk:
confusing presentation state, business state and execution authority.

**Phase 4 — Contextual companion and advanced orchestration**
(differentiation, conditional on proof). State machine, **anchored mode
first**; contextual movement behind a feature flag. Testable: time to
commands, interruptions, click errors, perceived nuisance, voluntary
disablement. Risk: investing in a visual signature whose functional
contribution remains low.

### 5.5. Testing strategy

Controlled comparisons: (A) chat + manually accessible artifacts; (B) chat +
deterministic contextual surface; (C) B + agent presentation proposals. The
robot gets a **separate** experiment.

Priority metrics: time to useful information; completion rate; avoided
navigation actions; context errors (wrong artifact/run); unwanted layout
changes; focus loss; multi-turn stability; subjective load.

Reproducible scenarios: multi-source research, failing code execution,
subagent switch, board modification during a run, reconnection, malicious
injection, animation disablement. **Each scenario includes several
successive turns**, not a final screenshot.

## 6. Critical evaluation of the vision

| Product hypothesis | Assessment | What must be proven |
|---|---|---|
| The robot gives a feeling of living work | Plausible | Does its presence improve status comprehension? |
| Free movement makes the agent more natural | **Weakly supported** | Does it reduce interactions rather than disrupting them? |
| Task templates reduce friction | Solid, conditionally | Better continuity on hybrid tasks? |
| A constrained catalog improves reliability | Strongly justified architecturally | Does it really limit errors and unwanted surfaces? |
| The contextual right panel improves efficiency | Promising | Does it speed up artifact inspection and comparison? |
| Shared agent/UI state improves collaboration | Very promising | Does it avoid ambiguous references and user repetition? |
| A fully morphable UI is always superior | **Undemonstrated** | Do the gains exceed the cost of spatial instability? |
| The interface should ship with the agent | Good direction | Which decisions should the model really control? |

**Where the competitive advantage lies**: not in the companion's appearance
nor in the number of layouts an LLM can produce, but in the ability to make
agent work **immediately inspectable, manipulable, verifiable and
resumable**. An interface that lets you understand the process (agent
collects → artifact → execution → error → correction → decision) and
intervene at the right level, without exploring dozens of messages.

> The interface follows the work, not the agent's imagination.
> The interface ships with the agent — but control stays with the user.

## 7. Bibliography

### Protocols and implementations
- A2UI official: https://a2ui.org — Spec v0.9: https://a2ui.org/specification/v0.9-a2ui/ — v0.9.1: https://a2ui.org/specification/v0.9.1-a2ui/ — v1.0 candidate: https://a2ui.org/specification/v1.0-a2ui/ — Evolution Guide: https://a2ui.org/specification/v0.9.1-evolution-guide/
- A2UI + A2A Extension: https://github.com/a2ui-project/a2ui/blob/main/specification/v0_9/docs/a2ui_extension_specification.md
- AG-UI: https://github.com/ag-ui-protocol/ag-ui — Events: https://docs.ag-ui.com/concepts/events — State: https://docs.ag-ui.com/concepts/state — Generative UI specs: https://docs.ag-ui.com/concepts/generative-ui-specs
- CopilotKit Generative UI: https://github.com/CopilotKit/generative-ui — Dojo: https://dojo.ag-ui.com/

### OpenAI and Apple
- OpenAI Intelligent UI (Oct 7, 2026): https://openai.com/index/gpt-6-for-everyone/
- OpenAI Generative UI Structured Outputs: https://github.com/openai/openai-structured-outputs-samples/blob/main/generative-ui/README.md
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Canvas: https://openai.com/index/introducing-canvas/ — Apps SDK: https://openai.com/index/introducing-apps-in-chatgpt/
- Apple Materials/Liquid Glass: https://developer.apple.com/design/human-interface-guidelines/materials
- Apple Ornaments: https://developer.apple.com/design/human-interface-guidelines/ornaments
- Apple Spatial Layout: https://developer.apple.com/design/human-interface-guidelines/spatial-layout
- App Intents / Siri: https://developer.apple.com/documentation/appintents/apple-intelligence-and-siri-ai — WWDC26 session 343: https://developer.apple.com/videos/play/wwdc2026/343/

### Academic research
- Chen et al. (2025), Generative Interfaces for Language Models: https://arxiv.org/abs/2508.19227
- Cao, Jiang & Xia (CHI 2025), Generative and Malleable User Interfaces: https://doi.org/10.1145/3706598.3713285
- Peng et al. (2026), Efficient Personalization of Generative User Interfaces: https://arxiv.org/abs/2604.09876
- Imteyaz et al. (2026), Design Theater: https://arxiv.org/abs/2607.22928
- Peng et al. (2026), EvoGenUI-Bench: https://arxiv.org/abs/2608.29387
- Li et al. (2026), When Interfaces Speak: https://arxiv.org/abs/2610.11123
- Cunningham et al. (2026), Context Matters!: https://arxiv.org/abs/2610.21484
- Ma et al. (2026), Beyond Activation: https://arxiv.org/abs/2610.09284
- IEEE ISMAR 2026, Spatial User Interfaces: https://www.ieeeismar.net/2026/papers/
- Rickenberg & Reeves (CHI 2000), The Effects of Animated Characters…: https://doi.org/10.1145/332040.332406
- Horvitz (CHI 1999), Principles of Mixed-Initiative User Interfaces: https://doi.org/10.1145/302979.303030
- Iqbal & Bailey (CHI 2008), Effects of Intelligent Notification Management…: https://doi.org/10.1145/1357054.1357070
- Weiser & Brown (1995), Designing Calm Technology: https://calmtech.com/papers/designing-calm-technology

### Security and accessibility
- OWASP LLM Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- WCAG 2.2 Animation from Interactions: https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions
- WCAG 2.2 Reflow: https://www.w3.org/WAI/WCAG22/Understanding/reflow.html

## Conclusion — recommended decisions

1. Keep the WebSocket and the existing React catalog. Introduce A2UI/AG-UI
   progressively, no migration on principle.
2. Build the reconciler BEFORE letting an LLM modify surfaces.
3. Templates are composable work modes, not six mutually exclusive screens.
4. Right panel = artifact space, not a second conversational stream.
5. Defer the mobile robot to an isolated experiment; an anchored, discreet,
   immediately useful companion is a more defensible base.

Concrete first milestone: a user launches a task, sees only the necessary
surfaces appear, consults evidence and execution output in real time,
edits the board, then resumes work without context loss or untimely
reorganization. **If this experience works without a robot, the essential
part of the problem is solved.** The companion can then become the embodied
interface of that capability, instead of trying to replace it.
