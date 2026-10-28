# Direct research: frozen five-probe assessment

## Decision and scope

The two corrections and their bounded evaluation close this experimental
iteration. Production worker selection and complete chat/Atelier acceptance
remain a separate cutover gate. The default researcher uses the previous workflow.

Packets now expose acquisition failures and capture-bound section navigation,
with bounded local paging. Native action shapes bind section IDs to their source
and capture. Conclusions require one assessment per read source, allowing unknown
or limited judgments. Provider-decoded candidates are retained before validation.

Offline research suite: **483 passed, eight skipped**, 20.33 seconds. Seven new
regressions cover the recorded SQLite failure and source-assessment cardinality.
The frozen manifest is [RESEARCH_DIRECT_FIVE_PROBES.json](RESEARCH_DIRECT_FIVE_PROBES.json).

## Live outcomes

All five used GPT-6.1 Terra medium through the Codex subscription, real native
transport and public-page acquisition. Each ran once, with identical implementation
hashes, one native binding and no intervening source changes.

| Case | Seconds | Calls | Runtime outcome | Manual audit qualification |
| --- | ---: | ---: | --- | --- |
| MDN fetch/abort | 19.612 | 2 | Partial | Requested content covered; secondary-source classification leaves findings unverified under the existing proof policy. |
| SQLite DELETE/WAL | 20.643 | 2 | Partial | Direct evidence for DELETE writer concurrency and network-filesystem conditions remains missing and explicitly reported. |
| Python unlink versions | 17.109 | 3 | Complete | Version/signature and FileNotFoundError scope supported; explicit explanation that other errors remain possible is omitted. |
| Klipper SAVE_CONFIG | 20.545 | 2 | Complete | Calibration, main-config persistence and host restart supported. |
| Git stash | 19.359 | 3 | Complete | Requested behavior supported; ignored-file exclusion with -u is qualified as an inference from the contrast with -a. |

Twelve model calls produced twelve candidate artifacts and zero technical failures.
Every attempt terminated within 21 seconds. The audit checked all 28 claim quotation
anchors against passage offsets and twelve source provenance assessments. Literal
citation validity and semantic completeness remain separate. Independent review
was absent.

MDN retains its partial status; source-role classification needs future calibration
against the proof policy. SQLite reached finish-only admission before further
acquisition. Python retains the manual omission above alongside its runtime status.
There were no reruns or acceptance-policy changes. Group-selector recovery was
covered by the captured SQLite regression offline; these live calls did not exercise it.

## Usage and evidence boundary

One of twelve calls reported native usage: 6,644 input and 227 output tokens,
zero cached input. Eleven used conservative reservations for unknown usage.
Aggregate accounting: 246,516 input units and 12,227 output units, combining
reported and reserved values. Actual total tokens and monetary cost remain unknown.
Git's final admitted call reached 77,607 input units against the monitored 64,000
threshold. No subsequent call followed.

The harness isolates memory, sessions and evidence. It exercises the direct engine
and native transport. HMAC worker delivery, chat state and Atelier rendering remain
outside this campaign. General-web reliability remains an ongoing product limit.

Evidence root: `/home/kwestog/Documents/code/tests/research-efficiency-evidence/`.
Directories: `direct-five-20261027-mdn`, `-sqlite`, `-python`, `-klipper`, `-git`.
Each retains results, frames, source hashes and native traces. The directory
`direct-five-20261027-assessment/` retains the audit, offline suite and process logs.
Audit script: `/home/kwestog/Documents/code/tests/audit_direct_five.py`.
