# Authentication & Connection Flows

Three ways BigBrain obtains model access, all surfaced in the web settings
panel (`⚙ Providers` button) and behind one selection facade
(`bigbrain/auth/registry.py`):

## Codex — "Connect with ChatGPT" (subscription)

Pipeline (Python port of shopifast-local's codexProvider, protocol verified
there against codex-cli 0.153.4):

1. The backend spawns `codex app-server` and speaks JSON-RPC over stdio.
2. Button → `POST /api/auth/codex/login` → `account/login/start
   {type: "chatgpt"}` → the app-server returns an `authUrl`; the server
   opens it in the browser (the "click the ChatGPT button" step happens
   there).
3. codex itself owns the OAuth callback, token exchange, and credential
   storage in `~/.codex`.
4. The UI polls `GET /api/auth/codex/status` (`account/read`) until the
   account appears.

Requirements: codex CLI on PATH with stored credentials. Each visible
request uses one ephemeral thread (the durable conversation stays in
BigBrain, so old tool payloads are never re-charged).

## Mistral — "Connect with Mistral" (browser PKCE wizard)

Faithful port of Mistral Vibe's own `vibe --setup` flow (upstream
`sign_in_flow.rs` / `sign_in_gateway.rs` / `whoami.rs`):

1. Button → `POST /api/auth/mistral/start` → PKCE (S256) handshake against
   `console.mistral.ai/api/vibe/sign-in` → returns a `sign_in_url` (opened
   in the browser).
2. `GET /api/auth/mistral/poll` (3s cadence, upstream default) until the
   console reports `completed` and issues an exchange token.
3. `POST /api/auth/mistral/complete` → exchanges token + code_verifier for
   an API key, verifies it with the FREE `GET /v1/models` probe, stores it
   in `.env` (atomic, 0600) and the durable `data/provider_keys.env`, and
   exports it into the process env — a running system adopts it without a
   restart.

The key never appears in any API response. Server-returned URLs are
validated against the console origin (split-horizon rules from upstream).
CLI equivalent: `python -m bigbrain.auth.mistral_oauth`.

## Anthropic — Claude Pro/Max OAuth

Pre-existing flow (`bigbrain/auth/oauth.py`, `python -m bigbrain --login`):
PKCE against claude.ai, token stored locally, used by
`llm/anthropic_oauth.py` with the Claude Code stealth headers.

## Environment keys (no wizard needed)

| Env var | Unlocks |
|---|---|
| `OPENROUTER_API_KEY` | all `openrouter-*` registry models |
| `MISTRAL_API_KEY` | `mistral-vibe` (also set by the wizard) |
| `KIMI_API_KEY` | `kimi-k3` direct |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | legacy litellm provider |
| `BIGBRAIN_PROVIDER` | force a registry key, e.g. `codex-chatgpt` |

## REST surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/models` | GET | registry models + availability |
| `/api/usage` | GET | token/cost ledger |
| `/api/auth/codex/status` | GET | who is signed in (poll target) |
| `/api/auth/codex/login` | POST | start ChatGPT OAuth (opens browser) |
| `/api/auth/mistral/start` | POST | start PKCE flow (returns sign_in_url) |
| `/api/auth/mistral/poll` | GET | poll in-flight sign-in once |
| `/api/auth/mistral/complete` | POST | exchange + store key |
