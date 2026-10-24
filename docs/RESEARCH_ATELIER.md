# Research acquisition and context — Atelier integration (phase 5)

## Merge approval and next branch, 24 October

The user approved merging `feat/research-evidence` before implementation of the
front decision protocol. Current UI verification: 128 tests and production build
pass. Full Python regression: 1,489 passed, 8 skipped (Python 3.12), with receipt
`../tests/research-premerge-2026-10-24.xml`. The bounded independent inspection and follow-up objective fixes are
documented in `RESEARCH_CONTEXT.md`; live end-to-end acceptance remains manual.

The latest incident was inspected in the durable bus: the front model emitted
an acknowledgement plus copied historical failure text, with no new task-routing
or researcher invocation. This is a front decision/dispatch problem. Its version
1 belongs on the new `feat/front-decision-v1` branch: mandatory typed decisions,
non-streaming replies, bounded memory consultation and checked dispatch. Version
2 (streamed structured fields) is deferred to the user's evaluation of version 1.
User memory changes and the pre-existing untracked dependency lock are excluded
from this merge.

## Authorized Codex-subscription probe, 24 October

One fresh isolated probe used GPT-6.1 Sol low through Codex, with the same public
Python question, 120-second limit, 2 searches, 2 page reads, 1 review and 60,000
conservative allowance units. No automatic retry was performed. Authentication,
structured planning, search and one HTTP read succeeded; no JSON-format error
occurred. The run remained **partial**, with no claims or independent review:
the next decision request and its output reserve could not fit the remaining
allowance.

Reported usage: 3 model calls; 40,154 total tokens = 39,635 input + 519 output;
24,192 input tokens were reported cached (a subset of input, not additional).
Cost was unknown. The final decision view was 39,567 UTF-8 bytes, including
37,027 bytes of serialized passages for only 3,591 bytes of passage text.
The literal `Path.unlink` focus returned 116 blocks and matched the mapping
table (`os.remove()/os.unlink()` → `Path.unlink()`), not the actual method's
`missing_ok`/`FileNotFoundError` explanation. Consequently this run proves neither
the required behavior nor the Python 3.7 comparison.

Two concrete gaps are exposed rather than hypothetical provider problems:
literal focus uses the first matching text window without disambiguating a
navigation/reference occurrence from the target explanation; numerous tiny
blocks repeat source/context/hash metadata, inflating decision context. The
runtime then stops conservatively before its next call, with no reserved final
review/conclusion path. These findings belong to the remaining research-context
and stopping work; success must not be inferred from authentication or parsing.
Durable local raw evidence: `research-retry-fix/codex-probe-2026-10-24/` in the
working folder. No project, private conversation history or user memory was
transmitted; no repository source code was changed to make this probe pass.

## Second manual retry: transport and selection lifecycle

The durable journal for run `1ff640ff-ba71-4317-90b3-b1aaf1b93a4f` establishes
that planning and one search succeeded before the next action failed JSON
decoding. The earlier run `4810afd1-a912-40db-b995-56fff8764049` failed before
planning on fenced JSON. These are distinct failures. The second record kept
only `json_invalid`, so the exact malformed syntax cannot be reconstructed from
that checkpoint. New diagnostics retain the parser message and immutable invalid
response artifact without placing its body in chat.

Research actions/reviews now request the existing native single-tool provider
protocol instead of relying exclusively on a prose instruction to return JSON.
OpenAI-compatible adapters force one named function and require endpoint parameter
support on OpenRouter; Codex maps the schema to its output-schema transport.
Schema arguments remain runtime-validated. Native schema bytes count toward the
conservative allowance. No syntax repair, weaker evidence policy or automatic
paid retry was added.

The front stream previously classified output from its first text prefix only:
a natural-language preamble enabled streaming of a later route object. It now
holds a potentially structured suffix, parses completed JSON with the JSON
decoder (including braces inside strings), emits one conversational completion
and dispatches the unchanged model route once. Ordinary prose/code is released
when it is not a routing/memory request. This is framing, not keyword intent
routing.

The Atelier follower previously required a project path and could therefore
never follow a new projectless research after its selected failed predecessor.
It now follows newer non-taskboard work after a closed projectless run, respecting
conversation identity, explicit inspection time, concurrent active work and the
closed/focus presentation preference.

The user authorized one isolated live probe (120 seconds, 2 searches, 2 page
reads, 1 review, 60,000 conservative allowance units) using GPT-6.1 Sol and Brave.
That single probe stopped on its first OpenRouter request with HTTP 401, before
planning or reading pages. A subsequent free auth-key health check returned
`auth_failed`. The process had a key; environment, project `.env` and the durable
project key store matched, compared without exposing values. No key was changed,
no other key location was searched and no second paid probe was attempted.
Reported token usage was zero but provider usage/cost was unavailable: this is
not a claim of known zero billing. Evidence is retained locally under
`/tmp/bigbrain-research-native-live-jt03_8d9/`. Native-protocol live acceptance
remains blocked by authentication, not demonstrated by offline tests.

Final offline regression after the streaming whitespace/privacy correction:
1,480 passed, 8 optional benchmarks skipped, 9 warnings (172.32 seconds).
Focused research/routing/memory controls: 121 passed; UI: 128 passed and build
succeeded. Nine Chromium component checks passed, including automatic selection
of the next projectless research without manual tab/run selection. Reports:
`bigbrain-research-retry-final-regression.xml`,
`bigbrain-research-retry-focused.xml` and `research-phase5-browser/acceptance.json`
in the local working folder. This supersedes the intermediate regression that
caught one leading-whitespace emission in a private memory-tool turn.

## Pre-merge manual-test correction, 24 October

The user's real Python documentation query exposed a provider-format case not
covered by the initial acceptance run: valid action JSON inside a Markdown
`json` fence was passed directly to strict JSON validation, stopping before any
search. An offline reproduction confirmed the same failure. Action and review
responses now share one boundary that accepts either complete JSON or a single
complete JSON/unlabeled code fence. It does not extract a convenient object from
prose, repair syntax, retry a provider or relax the action/evidence schema.
Malformed JSON, extra objects and unsupported actions still stop before tools.
Format/schema errors retain compact typed diagnostics in the run checkpoint;
the user-facing reason omits raw provider input and Pydantic implementation URLs.

The same manual test exposed a presentation failure: the entire objective was
rendered as a large heading, internal budget counters dominated the panel and
the overview duplicated the detailed research tab. The default Atelier now
shows a compact status, current observed action, read-source/conclusion counts,
recent sources and a short outcome. The original request and usage/diagnostics
are closed disclosures. The research tab holds the question breakdown, complete
source/evidence inspection and action journal. A failed query before its first
read has no fabricated sources or conclusions. Historical technical errors stay
available under the diagnostic disclosure rather than in the primary display.

Correction validation: 1,476 Python tests passed, 8 optional benchmarks skipped,
9 warnings (168.46 seconds); 127 UI tests passed and the production build passed.
Nine added provider-boundary cases cover plain/fenced JSON, malformed responses,
strict schema refusal, no tool execution on invalid output and the shared review
parser. Eight Chromium component checks passed with zero page errors, including
the long-request/legacy-error presentation fixture and separate overview/evidence
tabs. The full report is retained locally as
`bigbrain-research-atelier-fix-regression.xml`; screenshots and browser receipt
remain in `research-phase5-browser/`. No paid rerun or real-web conclusion was
validated by these offline checks. The earlier seven-check receipt below is the
pre-correction baseline, not acceptance of the user's failed live research.

Implemented on `feat/research-evidence`, 24 October 2026. This phase connects the
acquisition/context sub-plan to the existing Atelier and durable bus history.
It preserves the retrieval algorithm documented in `RESEARCH_CONTEXT.md`.

## Observed activity and source inspection

Research snapshots include the actual runtime activity: HTTP loading, cached
observation reuse, browser resource loading, extraction, question-based section
selection and independent review. Terminal snapshots clear live activity. The
Atelier shows these states in its research surface; a project with a research
subtask also gets a compact overview widget linking to that surface. No progress
percentage or invented task completion is inferred from elapsed time.

Source details distinguish HTTP and rendered observations, capture time and
consultation time, cache reuse, acquisition failures and restrictions. Selection
details show selected/index characters, section counts, partial original sections,
omitted headings and catalog truncation. `needs_context` means refinement is
needed, not that the site denied access. These are inspection controls; the UI
does not introduce a second policy that automatically selects or opens sources.

Passages retain headings, clipping, observation identity and whether they entered
through independent review. Long lists display 20 passages at a time with an
explicit reveal control. The UI no longer rejects an entire terminal snapshot
because it contains more than 60 passages. Byte/page limits remain runtime-owned.
Untrusted page text is rendered as text; artifact bodies are excluded from the
frontend projection. URLs use the existing HTTP(S)/credential checks.

## Replay and lifecycle

Live review supplements enter the store on `research_review_evidence`, rather
than waiting for the terminal checkpoint. The journal projection preserves each
review round by its action index, as it already does for page observations.
Terminal checkpoints include compact action history, including the error action
when a timeout stops execution before its normal observation event.

Research ID, subtask ID, run ID and conversation ID scope all updates. Revision
checks make replay idempotent; terminal tasks do not become live again. A
background conversation updates its own record without becoming the visible
conversation's active run, even if the visible conversation has no work.
Changing conversations and reopening an Atelier surface do not dispatch work.
After server restart, unfinished runs are marked interrupted; restoring their
snapshot restores evidence, not execution. Stop retains collected evidence and
suppresses live animation after termination.

## Retrieval boundaries retained for the next branch

The input to selection is the current question plus its required evidence, not
necessarily the complete original user message. Selection ranks section words
locally with a BM25-style formula. It uses frequency saturation, word rarity
within the page and section-length normalization. It has no embeddings, synonym
expansion, semantic reranker or stopword filtering. The tokenizer handles Unicode
words and limited camel-case splitting; it is not a multilingual semantic model.

Content up to 2,200 candidate characters stays intact; larger content uses two
positive-scoring anchor sections and immediate neighbors within 6,000 characters.
Those thresholds are initial heuristics. Main-text extraction may already omit
original blocks: whole selected candidate blocks do not imply complete original
sections. Omission/partial metadata exposes that distinction. Explicit section
reads retrieve original blocks using observation-bound IDs; literal focus is the
fallback outside the first 24 inline catalog entries. Catalog pagination remains
absent.

Lexical overlap is relevance retrieval, not truth or source credibility. Synonyms,
cross-language wording and distant qualifications can be missed. Independent
review receives retained original indexes so it does not share the decision
ranker's blind spots, but model interpretation is still fallible. An oversized
review remains incomplete; no hierarchical review has been added. Savings in the
decision context do not establish lower total research cost, since full review
can still be expensive. The phase-4 30.8% reduction measures evidence JSON bytes,
excluding fixed prompt/schema overhead, not provider-billed tokens.

## Validation and branch boundary

Validation observed on 24 October:

- Complete Python suite: 1,467 passed, 8 optional extractor benchmarks skipped,
  9 warnings, 169.80 seconds. Local report:
  `../tests/bigbrain-research-phase5-regression.xml` in the working directory.
- UI: 125 tests passed across 13 files; production type-check/build succeeded.
  Existing bundle-size/dynamic-import and dependency annotation warnings remain.
- Actual Chromium acceptance: seven checks passed with zero page errors. It
  exercised production Atelier components/styles with 33 real worker/bus frames
  and 13 journal-projected frames, on isolated synthetic HTTP/script responses.
  The real PageReader and Chromium rendered the script and performed cached
  observation-bound refinement; the fake transport made two in-memory responses,
  with no external search or model call.
- Browser checks covered the visible phase, foreign-session isolation, Stop,
  late terminal evidence, reload/history restoration, replay idempotence and
  closing/reopening the surface. The local harness, raw frames, receipts and
  screenshots are retained in `../tests/research-phase5-browser/` alongside the
  project checkout, not loaded into production UI or user data.

Three older store assertions/fixtures were aligned with the scoped-run invariant:
a foreign proposal is retained without becoming active in the visible session;
maintenance/routing tests now explicitly identify the conversation being viewed.
The new regression independently reproduces and checks the empty-session leak.
No contract, source-credibility or claim-acceptance gate was relaxed.

CI installs the research extra so these new production-reader controls run with
their actual extractor dependencies. This is a prepared workflow change, not a
claim that a new GitHub run or the Python 3.13 CI matrix has been observed green.

The offline gates cover real PageReader selection/refinement/cache through the
worker and durable bus, pending acquisition across restart, retained review rounds,
and cancellation. UI controls cover the observed phase, access/selection metadata,
long passage lists, review supplements, replay and conversation isolation.

Complete current-branch validation precedes a merge proposal. Merge requires the
user's final approval; the next research-improvement branch starts from merged
main, not a parallel fork omitting this work. That branch should improve retrieval
and bounded independent review with measured ablations, then perform the authorized
real-web comparison (phase 6). A cheap model such as Luna is a candidate to compare,
not an enabled dependency or a demonstrated quality gain. No paid campaign is
authorized merely by configuring Brave credentials.
