# Demo incident — memory completion and ChatGPT connection

Research phases 3/4 paused at the user's request. The urgent fixes below are in
the current working branch; they are not a new merge or a completed live recall
campaign. No paid model requests were made to diagnose or test this incident.

## Observed causes

The actual journal (`logs/bus-2026-10-24.jsonl`) shows the demo conversation at
02:17 Paris time ending with "Laisse-moi vérifier dans ta mémoire." and a
`chat.done` event, with no `memory.consulted` operation. The next user turn at
02:18 produced `chat.message` with an empty text. The transcript callback ignored
the empty text before finalizing its waiting indicator. This was an unexecuted
lookup followed by a missing terminal UI transition, not evidence of lost data
or a slow Chroma query.

The live server's read-only `/api/auth/codex/status` returned "codex CLI not found
on PATH". Separately, the settings UI discarded `authUrl` and relied on the
server opening a browser, with an unbounded polling timer. Both the executable
configuration and browser-owned sign-in UX needed attention.

## Changes

- Front memory reads/writes can use the real optional `bigbrain_memory` native
  function tool on OpenAI-compatible providers. Fragmented SSE tool calls are
  assembled privately, validated as exactly one named call and executed through
  the same scoped `execute_memory` contract. The actual tool result is returned
  with its matching tool-call ID before the model continues. No keyword-based
  intent matching was introduced. Other providers retain the existing bounded
  JSON memory protocol.
- Private reasoning continuation fields are forwarded to their originating
  provider alongside the assistant tool-call message, never shown or logged as
  conversation/memory output. Memory operations retain the three-operation cap;
  each lookup has a ten-second timeout reporting an error rather than absence.
- Empty model replies now produce an explicit user-facing failure. The browser
  also finishes waiting on terminal `chat.message`, including legacy empty ones.
- ChatGPT login opens the returned HTTPS URL in the user's browser. A visible
  link survives popup blocking. Polling is sequential, bounded and cancelled
  when settings close; errors appear in the status. Codex startup/account RPCs
  have time bounds, and provider discovery honors `BIGBRAIN_CODEX_BINARY`.
- Local `.env` now has a blank `BRAVE_API_KEY` field and the explicit path to an
  already installed Codex executable. No API key was added or exposed. The
  example configuration documents both variables. A restart is required for
  the running Python process to load these changes. Missing Brave is honestly
  announced as unavailable rather than mock search.

## Evidence and remaining validation

An actual local Codex app-server was initialized using the configured binary;
`account/read` confirmed an authenticated ChatGPT account. The probe did not
start a login, read token contents, change credentials or call a model, and its
child process was stopped afterwards. This establishes executable/account access
for the new configuration, not hot-reload of the already running server.

The regression replay uses frozen HTTP SSE responses but real shared-memory
storage with an explicitly sourced synthetic user fact. It proves that a
visible preamble followed by a native tool call performs the lookup and ends
with the retrieved value, without a premature `chat.done` or leaked tool JSON.
It does not prove that a particular live model always chooses the right tool.
The user's original cat-name question should be retried after restart; no name
has been fabricated, seeded or overwritten in their real memory as a shortcut.

UI tests cover a blocked popup, missing CLI, invalid login URL, timeout, account
type and cancellation, plus terminal empty-message handling. All keys and real
memory contents remain outside the test fixtures and commits.

CI checkout history (`fetch-depth: 0`) is also prepared for the next merge,
addressing the previously observed missing frozen baseline commit.

Final targeted regression results: 83 Python tests passed; 120 UI tests passed
across 13 files; the production UI build succeeded. `git diff --check` was clean.
These are offline regression checks, not a live-model memory recall validation.
Research phases 3/4 remain work in progress and paused for this incident.
