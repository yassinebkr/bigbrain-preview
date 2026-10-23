# Codex conversation integration

Scope: fix subscription transport first; do not redesign orchestration here.

- Stable front thread per visible conversation and authenticated account.
- Separate worker identities; independent acceptance reviews each own their
  bounded review conversation. Never put worker history into the front thread.
- Persist thread identifiers and input hashes under the isolated session root;
  resume after server restart. No silent new thread on a failed resume.
- Append only new visible messages; send updated runtime instructions explicitly.
  Callers' changing diagnostic snapshots remain unchanged in this phase.
- Serialize a thread's turns; allow different conversations concurrently.
  Stop interrupts the owned turn, never another conversation.
- Native manual compaction and native automatic context compaction; preserve
  input cursors across compaction. No presentation of plan-result truncation as
  conversation compaction. Initial native threshold: 128000 context tokens,
  configurable via BIGBRAIN_CODEX_AUTO_COMPACT_TOKENS (not a generation cap).
- Record per-turn usage deltas, cached input and raw cumulative checkpoints;
  never sum the thread lifetime counter once per turn. Unknown costs stay unknown.

Validation: isolated deterministic tests for reuse, isolation, restart, delta
history, concurrent turns, cancellation, usage and compaction. Then a bounded
low-reasoning synthetic multi-turn subscription probe; no full repair campaign.
## Delivered boundaries

Runtime scope is attached at the front response loop, planner and worker
execution boundaries. Reviews and soul consolidation get independent scopes;
review steps reuse their own thread, not the implementation worker's history.
Requests without a conversation ID remain ephemeral: no implicit global chat.
The direct low-level caller may supply conversation_id/conversation_role.

Bindings live under BIGBRAIN_SESSIONS_DIR/codex, keyed by hashes of the visible
conversation, role and authenticated account. They contain thread IDs, message
hashes, usage checkpoints and compaction counters, not source dumps or tokens.
The native Codex thread itself persists history in Codex-owned storage. Deleting
a BigBrain chat blocks further use but does not purge Codex-native history,
matching existing retention of technical journals. No cross-process lock is
claimed: turn serialization is within one running BigBrain event loop.

Manual backend entry point: await provider.compact_conversation(session_id).
No new chat button was added. Native auto-compaction is configured at 128000
context tokens and contextCompaction lifecycle events are accepted/recorded.
The old orchestrator compaction is merely character-based result reduction;
it is neither this native compaction nor long-term shared memory.

## Live evidence (2026-10-23)

Four short GPT-6.1 Sol low subscription responses plus one explicit compaction:
`/tmp/bigbrain-codex-conversations-o8jcn5t0`. Duration 18.29 s. The marker was
recalled, survived compaction + app-server restart/resume, and the other chat
answered UNKNOWN. Account and project sources were never supplied to the probe.

The first probe logger selected the first in-memory binding when printing the
second chat's thread ID. That displayed ID was wrong; direct inspection of both
durable binding files confirms distinct native IDs:

- chat A: 01a16911-ff21-7d53-8772-b7f5c652e59a (same before/after resume)
- chat B: 01a16912-34ef-70a3-9d97-186eb0fab695

Probe logging now selects the binding by exact conversation identity and asserts
different IDs. No paid rerun was made just to correct a display-only logger bug.

Reported completions: 32019 input, 37 output (9 reasoning), 3840 cached input;
32056 total. Explicit compaction emitted an unchanged usage counter, so its own
usage is UNKNOWN, not zero. The initial result counted that zero-delta event as
a fifth usage record; the adapter now excludes it and flags unknown compaction
usage. Raw result remains unchanged. This is not a same-case comparison with the
22-step repair campaign and does not prove a token reduction. Native base
context remains about 7.8k input per short request in this sample.

Native automatic compaction lifecycle is covered deterministically; the live
probe did not force a 128k context or a large automatic compaction. Its threshold
is configured, not a claimed stress-test result.

Offline tests cover reuse, role/chat separation, concurrency, exact-ID resume,
failed resume without reset, incremental/rolling history, Stop, deleted chat,
cumulative usage deltas and native manual/automatic compaction. Final regression:
**1217 passed / 9 existing warnings (151.49 s)**, including 33 targeted
provider/conversation/usage tests. No UI files changed. No merge before user
validation.

## Next discussion: orchestration, not implemented here

The native thread fix does not make 22 LLM calls proportionate to a one-line
repair. Discuss the unit of work (a bounded edit/verification batch rather than
one read at a time), deterministic preflight/verification outside the LLM, and
review context sized to the actual project/diff. Keep native LLM intent routing,
immutable approval, independent acceptance, scoped writes and rollback. Do not
silently weaken gates to make a benchmark cheaper.

Reference: https://learn.chatgpt.com/docs/app-server

## Independent review evidence delivery (23 October)

Codex declares `review_event_context=True`. The progressive reviewer builds an
append-only transcript: pinned criteria/inventory/provenance once, then only
new runtime observations and action/decision instructions. Assistant replies
remain in the transcript so the native provider's existing suffix cursor can
match them. Stable system instructions are not rewritten on decision phase.
Stateless providers retain the bounded rolling snapshot protocol.

A separate current snapshot is supplied as `context_checkpoint`; the provider
injects it only after compaction, not each normal turn. Acceptance conditions,
source page limits, hashes, evidence coverage and independent scope are unchanged.
This avoids redundant prompt transmission; native inference still counts the
retained conversation as input, so it does not promise constant token usage.
Offline generic tests check exact unseen suffixes and each source page delivered
once, plus unchanged stateless snapshots. No new paid validation yet.
