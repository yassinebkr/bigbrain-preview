# BigBrain — Multi-Brain AI Agent System

A modular, async AI agent system built on a **3-layer architecture** with specialized brain topologies, event-driven orchestration, and focus-managed attention.

> **Preview Implementation** — Full reference codebase with 523 tests. The [real project](https://github.com/yassinebkr/bigbrain) is built incrementally by hand.

## Quick Start

```bash
git clone https://github.com/yassinebkr/bigbrain-preview.git
cd bigbrain-preview

# Core + TUI + tests
pip install pydantic rich textual litellm pytest pytest-asyncio

# Voice (optional)
pip install websockets sounddevice numpy

# Authenticate with Claude (free via Pro/Max subscription)
python -m bigbrain --login

# Run
python -m bigbrain
```

### Environment (`.env`)
```bash
# LLM (used when NOT using OAuth)
BIGBRAIN_MODEL=anthropic/claude-opus-4-6
BIGBRAIN_FRONT_MODEL=anthropic/claude-opus-4-6
BIGBRAIN_CODE_MODEL=anthropic/claude-sonnet-4-20250514

# Voice (optional)
DEEPGRAM_API_KEY=dg-...
CARTESIA_API_KEY=sk-cart-...
CARTESIA_VOICE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# System
BIGBRAIN_LOG_DIR=logs
BIGBRAIN_MAX_TOKENS=2048
BIGBRAIN_CODE_TIMEOUT=30
BIGBRAIN_TEMPERATURE=0.7
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
| PythonBrain | ✅ | Subprocess code execution with timeout, lifecycle events |
| ResearcherBrain | ✅ | Research planning + summarization |
| Front Brain | ✅ | Real Claude LLM via OAuth, conversation history, code auto-execution |

### Orchestration
| Feature | Status | Description |
|---------|--------|-------------|
| WorkspaceOrchestrator | ✅ | DAG decomposition, ReWOO variable refs, brain load balancing |
| Task Cancellation | ✅ | Soft (cooperative) + hard (kill) modes |
| Execution Modes | ✅ | Lightning (auto) / Control (human gate) / Custom (per-brain) |
| Task Timeout | ✅ | Configurable TTL with cleanup loop and callback |

### Verification (5-layer pipeline)
| Layer | Status | Description |
|-------|--------|-------------|
| V1 Schema | ✅ | Pydantic output validation |
| V2 Sandbox | 🔲 | OS-level isolation (bubblewrap — production only) |
| V3 Cross-Check | ✅ | Different-provider LLM reviews brain output |
| V4 Deterministic | ✅ | Syntax checks, test runners, type checking |
| V5 Human Gate | ✅ | Async approval with configurable timeout |

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
| litellm Provider | ✅ | Multi-provider LLM routing |
| Mock Provider | ✅ | Realistic responses for testing |

### UI
| Feature | Status | Description |
|---------|--------|-------------|
| Morphable UI (Web) | ✅ | Glassmorphic workspace-based UI with FLIP animations, 7 layout grids, 9 panel types |
| Textual TUI | ✅ | 4-panel layout: chat, brains, tasks, bus/focus |
| Rich Fallback | ✅ | Console output when Textual unavailable |

### Morphable UI — Web Interface
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

### Web Mode (Morphable UI)
```bash
python -m bigbrain --web --web-port 3007
```
Opens the Morphable UI web interface. Access at `http://localhost:3007`.

Set `BIGBRAIN_WEB_PASSWORD` env var to enable Basic Auth.

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
# Full suite (523 tests)
python -m pytest tests/ -v

# By module
python -m pytest tests/test_bus.py -v           # Bus (14 tests)
python -m pytest tests/test_brain.py -v          # Brains (24 tests)
python -m pytest tests/test_python_brain.py -v   # PythonBrain (25 tests)
python -m pytest tests/test_orchestrator.py -v   # Orchestrator (28 tests)
python -m pytest tests/test_bus_auth.py -v       # HMAC auth (22 tests)
python -m pytest tests/test_bus_participant.py -v # BusParticipant (17 tests)
python -m pytest tests/test_v3_cross_check.py -v # V3 verification (19 tests)
python -m pytest tests/test_v5_human_gate.py -v  # V5 human gate (21 tests)
python -m pytest tests/test_execution_modes.py -v # Execution modes (30 tests)
python -m pytest tests/test_voice_real.py -v     # Voice providers (66 tests)
python -m pytest tests/test_memory.py -v         # Memory system
python -m pytest tests/test_verification.py -v   # Verification pipeline
```

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
├── verification/         # 5-layer verification pipeline
│   ├── pipeline.py       # Pipeline orchestration
│   ├── v1_schema.py      # Pydantic output validation
│   ├── v3_cross_check.py # Cross-provider LLM review
│   ├── v4_deterministic.py # Syntax, tests, types
│   └── v5_human_gate.py  # Async human approval
├── llm/                  # LLM provider abstraction
│   ├── provider.py       # ABC for LLM providers
│   ├── anthropic_oauth.py # OAuth + Claude Code stealth headers
│   ├── litellm_provider.py # Multi-provider via litellm
│   └── mock_provider.py  # Mock with realistic responses
├── voice/                # Voice pipeline
│   ├── deepgram_stt.py   # Deepgram Nova-3 WebSocket streaming
│   ├── cartesia_tts.py   # Cartesia Sonic REST + WebSocket
│   ├── stt.py            # MockSTT for testing
│   ├── tts.py            # MockTTS for testing
│   └── voice_manager.py  # Pipeline coordinator + auto-detection
├── auth/                 # Authentication
│   └── oauth.py          # Anthropic PKCE OAuth flow
├── tui/                  # Textual TUI
│   ├── app.py            # Main 4-panel application
│   ├── app.css           # Dark theme styling
│   └── widgets/          # Chat, brains, tasks, bus, focus panels
├── web/                  # Morphable UI (Phase 3 WebAdapter)
│   ├── server.py         # aiohttp WS bridge, Basic Auth, static serving
│   ├── adapter.py        # WebAdapter (UIAdapter implementation)
│   ├── focus_bridge.py   # Bidirectional Focus ↔ UI sync
│   ├── pipeline_manager.py # Server-side pipeline validation
│   └── static/           # Client-side (zero dependencies)
│       ├── app.js        # MorphableUI orchestrator, workspace switching
│       ├── morph.js      # Spring FLIP engine, CSS linear() generator
│       ├── layout.js     # 7 layout grids, SlotManager, workspace configs
│       ├── panel.js      # 9 panel types (chat, code-output, research, etc.)
│       ├── bus-client.js # WebSocket bus client, auto-reconnect
│       ├── pipeline.js   # 3 pipeline runners (bus/http-poll/websocket)
│       ├── style.css     # Glassmorphic dark theme, 24 sections
│       └── index.html    # App shell
├── ui/                   # Rich fallback UI
│   ├── ui_adapter.py     # ABC for UI adapters
│   └── rich_adapter.py   # Rich console implementation
├── config.py             # Configuration (env + defaults)
└── __main__.py           # Entry point + system coordinator
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| LLM Interface | litellm + custom Anthropic OAuth provider |
| Auth | Anthropic OAuth (PKCE) — free via Pro/Max subscription |
| Memory | ChromaDB (PersistentClient) + vector embeddings |
| Schemas | Pydantic v2 |
| Concurrency | asyncio |
| Bus Auth | HMAC-SHA256 per-brain tokens |
| STT | Deepgram Nova-3 (WebSocket streaming, ~100ms) |
| TTS | Cartesia Sonic (REST + WebSocket, sub-100ms) |
| Terminal UI | Textual 8.x (dark theme, 4-panel layout) |
| Fallback UI | Rich (console panels) |
| Tests | pytest + pytest-asyncio (523 tests) |
| Web Server | aiohttp (async WS bridge to MessageBus) |
| Web UI | Vanilla JS + WAAPI (zero dependencies) |

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

- **Real project**: [github.com/yassinebkr/bigbrain](https://github.com/yassinebkr/bigbrain) (private)
- **Research**: MASS (Google ICLR 2026), Spotify Honk, LLMCompiler, ReWOO, Andrew Ng patterns
