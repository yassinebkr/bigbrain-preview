# BigBrain

A multi-brain AI agent system: a user-facing conversational brain delegates
work over an authenticated message bus to an orchestrator, which dispatches
subtasks to worker brains (code execution, research, task board). Every code
execution goes through a deterministic verification gate whose evidence is
recorded, immutable, and replayable. A React web UI is the primary interface.

This is an active development repository. Details live in `docs/`:
[AUTH.md](docs/AUTH.md), [MODELS.md](docs/MODELS.md),
[HARNESS-DETERMINISTE.md](docs/HARNESS-DETERMINISTE.md).

## Quick start

```bash
git clone https://github.com/yassinebkr/bigbrain-preview.git
cd bigbrain-preview

# Backend
pip install -e ".[test,web]"

# Web UI (built once, served by the backend at /)
cd web-ui && npm install && npm run build && cd ..

# Run
python -m bigbrain --web --web-port 3007
```

Open http://localhost:3007. There is no default LLM: open the Providers
panel and either paste an OpenRouter key, click "Connect with Mistral"
(browser PKCE), or connect a ChatGPT subscription (Codex). The model
lineup (per role: front, planner, code, subagent) is selected in the UI
and persisted server-side.

Set `BIGBRAIN_WEB_PASSWORD` to enable HTTP Basic Auth.

### Other modes

```bash
python -m bigbrain            # Textual TUI
python -m bigbrain --simple   # Rich console fallback
```

Run BigBrain in a standalone terminal, not VS Code's integrated one —
the TUI needs keyboard shortcuts the integrated terminal captures.

## Environment (`.env`)

```bash
# Providers — at least one, or connect one from the Providers panel
OPENROUTER_API_KEY=sk-or-v1-...   # unlocks gpt-sol, kimi-k3, opus-5.5,
                                  # kimi-k2.7-code, gpt-luna via OpenRouter
MISTRAL_API_KEY=...               # medium 3.5 + GLM 5.3 (set automatically
                                  # by the Connect-with-Mistral button)
KIMI_API_KEY=...                  # Kimi K3 direct coding endpoint
BIGBRAIN_PROVIDER=<registry key>  # force the provider used by default

# Optional per-role overrides (otherwise the Providers panel lineup wins)
BIGBRAIN_FRONT_MODEL=...
BIGBRAIN_PLANNER_MODEL=...
BIGBRAIN_CODE_MODEL=...
BIGBRAIN_SUBAGENT_MODEL=...

# System
BIGBRAIN_LOG_DIR=logs
BIGBRAIN_MAX_TOKENS=2048
BIGBRAIN_CODE_TIMEOUT=30
BIGBRAIN_TEMPERATURE=0.7
BIGBRAIN_WEB_PASSWORD=...         # enables Basic Auth

# Gates and storage
BIGBRAIN_EVIDENCE=1               # 0 disables the verification gate
BIGBRAIN_CONTRACTS=1              # 0 disables pre-implementation approval
BIGBRAIN_EVIDENCE_ROOT=data/evidence
BIGBRAIN_SESSIONS_DIR=data/sessions

# Voice (optional extra: pip install -e ".[voice]")
DEEPGRAM_API_KEY=...
CARTESIA_API_KEY=...
CARTESIA_VOICE_ID=...
```

Note: Anthropic models are reachable through OpenRouter (the
`openrouter-opus-5.5` entry). The old "Claude OAuth / --login" flow is
obsolete: Anthropic no longer permits its subscription models outside
its API, and the flow is not maintained. Do not use it.

## Architecture

Three layers over an asynchronous, HMAC-authenticated message bus:

```
user ──▶ Front Brain ──task──▶ Orchestrator ──subtask──▶ Worker brains
              │                     │                        │
              └──────── results / events over the bus ───────┘
```

- **Front brain** — the conversational layer. Answers directly, or
  delegates. It picks the target itself (LLM tool-call routing): a
  board task goes to the taskboard brain, a file run to PythonBrain;
  anything else goes to the orchestrator as one compound request.
- **Orchestrator** — decomposes requests into a DAG of subtasks with
  dependencies, balances brain load, honors explicit routes verbatim,
  and pauses codegen plans until contracts are approved.
- **Worker brains** — PythonBrain (pool of 3 subprocess workers with
  the Honk retry loop), ResearcherBrain (parallel search + synthesis),
  TaskBoardBrain (persistent user board).

A focus system filters which bus events reach the user by attention
mode (deep focus / normal / overview).

## Memory

Memory was a core part of the original vision (the scratchy / openclaw
lesson: a system that remembers you is qualitatively different — but
openclaw's approach burned tokens re-injecting everything, every turn).

BigBrain's memory is deliberately frugal:

- **Working memory** — ephemeral, per-brain, capped (size and age).
- **Persistent memory** — a single ChromaDB collection
  (`~/.bigbrain/memory/`) with a `scope` field: `workspace` entries die
  with their project, `global` entries survive everything. Conversation
  turns, user preferences (name, focus mode) and learned context are
  written there; the `memory/` JSON files in the repo are its runtime
  state. Without ChromaDB installed it degrades to an in-process store.
- **Token budget by design** — the LLM prompt gets the last 20 turns of
  the current session and the loaded preferences, nothing more. Memory
  writes cost no LLM tokens; nothing is re-summarized on each turn.

What is deliberately *not* there yet: per-turn semantic recall (memories
are stored, but nothing retrieves the relevant ones into the prompt
today), image memory, and a consolidation/"soul" process. Wiring
top-k retrieval into the prompt is the intended next step — with the
same frugality rule: a handful of retrieved lines, not a replayed life.

## Verification harness

Every Python execution attempt is evaluated against what was asked:

```
DesignSpec (request + contracts)
        │
        ▼
RunManifest (one per attempt, immutable, chained to the previous)
  stages:  syntax → compile → run → tests → contracts
  verdict: passed | failed | inconclusive    (inconclusive is never a pass)
  artifacts: sha256 content-addressed (code, stdout, stderr, test output)
```

A `failed` verdict feeds the stage details back into the Honk retry
loop; an `inconclusive` one is labelled "not fully verified" instead of
claimed. Recorded runs can be replayed in a clean subprocess to diff
outputs, and a golden corpus (hello, fibonacci, file_io, unicode)
regression-tests the execution machinery itself without any LLM.

### Contract approval

Before the agent writes code, it proposes checkable contracts in the
chat. The plan stays paused until you approve or reject them; your
verdict is stamped onto the spec as a new immutable revision, and every
run manifest links to the approved spec. The Evidence tab shows the
contracts, the verdict chip, and who approved.

## Web UI

Chat with token streaming, a run panel (live steps, written files,
gate verdict), a persistent multi-conversation history, a workspace
file explorer with per-project sub-workspaces, a real task board
(persisted in `data/tasks.json`), brains and evidence tabs. No mock
data anywhere: if the board is empty, it is empty.

## Tests

```bash
python -m pytest tests/ -q          # backend, 860+
cd web-ui && npm run test          # store state machine (vitest)
cd web-ui && npm run build         # type-check + production build
```

Three environment-fragile tests fail locally by default (architect
event-loop on 3.13, dispatch timing, voice/numpy absent) — CI runs the
suite on Python 3.12/3.13 with the two fragile ones deselected, plus a
frontend job (npm ci, vitest, build).

## Project layout

```
bigbrain/
  bus/             async pub/sub bus, HMAC auth, JSONL logging
  front/           front brain (delegation, focus manager)
  orchestrator/    DAG planning, dispatch, contract gate
  brains/          python (pool), researcher, taskboard
  verification/    evidence, stages, gate, replay, contracts
  llm/             providers, model registry, usage accounting
  auth/            provider auth facade (Mistral PKCE, OpenRouter, Codex)
  web/             aiohttp server + WS bridge, FS/projects/sessions APIs
  memory/          3-tier memory (working, project, long-term)
  voice/           optional STT/TTS (Deepgram, Cartesia)
  tui/, ui/        Textual app, Rich fallback
web-ui/            React 18 + TypeScript + Vite + Zustand product
docs/              AUTH.md, MODELS.md, HARNESS-DETERMINISTE.md
```

## License

Dual license: AGPL-3.0 (core) + commercial (contact for production use
without open-source obligations).
