# BigBrain — Multi-Brain AI Agent System

A modular, async AI agent system built on a **3-layer architecture** with specialized brain topologies, event-driven orchestration, and focus-managed attention.

> **Preview Implementation** — This is a reference/demo codebase. The [real project](https://github.com/yassinebkr/bigbrain) is built incrementally by hand.

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

### Layer 2 — Orchestrator(s) (Task Management)
- Pure task decomposition and routing. Never talks to the user directly.
- One orchestrator per workspace (web dev, research, electronics, etc.)
- Event-driven message handler (NOT a blocking loop)
- Tracks task state, manages dependencies, dispatches subtasks
- **RT State Streaming**: publishes typed events continuously (`brain.started`, `brain.progress`, `brain.verify`, `brain.complete`, `brain.error`)

### Layer 3 — Sub-brains (Independent Workers)
- Standalone workers. Don't know about the user. Receive tasks, execute, return results.
- Each brain has its own **loop topology** (see below)
- Multiple brains per workspace can collaborate
- Monitored by their workspace's Orchestrator via heartbeats

## Brain Loop Topologies

Each brain type uses a different execution loop architecture, chosen based on research into multi-agent patterns (MASS paper, Spotify Honk, LangChain, Andrew Ng patterns).

### Python Brain → Spotify Honk Pattern (Inner/Outer Loop)

```
┌─────────────── Outer Loop (Cross-Provider Review) ──────────────┐
│                                                                  │
│   ┌──────── Inner Loop (Deterministic Verification) ──────┐     │
│   │                                                        │     │
│   │   LLM generates code                                  │     │
│   │       ↓                                                │     │
│   │   Morph Fast Apply (merge edits into files)            │     │
│   │       ↓                                                │     │
│   │   verify() tool → pytest + mypy + ruff                 │     │
│   │       ↓                                                │     │
│   │   Pass? ──yes──→ Exit inner loop                       │     │
│   │    │no                                                 │     │
│   │    ↓                                                   │     │
│   │   Reflexion memory (don't repeat same mistake)         │     │
│   │    ↓                                                   │     │
│   │   Fix → loop back ─────────────────────────────────────┘     │
│   │                                                              │
│   Cross-provider LLM review (catches scope creep — 25% go       │
│   off-task per Spotify's findings)                               │
│       ↓                                                          │
│   Pass? ──yes──→ Exit gate: V4 → V1 → V3 → V5                  │
│    │no                                                           │
│    ↓                                                             │
│   Retry with feedback ──────────────────────────────────────────┘
```

**Key insight**: The agent never sees verifier internals — just pass/fail + focused error excerpt. This prevents the LLM from gaming the verifier.

### Researcher Brain → ReWOO + Source Triangulation

```
┌──────────── ReWOO Planning Phase ────────────┐
│                                               │
│   Decompose query into search plan            │
│   (all steps planned BEFORE execution)        │
│       ↓                                       │
│   ┌── Parallel Execution (LLMCompiler) ──┐   │
│   │   Search 1 ──→ results               │   │
│   │   Search 2 ──→ results    (3.6x      │   │
│   │   Search 3 ──→ results     speedup)  │   │
│   └──────────────────────────────────────┘   │
│       ↓                                       │
│   Source triangulation                        │
│   (cross-reference findings, score trust)     │
│       ↓                                       │
│   Synthesize summary with citations           │
└───────────────────────────────────────────────┘
```

**Why ReWOO over ReAct**: ReWOO plans all steps upfront → enables parallel execution. ReAct is sequential (observe→think→act→repeat). For research, parallelism matters.

### Future Brain Topologies (Planned)

| Brain | Topology | Pattern |
|-------|----------|---------|
| **DevOps** | Plan + Rollback | Execute with automatic rollback on failure |
| **Designer** | Self-Refine + Visual | Generate → render → self-critique → iterate |
| **Writer** | ReWOO Sequential | Plan structure → write sections → verify coherence |
| **Security** | Reflexion + Memory | Audit → remember past vulnerabilities → cross-reference |
| **KiCad** | MCP-Driven | Agent-driven PCB design via KiCad's IPC-API |

### Morph Fast Apply (Edit Merging Tool)

Not a brain — a tool inside the Python Brain's inner loop:
- 7B model specialized in merging code edit snippets into existing files
- 10,500 tok/s, 98% accuracy, $0.80/M input tokens
- Replaces brittle search-and-replace (84-96% accuracy) with purpose-built merging
- Flow: LLM generates edit snippet → Morph applies to file → verify → loop
- OpenAI-compatible API (works with litellm)

## Verification Pipeline

Every brain output passes through a 5-layer verification pipeline, ordered cheapest-first:

| Layer | Type | What | Cost |
|-------|------|------|------|
| V4 | Deterministic | Syntax, tests, types (no LLM) | Free |
| V1 | Schema | Pydantic output validation | Free |
| V2 | Sandbox | OS-level subprocess isolation | Free |
| V3 | Cross-Check | Different-provider LLM review | $ |
| V5 | Human Gate | Auto/review/notify per brain | Time |

**Key rule**: Worker and verifier use DIFFERENT LLM providers (cross-provider verification).

## Focus System

LLMs, like humans, need focus to be efficient. The Focus System manages attention as an explicit resource.

### Three Focus States Per Workspace
- **Active** — Full attention. All events reach Front Brain.
- **Peripheral** — Background monitoring. Only high-priority events (failures, completions).
- **Background** — Minimal attention. Only critical alerts break through.

### User-Selectable Focus Modes
- **Deep Focus** — Only critical (P0) events interrupt. Guards flow state.
- **Normal** — Critical + high priority. Standard working mode.
- **Overview** — All workspaces visible. "Project manager" mode.

### Priority Hierarchy

| Level | Name | Behavior | Examples |
|-------|------|----------|----------|
| P0 | Critical | Always interrupts | Security breach, system crash |
| P1 | High | Next natural pause | Task failed, human input needed |
| P2 | Normal | Buffered | Task complete, build passed |
| P3 | Low | Detail view only | Heartbeats, minor progress |

## Memory Architecture

### Tier 1: Working Memory (Ephemeral)
- Per-brain conversation context
- Dies with brain process

### Tier 2: Project Memory (ChromaDB)
- Per-workspace structured data with vector embeddings
- Semantic search within workspace scope

### Tier 3: Long-term Memory (ChromaDB)
- Cross-workspace knowledge, user preferences, lessons learned
- Vectorized, query by meaning

## Message Bus

CAN bus-style async pub/sub connecting all components:

- **Decoupled**: Components only know about the bus, not each other
- **Logged**: Every message persisted to disk (full replay for debugging)
- **Typed**: Pydantic-validated messages (`TASK`, `RESULT`, `EVENT`, `PROGRESS`, `CANCEL`, `QUERY`, `STATE`)
- **Priority-filtered**: Focus System filters events by priority level
- **Broadcast + point-to-point**: `target="*"` for events, specific target for tasks
- **Auth**: HMAC-SHA256 per-brain tokens (planned)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| LLM Interface | litellm (unified API, easy model swap) |
| Memory | ChromaDB + Google text-embedding-004 |
| Schemas | Pydantic v2 |
| Concurrency | asyncio |
| Sandboxing | subprocess (→ bubblewrap for production) |
| STT | Deepgram Nova-3 (streaming, ~100ms) |
| TTS | Cartesia Sonic (sub-100ms, natural voice) |
| Terminal UI | Textual (TUI) / Rich (fallback) |

## Installation

```bash
git clone https://github.com/yassinebkr/bigbrain-preview.git
cd bigbrain-preview

# Core dependencies
pip install pydantic rich

# For TUI mode
pip install textual

# For tests
pip install pytest pytest-asyncio
```

## Usage

### Demo Mode (default)
```bash
python -m bigbrain --mode demo
```
Runs automated demos showing code execution and file operations, then drops into interactive mode.

### Interactive Mode
```bash
python -m bigbrain --mode interactive
```
Direct conversation with the Front Brain.

### Simple Mode (no Textual TUI)
```bash
python -m bigbrain --simple
```
Falls back to Rich console output if Textual is unavailable.

### Options
```
--workspace NAME    Workspace name (default: demo)
--mode TYPE         interactive | demo (default: demo)
--log-dir DIR       Log directory (default: logs)
--tui               Use Textual TUI (default)
--simple            Use Rich console fallback
```

## TUI Layout

```
┌──────────────────────────────────────────────────────────────┐
│  BigBrain - Multi-Brain AI Agent System            00:00:00  │
├────────────────────────────────┬─────────────────────────────┤
│ 💬 Chat                       │ 🧠 Brains                   │
│                                │  Python: 🟢 idle             │
│ User: hey!                     │  Researcher: 🟢 ready        │
│ BigBrain: Hello! How can I     │  Voice: 🔇 disabled          │
│   help you today?              │                              │
│                                ├─────────────────────────────┤
│                                │ 📊 Tasks                     │
│                                │  No active tasks             │
├────────────────────────────────┼─────────────────────────────┤
│ 📡 Bus Monitor                 │ 🎯 Focus                    │
│ [01:22:49] EVENT               │ Mode: 🟢 Normal              │
│   orchestrator → *             │ Active: 📂 demo              │
│   orchestrator.started         │ Idle: ⚡ 2s                  │
│ [01:22:50] EVENT               │ ─────────────                │
│   bigbrain_system → *          │ Workspaces:                  │
│   system.ready                 │   🎯 demo (12)               │
│                                │   👁️ research (3)            │
├────────────────────────────────┴─────────────────────────────┤
│ Type your message... 💬                                       │
└──────────────────────────────────────────────────────────────┘
```

**Keybindings**: `Ctrl+C` quit · `F1` toggle focus mode · `F2` toggle voice · `F3` help · `Ctrl+L` clear chat · `Tab` navigate panels

## Tests

```bash
# Full suite (133 tests)
python -m pytest tests/ -v
```

## Project Structure

```
bigbrain/
├── bus/              # Message bus + logging
│   ├── bus.py        # Async pub/sub with wildcard routing
│   ├── message.py    # BusMessage (Pydantic) + Priority enum
│   └── logger.py     # JSONL disk logger
├── front/            # Layer 1 — User-facing intelligence
│   ├── front_brain.py    # Conversation, intent, task routing
│   └── focus_manager.py  # Attention filtering + workspace focus
├── orchestrator/     # Layer 2 — Task management
│   └── orchestrator.py   # Decomposition, dependencies, dispatch
├── brains/           # Layer 3 — Execution workers
│   ├── base.py       # BaseBrain ABC (lifecycle, bus integration)
│   ├── python_brain.py   # Code execution (subprocess)
│   └── researcher.py     # Research + summarization
├── memory/           # 3-tier memory system
│   ├── working_memory.py     # Ephemeral per-brain context
│   ├── project_memory.py     # Workspace-scoped ChromaDB
│   ├── long_term_memory.py   # Cross-workspace knowledge
│   └── memory_manager.py     # Unified interface
├── verification/     # 5-layer verification pipeline
│   ├── v1_schema.py      # Pydantic output validation
│   ├── v4_deterministic.py   # Syntax, tests, types
│   └── pipeline.py       # Pipeline orchestration
├── llm/              # LLM provider abstraction
│   ├── provider.py   # ABC for LLM providers
│   └── mock_provider.py  # Mock with realistic responses
├── voice/            # Voice pipeline
│   ├── stt.py        # Speech-to-text (Deepgram Nova-3)
│   ├── tts.py        # Text-to-speech (Cartesia Sonic)
│   └── voice_manager.py  # Pipeline coordinator
├── tui/              # Textual TUI
│   ├── app.py        # Main 4-panel application
│   ├── app.css       # Dark theme styling
│   └── widgets/      # Chat, brains, tasks, bus, focus panels
├── ui/               # Rich fallback UI
│   ├── ui_adapter.py     # ABC for UI adapters
│   └── rich_adapter.py   # Rich console implementation
└── __main__.py       # Entry point + system coordinator
```

## License

Reference implementation for educational and demonstration purposes.

## Links

- **Real project**: [github.com/yassinebkr/bigbrain](https://github.com/yassinebkr/bigbrain) (private)
- **Architecture spec**: See `memory/bigbrain-architecture.md` in the workspace
- **Research**: MASS (Google ICLR 2026), Spotify Honk, LangChain planning agents, Andrew Ng patterns
