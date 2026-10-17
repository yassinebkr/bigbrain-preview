# Models & Providers

BigBrain selects its provider through a registry: `bigbrain/llm/model_registry.py`.
Each entry maps a short key to a display name, provider kind, model id, API-key
env var, base URL, and capability flags (reasoning, vision).

## Registry keys

| Key | Provider | Model id | Auth | Reasoning | Vision |
|---|---|---|---|---|---|
| `openrouter-gpt-sol` | OpenRouter | `openai/gpt-5.6-sol` | `OPENROUTER_API_KEY` | yes (low default) | yes |
| `openrouter-kimi-k3` | OpenRouter | `moonshotai/kimi-k3` | `OPENROUTER_API_KEY` | yes | yes |
| `openrouter-opus-5.5` | OpenRouter | `anthropic/claude-opus-5.5` | `OPENROUTER_API_KEY` | no | yes |
| `openrouter-kimi-k2.7-code` | OpenRouter | `moonshotai/kimi-k2.7-code` | `OPENROUTER_API_KEY` | no | no |
| `openrouter-luna` | OpenRouter | `openai/gpt-5.6-luna` | `OPENROUTER_API_KEY` | no | no |
| `kimi-k3` | Kimi direct | `k3` | `KIMI_API_KEY` | yes | yes |
| `mistral-vibe` | Mistral | `mistral-medium-3-5` | `MISTRAL_API_KEY` | no | no |
| `mistral-glm-5.3` | Mistral hosted | `zai-glm-5-3` | `MISTRAL_API_KEY` | yes (low default) | yes |
| `codex-chatgpt` | codex app-server | `gpt-5.6-luna` | `~/.codex` (ChatGPT login) | via effort | no |
| `anthropic-oauth` | Anthropic OAuth | `claude-sonnet-4-6` | stored token | no | no |

Model ids on OpenRouter evolve quickly: every id is overridable via env
(`<KEY_UPPER>_MODEL`, `<KEY_UPPER>_BASE_URL`, e.g. `OPENROUTER_GPT_SOL_MODEL`).
Verify current ids on openrouter.ai/models before relying on a default.

## Selection order

`bigbrain/auth/registry.py` picks the first available (overridable with
`BIGBRAIN_PROVIDER=<key>`):

1. Claude OAuth token (stored by `python -m bigbrain --login`)
2. `OPENROUTER_API_KEY` → `openrouter-gpt-sol`
3. `MISTRAL_API_KEY` → `mistral-vibe` (set by the browser wizard)
4. `KIMI_API_KEY` → `kimi-k3`
5. codex CLI with stored credentials → `codex-chatgpt`
6. legacy litellm keys (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`)
7. mock provider

## Role models

Roles get distinct models through the existing env vars; when using an
OpenRouter provider, any OpenRouter id works per call:

- `BIGBRAIN_FRONT_MODEL` — Front Brain (default role for chat)
- `BIGBRAIN_CODE_MODEL` — code generation
- `BIGBRAIN_PLANNER_MODEL` — orchestrator planning
- `BIGBRAIN_SUBAGENT_MODEL` — sub-brains / sub-agents (new; Luna-class
  models are intended here: cheap, fast)

Suggested OpenRouter pairing: Sol or Opus 5.5 for front/planner, Kimi K2.7
Code for code, Luna for sub-agents.

## Reasoning models

Reasoning models stream thinking via `reasoning_content` deltas. Thinking
tokens share the completion budget, so the provider adds
`_REASONING_MAX_TOKENS_HEADROOM` (2048) to `max_tokens` for reasoning
entries and sends `reasoning_effort` only when the entry declares supported
values (default `low`). `reasoning_content` is never surfaced as visible
output.

## Health checks

`verify_model(key)` uses only FREE authenticated GETs
(OpenRouter `/auth/key`, Mistral/Kimi `/models`) — never a paid completion
call. Results are cached for 60s. Status words: `ok | auth_failed |
unreachable | unknown | no_key`. The settings panel (`/api/models`)
displays this per model.

## Token accounting

Every provider records a `UsageRecord` (input, cached input, cache-write,
output, reasoning output, total) into the process-wide `UsageTracker`
(`bigbrain/llm/usage.py`). See it live at `GET /api/usage`. Budgets per role
are configured with `BIGBRAIN_BUDGET_FRONT` etc. (tokens/day; 0 disables).
Costs are only reported when a price is configured
(`BIGBRAIN_PRICE_<MODEL>_IN` / `_OUT`, USD per million tokens) — an
unpriced model reports `cost_usd: null` rather than a guess.
