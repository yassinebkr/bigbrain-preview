# BigBrain — Multi-Brain AI Agent System

A modular, async AI agent system built on a **3-layer architecture** with specialized brain topologies, event-driven orchestration, and focus-managed attention.

> **Active development repo.** What started as the preview reference codebase
> is now the working product (web UI, models/auth, deterministic harness).

## Quick Start

```bash
git clone https://github.com/yassinebkr/bigbrain-preview.git
cd bigbrain-preview

# Backend (core + web + tests)
pip install -e ".[test,web]"

# Web UI (React app in web-ui/, served by the backend at /)
cd web-ui && npm install && npm run build && cd ..

# Authenticate with Claude (free via Pro/Max subscription)
python -m bigbrain --login

# Run the web product
python -m bigbrain --web --web-port 3007
```

### Environment (`.env`)
```bash
# LLM (used when NOT using OAuth)
BIGBRAIN_MODEL=anthropic/claude-opus-4-6
BIGBRAIN_FRONT_MODEL=anthropic/claude-opus-4-6
BIGBRAIN_CODE_MODEL=anthropic/claude-sonnet-4-20250514

# Registry providers (docs/MODELS.md):
# OpenRouter — one key unlocks kimi k3, gpt sol, opus 5.5, k2.7-code, luna
# OPENROUTER_API_KEY=sk-or-v1-...
# MISTRAL_API_KEY (set automatically by the Connect-with-Mistral button)
# KIMI_API_KEY (direct coding endpoint)
# BIGBRAIN_PROVIDER=codex-chatgpt  # force a registry provider

# Voice (optional)
DEEPGRAM_API_KEY=dg-...
CARTESIA_API_KEY=sk-cart-...
CARTESIA_VOICE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# System
BIGBRAIN_LOG_DIR=logs
BIGBRAIN_MAX_TOKENS=2048
BIGBRAIN_CODE_TIMEOUT=30
BIGBRAIN_TEMPERATURE=0.7

# Deterministic harness (P1-P4) — 0 disables evidence recording
BIGBRAIN_EVIDENCE=1
BIGBRAIN_EVIDENCE_ROOT=data/evidence
```

## Architecture

BigBrain splits intelligence into three distinct layers, connected by a CAN bus-style message bus:

```
User ←→ Front Brain ←→ Bus ←→ Orchestrator(s) ←→ Sub-brains
              ↕                       ↕
         Focus Rules            RT State Stream
              ↕                       ↕
         Morphable UI ←—————————————————
```

### Layer 1 — Front Brain (User-Facing Intelligence)
- The "person" the user talks to — personality, context, relationship
- Manages the **Focus System**: filters bus events based on attention mode
- Translates technical bus events into human language
- **NOT a narrator.** Silent by default, speaks when relevant — like a real colleague
- Drives voice pipeline (STT/TTS) when enabled
- **Model: Opus** — the smartest available. Sub-brains can use cheaper models.

### Layer 2 — Orchestrator(s) (Task Management)
- Pure task decomposition and routing. Never talks to the user directly.
- One orchestrator per workspace (web dev, research, electronics, etc.)
- Event-driven message handler (NOT a blocking loop)
- DAG-based dependency resolution with ReWOO-style variable references
- **RT State Streaming**: publishes typed events continuously
- Configurable **execution modes** per brain (Lightning / Control / Custom)

### Layer 3 — Sub-brains (Independent Workers)
- Standalone workers. Don't know about the user. Receive tasks, execute, return results.
- Each brain has its own **loop topology** (Honk, ReWOO, etc.)
- Multiple brains per workspace can collaborate
- Monitored by their workspace's Orchestrator via heartbeats

## Implemented Features

### Core Infrastructure
| Feature | Status | Description |
|---------|--------|-------------|
| Message Bus | ✅ | Async pub/sub, wildcard routing, concurrent dispatch, disk logging |
| Bus Authentication | ✅ | HMAC-SHA256 per-brain tokens, auto-sign/verify |
| BusParticipant | ✅ | Shared base class for Brains + Orchestrators |
| BusMessage | ✅ | Pydantic-typed with priority (P0-P3), workspace, signature |

### Brains
| Feature | Status | Description |
|---------|--------|-------------|
| BaseBrain | ✅ | Abstract base with lifecycle, error events, double-start guard |
| PythonBrain | ✅ | Worker pool (3), subprocess execution with timeout/unique temp scripts, 7 task types (generate_and_execute, run_file, edit_file, write_project_file, assemble_and_run, batch_write_files, search_project) |
| ResearcherBrain | ✅ | Research planning + summarization (Brave search, LLM synthesis) |
| Front Brain | ✅ | Real-time chat.delta streaming, delegation routing to the orchestrator, project context injection |

### Orchestration
| Feature | Status | Description |
|---------|--------|-------------|
| WorkspaceOrchestrator | ✅ | DAG decomposition, ReWOO variable refs, brain load balancing |
| Task Cancellation | ✅ | Soft (cooperative) + hard (kill) modes |
| Execution Modes | ✅ | Lightning (auto) / Control (human gate) / Custom (per-brain) |
| Task Timeout | ✅ | Configurable TTL with cleanup loop and callback |

### Verification (5-layer pipeline + deterministic harness)
| Layer | Status | Description |
|-------|--------|-------------|
| V1 Schema | ✅ | Pydantic output validation |
| V2 Sandbox | 🔲 | OS-level isolation (bubblewrap — production only) |
| V3 Cross-Check | ✅ | Different-provider LLM reviews brain output |
| V4 Deterministic | ✅ | Syntax checks, test runners, type checking |
| V5 Human Gate | ✅ | Async approval with configurable timeout |
| Evidence core | ✅ | DesignSpec / RunManifest / EvidenceRepository — immutable, hash-linked, content-addressed artifacts (sha256) |
| Gate + stages | ✅ | syntax → compile → run → tests → contracts, conservative verdict (inconclusive is never a pass), wired into the Honk retry loop |
| Replay + golden | ✅ | Re-execute recorded runs in a clean subprocess and diff the outputs; LLM-independent golden corpus (hello, fibonacci, file_io, unicode) |

### Focus System
| Feature | Status | Description |
|---------|--------|-------------|
| Focus Modes | ✅ | Deep Focus / Normal / Overview |
| Workspace States | ✅ | Active / Peripheral / Background |
| Priority Filtering | ✅ | P0 (critical) through P3 (low) |
| Event Buffering | ✅ | Deferred delivery on focus switch |
| Focus Suggestions | ✅ | Idle detection, break suggestions, attention alerts |

### Memory (3-tier)
| Tier | Status | Description |
|------|--------|-------------|
| Working Memory | ✅ | Ephemeral per-brain context (in-memory) |
| Project Memory | ✅ | Workspace-scoped ChromaDB with embeddings |
| Long-term Memory | ✅ | Cross-workspace knowledge, single collection with scope field |

### Voice Pipeline
| Feature | Status | Description |
|---------|--------|-------------|
| Deepgram STT | ✅ | Nova-3 WebSocket streaming, microphone capture |
| Cartesia TTS | ✅ | Sonic REST + WebSocket streaming, voice selection |
| VoiceManager | ✅ | State machine, wake words, auto-listen loop |
| Auto-detection | ✅ | `create_voice_manager()` — real APIs if keys present, mock fallback |

### Auth & LLM
| Feature | Status | Description |
|---------|--------|-------------|
| Anthropic OAuth | ✅ | PKCE flow, `--login` CLI, token persistence |
| AnthropicOAuthProvider | ✅ | Raw httpx with Claude Code stealth headers |
| Model Registry | ✅ | 10 entries (OpenRouter, Kimi direct, Mistral vibe, GLM 5.3, Codex, Claude), free health checks (60s cache), per-role lineup (front/planner/code/subagent) |
| Auth facade (`bigbrain/auth/`) | ✅ | Mistral PKCE wizard, OpenRouter key input, Codex subscription login, provider hot-reload without restart |
| litellm Provider | ✅ | Multi-provider LLM routing |
| Mock Provider | ✅ | Realistic responses for testing |

### Projects & Workspace
| Feature | Status | Description |
|---------|--------|-------------|
| Projects | ✅ | Per-project sub-workspaces (`.project.json` manifests), selector in the explorer, current project persisted |
| Sandbox default | ✅ | No project selected → agent writes land in the auto-created `sandbox/` project (no more loose pools) |
| FS API | ✅ | list / read / write / mkdir / rename / move / delete / **run** (bounded .py execution) / **search** (dot-entries skipped) |

### UI
| Feature | Status | Description |
|---------|--------|-------------|
| **Web Product (web-ui/)** | ✅ | React 18 + TypeScript + Vite + Tailwind + Framer Motion (Aplot port) — the primary interface, served from `web-ui/dist` |
| Morphable UI (legacy static) | ✅ | Glassmorphic workspace-based UI with FLIP animations, 7 layout grids, 9 panel types (kept as the morphable core prototype) |
| Textual TUI | ✅ | 4-panel layout: chat, brains, tasks, bus/focus |
| Rich Fallback | ✅ | Console output when Textual unavailable |

### Web Product (web-ui/)
| Feature | Status | Description |
|---------|--------|-------------|
| Real-time chat | ✅ | `chat.delta` streaming, markdown bubbles, stop button (cancels the LLM stream AND the orchestrated run) |
| Model lineup | ✅ | Available-only dropdown (free health checks), per-role selection (front/planner/code/subagent) |
| Run panel | ✅ | Live run state derived from bus events (no per-event timers), persistent across reloads, per-step brains/durations, clickable written files, sandbox nudge, gate-verdict chip + stage pills |
| Code surface | ✅ | Shared highlight (multi-language) / run (stdout/stderr inline) / edit (Ctrl+S) component — modal in chat, inline pane in the workspace |
| Tasks & Brains tabs | ✅ | TaskBoard on real bus tasks (starts empty — zero mock data), brain status dots + live activity feed |
| Workspace | ✅ | Project file explorer, project selector, research bar with real FS search |
| Providers panel | ✅ | Model availability, OpenRouter key input, Connect-with-Mistral / Connect-with-ChatGPT wizards, provider reload |

### Morphable UI — Web Interface (legacy core)
| Feature | Status | Description |
|---------|--------|-------------|
| Spring FLIP Engine | ✅ | Custom WAAPI + CSS `linear()` spring physics, 5 presets, zero deps |
| Layout Catalog | ✅ | 7 pre-designed grids (focus, split, tri-left, quad, etc.) — agent never creates layouts |
| Workspace Tabs | ✅ | 6 domain-tailored workspaces: Home, Python, Research, Web, 3D Print, Electronics |
| Autonomous Panels | ✅ | Panels self-update via bus subscription. 9 types: chat, brain-status, task-list, code-output, research-results, bus-monitor, pipeline, placeholder, status-strip |
| Persistent Panels | ✅ | Chat, Tasks, Brain Status survive workspace switches — no state loss |
| Global Result Buffer | ✅ | Results captured even when target workspace panel doesn't exist yet |
| LLM Result Summary | ✅ | Front Brain uses LLM to turn raw stdout into a conversational answer |
| Data Pipelines | ✅ | Agent-defined sources (bus/http-poll/websocket) + JSON path transforms |
| WebSocket Bridge | ✅ | aiohttp WS server bridges browser ↔ Python MessageBus, anti-spoof source forcing |
| Focus Sync | ✅ | Bidirectional: UI workspace switch ↔ FocusManager, rate-limited broadcasts |
| Auth | ✅ | HTTP Basic Auth + WS token query param (Cloudflare tunnel compatible) |
| Design | ✅ | Glassmorphism, SVG noise grain, WCAG AA contrast, Geist font, indigo accent |

## Brain Loop Topologies

### Python Brain → Spotify Honk Pattern
```
┌─── Outer Loop (Cross-Provider Review) ───┐
│  ┌── Inner Loop (Deterministic) ──┐      │
│  │  LLM → code → verify → fix    │      │
│  │  (pytest + mypy + ruff)        │      │
│  └────────────────────────────────┘      │
│  Cross-provider LLM review               │
│  Exit gate: V4 → V1 → V3 → V5           │
└──────────────────────────────────────────┘
```

### Researcher Brain → ReWOO + Source Triangulation
```
Plan all steps upfront → parallel execution (3.6x speedup)
→ source triangulation → synthesize with citations
```

## Verification Pipeline

Every brain output passes through verification layers, ordered cheapest-first:

```
V4 (syntax/tests) → V1 (schema) → V3 (cross-provider LLM) → V5 (human gate)
```

**Key rule**: Worker and verifier use DIFFERENT LLM providers.

Execution modes control which layers run per brain:
- **Lightning**: V4 + V1 only (full auto)
- **Control**: All layers including V5 human approval
- **Custom**: Per-brain configuration

### Deterministic Harness (P1–P4)

On top of the V-layers, every Python execution attempt goes through a
conservative evidence gate (`bigbrain/verification/`, ported from the
fpga backend patterns — see [docs/HARNESS-DETERMINISTE.md](docs/HARNESS-DETERMINISTE.md)):

```
DesignSpec (what was asked) ──hash──→ RunManifest (what happened)
     │                                      │
     │   stages: syntax → compile → run → tests → contracts
     │   verdict: passed | failed | inconclusive  (inconclusive is NEVER a pass)
     └── artifacts: sha256 content-addressed (code, stdout, stderr, test output)
```

- **Immutable evidence**: terminal manifests cannot be rewritten; every
  attempt chains to the previous via `parent_run_id`.
- **Gate in the Honk loop**: a `failed` verdict feeds the stage details
  back to the LLM (retry); an `inconclusive` one is labelled
  "not fully verified" instead of claimed.
- **Replay**: `replay_run()` re-executes a recorded run in a clean
  subprocess and diffs the outputs — non-determinism is detected.
- **Golden corpus**: LLM-independent cases (hello, fibonacci, file_io,
  unicode) regression-test the execution machinery itself.
- **UI**: the run panel shows the verdict chip and per-stage pills
  (`verification.run_recorded` event); kill switch: `BIGBRAIN_EVIDENCE=0`.

## Focus System

| Mode | What reaches the user | Use case |
|------|----------------------|----------|
| **Deep Focus** | P0 only (critical) | In the zone, don't interrupt |
| **Normal** | P0 + P1 (critical + high) | Standard working |
| **Overview** | P0 + P1 + P2 (all but low) | Checking on everything |

| Priority | Name | Examples |
|----------|------|----------|
| P0 | Critical | Security breach, system crash |
| P1 | High | Task failed, human input needed |
| P2 | Normal | Task complete, build passed |
| P3 | Low | Heartbeats, minor progress |

## Usage

### Web Mode (product UI)
```bash
# Build the React UI once (or after UI changes)
cd web-ui && npm install && npm run build && cd ..

python -m bigbrain --web --web-port 3007
```
Opens the web product at `http://localhost:3007` — chat with streaming,
run panel with verification pills, workspace explorer, Tasks/Brains
tabs. The legacy morphable UI's static assets remain served under
`/static/`.

Set `BIGBRAIN_WEB_PASSWORD` env var to enable Basic Auth.

The `⚙ Providers` button opens the settings panel: model availability
(OpenRouter / Mistral / Kimi / Codex / Claude), a **Connect with ChatGPT**
button (codex subscription OAuth — the server opens the login URL and
codex stores the credentials), a **Connect with Mistral** button (browser
PKCE wizard), and the live token/cost ledger. See [docs/AUTH.md](docs/AUTH.md)
and [docs/MODELS.md](docs/MODELS.md).

### Interactive Mode (TUI)
```bash
python -m bigbrain
```
Opens the Textual TUI. Chat with the Front Brain, watch bus events, monitor brain status.

### Simple Mode (no TUI)
```bash
python -m bigbrain --simple
```
Falls back to Rich console output.

### OAuth Login
```bash
python -m bigbrain --login    # Authenticate with Claude
python -m bigbrain --logout   # Clear stored token
```

### Deployment (systemd)
```bash
# Create a systemd user service
cat > ~/.config/systemd/user/bigbrain-web.service << EOF
[Unit]
Description=BigBrain Web UI

[Service]
WorkingDirectory=/path/to/bigbrain-preview
ExecStart=/usr/bin/python3 -m bigbrain --web --web-port 3007 --mock-voice
Environment=PYTHONUNBUFFERED=1
Environment=BIGBRAIN_WEB_PASSWORD=your-password
Restart=always

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now bigbrain-web
```

### Run in Separate Terminal
**Important**: Run BigBrain in a standalone PowerShell/terminal, NOT VS Code's integrated terminal. VS Code captures keyboard shortcuts that conflict with the TUI.

## Tests

```bash
# Backend full suite (743+ tests)
python -m pytest tests/ -q --ignore=tests/test_voice_real.py

# Frontend (vitest — store state machine, 14 tests)
cd web-ui && npm run test

# Frontend type-check + production build
cd web-ui && npm run build
```

CI (GitHub Actions): Python 3.12/3.13 matrix (`pip install -e ".[test,web]"`,
ruff non-blocking, two environment-fragile tests deselected) plus a
frontend job (npm ci + vitest + build).

## Project Structure

```
bigbrain/
├── bus/                  # Message bus infrastructure
│   ├── bus.py            # Async pub/sub, concurrent dispatch
│   ├── message.py        # BusMessage + Priority + MessageType
│   ├── auth.py           # HMAC-SHA256 message authentication
│   ├── participant.py    # BusParticipant base class
│   └── logger.py         # JSONL disk logger
├── front/                # Layer 1 — User-facing intelligence
│   ├── front_brain.py    # Conversation, intent routing, code execution
│   └── focus_manager.py  # Attention filtering + workspace focus
├── orchestrator/         # Layer 2 — Task management
│   ├── orchestrator.py   # DAG decomposition, dispatch, tracking
│   └── execution_modes.py # Lightning/Control/Custom per brain
├── brains/               # Layer 3 — Execution workers
│   ├── base.py           # BaseBrain ABC (inherits BusParticipant)
│   ├── python_brain.py   # Code execution via subprocess
│   └── researcher.py     # Research + summarization
├── memory/               # 3-tier memory system
│   ├── working_memory.py     # Ephemeral per-brain
│   ├── project_memory.py     # ChromaDB workspace-scoped
│   ├── long_term_memory.py   # ChromaDB cross-workspace
│   ├── chromadb_backend.py   # ChromaDB integration
│   └── memory_manager.py     # Unified interface
├── verification/         # 5-layer pipeline + deterministic harness (P1-P4)
│   ├── pipeline.py       # Pipeline orchestration (V1-V5)
│   ├── v1_schema.py      # Pydantic output validation
│   ├── v3_cross_check.py # Cross-provider LLM review
│   ├── v4_deterministic.py # Syntax, tests, types
│   ├── v5_human_gate.py  # Async human approval
│   ├── evidence.py       # DesignSpec/RunManifest/EvidenceRepository — immutable evidence
│   ├── executors.py     # Deterministic stages: syntax/compile/run/tests/contracts
│   ├── gate.py           # Conservative verdict + chained manifests per attempt
│   ├── replay.py         # Re-execute recorded runs, diff outputs
│   └── golden.py         # LLM-independent regression corpus
├── llm/                  # LLM provider abstraction
│   ├── provider.py       # ABC for LLM providers
│   ├── anthropic_oauth.py # OAuth + Claude Code stealth headers
│   ├── litellm_provider.py # Multi-provider via litellm
│   ├── openai_compat_provider.py # OpenRouter/Mistral/Kimi (SSE, reasoning deltas)
│   ├── codex_provider.py # Codex subscription via `codex app-server` JSON-RPC
│   ├── model_registry.py # 10-entry registry, free health checks, capabilities
│   ├── usage.py          # Token accounting + per-role budgets
│   └── mock_provider.py  # Mock with realistic responses
├── voice/                # Voice pipeline (optional extra)
│   ├── deepgram_stt.py   # Deepgram Nova-3 WebSocket streaming
│   ├── cartesia_tts.py   # Cartesia Sonic REST + WebSocket
│   ├── stt.py / tts.py   # Mocks for testing
│   └── voice_manager.py  # Pipeline coordinator + auto-detection
├── auth/                 # Auth facade (unified)
│   ├── oauth.py          # Anthropic PKCE OAuth flow
│   ├── mistral_oauth.py  # Mistral vibe PKCE wizard
│   ├── openrouter_key.py # OpenRouter key input
│   └── registry.py       # Provider selection facade
├── tui/                  # Textual TUI
│   ├── app.py            # Main 4-panel application
│   └── widgets/          # Chat, brains, tasks, bus, focus panels
├── web/                  # Web backend
│   ├── server.py         # aiohttp WS bridge, Basic Auth, serves web-ui/dist
│   ├── fs_api.py         # Workspace FS API (list/read/write/run/search + projects)
│   ├── model_roles.py    # Per-role model lineup (persisted)
│   ├── adapter.py / focus_bridge.py / pipeline_manager.py
│   └── static/           # Legacy morphable UI (zero-dep vanilla JS)
├── ui/                   # Rich fallback UI
├── plugins.py            # Brain plugin manifests (builtin: python-brain, researcher)
├── system.py             # BigBrainSystem assembly + runtime hooks (reload/project/cancel)
├── cli.py / __main__.py  # Entry points
└── config.py             # Configuration (env + defaults)

web-ui/                   # The web product (React 18 + TS + Vite + Tailwind)
├── src/components/       # RunPanel, CodeSurface/CodeViewer, ChatView, Tasks/Brains views...
├── src/store/            # Zustand store (run state machine, persisted activeRun)
├── src/lib/connection/   # WS adapters (bigbrain protocol + scratchy)
└── dist/                 # Production build served by the backend
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ (backend) · TypeScript (frontend) |
| LLM Interface | litellm + OpenAI-compatible registry providers + Anthropic OAuth + Codex JSON-RPC |
| Auth | Anthropic OAuth (PKCE) · Mistral vibe PKCE · OpenRouter key · Codex subscription |
| Memory | ChromaDB (PersistentClient) + vector embeddings |
| Schemas | Pydantic v2 |
| Concurrency | asyncio |
| Bus Auth | HMAC-SHA256 per-brain tokens |
| Evidence | Content-addressed sha256 artifacts, immutable JSON manifests |
| STT | Deepgram Nova-3 (WebSocket streaming, ~100ms) |
| TTS | Cartesia Sonic (REST + WebSocket, sub-100ms) |
| Terminal UI | Textual 8.x (dark theme, 4-panel layout) |
| Fallback UI | Rich (console panels) |
| Tests | pytest + pytest-asyncio (743+) · vitest (frontend store) |
| CI | GitHub Actions — Python 3.12/3.13 matrix + frontend job (npm ci, vitest, build) |
| Web Server | aiohttp (async WS bridge to MessageBus) |
| Web Product | React 18 + Vite + Tailwind + Framer Motion + Zustand (web-ui/) |
| Legacy Web UI | Vanilla JS + WAAPI (zero dependencies) |

## Design Philosophy

- **3 layers, never collapse them.** Front Brain (user) → Orchestrator (tasks) → Sub-brains (execution).
- **Bus-decoupled.** Components only know about the bus. No direct calls.
- **Focus is a managed resource.** Attention dilution = bad output. Filter aggressively.
- **Cheapest verification first.** V4 (free) catches 80% of issues before V3 (costs money).
- **Cross-provider verification.** Worker and reviewer use different LLMs. Same-provider = blind spots.
- **Specialized beats full-stack.** Each brain has focused rules, not a generic "do everything" prompt.
- **The user decides.** System suggests, never forces context switches or interrupts (except P0).

## License

Dual license: AGPL-3.0 (core) + Commercial (contact for production use without open-source obligations).

## Links

- **Research**: MASS (Google ICLR 2026), Spotify Honk, LLMCompiler, ReWOO, Andrew Ng patterns
