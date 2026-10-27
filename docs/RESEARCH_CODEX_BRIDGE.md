# Research inference integration

## Integration choices

### Structured inference through an API

An inference API can expose BigBrain's function contracts directly and enforce
the provider's supported tool selection settings. OpenRouter evaluation is
deferred until credits are available and the Codex path requires reassessment.
Provider changes require explicit selection; automatic fallback stays disabled.

### Codex client-owned decision bridge

This is the selected implementation. The app-server exposes the dynamic function
`bigbrain_submit_decision` with one `decision_json` string argument. Code-mode
orchestration can discover and invoke this function. The client receives the
proposal through `item/tool/call`, acknowledges receipt and interrupts the native
turn. BigBrain then parses the original research contract, checks phase/resource
constraints and executes the admitted operation. The next native turn receives
the resulting runtime observation through the existing policy view.

## Boundaries

- Collection and independent review use the same submission transport.
- The bridge accepts one JSON object, at most 65,536 UTF-8 bytes, for the active
  native thread and turn. Its acknowledgement records receipt for validation.
- Existing Action validation, source identities, quote anchoring, passage
  provenance, acquisition permissions and delivery checks remain authoritative.
- Runtime deadlines and Stop cancel the native turn. The guard interrupts when
  observed orchestration calls exceed three. Native calls remain distinct from
  logical BigBrain decisions and contribute to provider-reported usage.
- Native shell, browser, image generation, apps, plugins and agents remain
  disabled. MCP servers returned by effective config inspection are disabled in
  the research thread configuration. Unknown client requests receive an error.
- Code-mode host availability is enabled for the child process; per-thread
  configuration enables it for the bridge and disables it for the existing
  frontbrain inference path. Native code-mode execution remains version-sensitive
  and its configured permissions require continued regression coverage.
- The bridge produces proposals. Search and page acquisition execute through
  ResearchRuntime after the native turn has been interrupted.

## Conversation bindings

The research role gains the versioned suffix `-actions-v1`. The first call creates
one binding for the new tool contract. Subsequent calls reuse that native thread;
resume restores the persisted dynamic tool definition. Earlier inference-only
threads remain preserved. Frontbrain bindings keep their existing identities.

## Protocol and compatibility

The official app-server documentation describes experimental `dynamicTools` on
thread creation and the `item/tool/call` request/response lifecycle:
https://learn.chatgpt.com/docs/app-server

The installed schema defines `arguments`, `threadId`, `turnId`, `tool`, `callId`
and optional `namespace`; responses contain `success` and `contentItems`.
The reader dispatches server requests separately from notifications and ordinary
RPC responses. A late answer cannot authorize a rejected proposal.

## Verification

The focused provider, runtime, documentary, worker-journey and trace campaign
passes 147 tests. The suite includes invalid JSON, unexpected tools, wrong turns,
native-call overflow, missing submissions and dynamic proposal submission.

The final backend suite passes 1,643 tests with eight optional skips and nine
warnings (189.63 seconds). It includes additional regressions for thread reuse,
requests arriving before the turn-start response and stale completion events.
The final log is `/tmp/bigbrain-action-bridge-final-full.log`.

An isolated live Luna low probe submitted two decisions through the bridge in
one conversation in 3.32 seconds. Reported usage: 4,220 input tokens, 50 output
tokens, 4,270 total; monetary cost unavailable. Evidence:
`/tmp/bigbrain-boundary-probe-607762nf/result.json`.

This probe validates the native tool transport with a minimal decision schema.
A second isolated probe confirms the final submission/interruption sequencing:
two submissions in one conversation, 11.29 seconds. Native usage notifications
were absent; token consumption is unknown. The runtime retains an unknown-usage
count and conservative admission charges for that situation. Evidence:
`/tmp/bigbrain-boundary-probe-q12d0x1h/result.json`.

Full documentary coverage, independent review quality and representative
production efficiency remain separate acceptance gates. Raw-event visibility
after native thread resume remains version-sensitive; the orchestration-call
guard acts on observed events while the runtime deadline remains authoritative.
