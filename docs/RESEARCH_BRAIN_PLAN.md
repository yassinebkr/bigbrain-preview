# ResearchBrain roadmap and implementation history

## Current checkpoint — 27 October 2026

27 October follow-up: Gate 4 live acceptance remains open. The first waves exposed
integration blockers; consolidated corrections and their exact evidence boundary
are recorded in [RESEARCH_LIVE_BLOCKERS_20261027.md](RESEARCH_LIVE_BLOCKERS_20261027.md).
The final six-case wave has completed. Both MDN cases failed their dossier or
closing budgets. Conflicting-source answers retained the expected limits;
blocked-report cases left the intended 403 acquisition unexercised.

The implementation checkpoint is `feat/front-decision-v1`. Its work includes native
front decisions, Codex research transport, bounded research collection, source
selection, evidence assessment, usage tracing and Atelier delivery. Real journeys
have produced successful and partial outcomes. General research reliability
remains open. This checkpoint preserves the implementation and experiment history.
The next development branch will replace the default multi-role dossier journey
with a direct research loop: scoped acquisition, compact passages, synthesis and
mechanical citation validation. Additional semantic review will be selected by
explicit risk or request. Source acquisition and orchestration remain owned by
BigBrain. The detailed replacement contract will precede implementation.
The current replacement contract is
[RESEARCH_DIRECT_LOOP_PLAN.md](RESEARCH_DIRECT_LOOP_PLAN.md), on
`feat/research-direct-loop` from merged checkpoint `3829317`.

The approved architecture and closure gates are documented in
[RESEARCH_CLOSURE_PLAN.md](RESEARCH_CLOSURE_PLAN.md). Gates 1–3 implementation
and Gate 4 preparation are authorized. It specifies a shared versioned evidence dossier, explicit stages,
separate final control, one targeted complement cycle and a frozen acceptance
campaign. Official API pricing will serve as the reference cost; measured tokens,
unknown usage, conservative reservations and subscription quota remain distinct.

Current evidence and unresolved issues are recorded in
[RESEARCH_GATES_20261026.md](RESEARCH_GATES_20261026.md); the pre-implementation
checkpoint remains in [RESEARCH_CHECKPOINT_20261026.md](RESEARCH_CHECKPOINT_20261026.md).
Earlier test counts and phase reports below describe their own source revisions.
Gates 1–3 are closed offline under the approved monitored Codex subscription
policy. The twelve-case Gate 4 campaign has live follow-up evidence with unresolved
failures. General reliability remains unestablished.

Local user memory, local `AGENTS.md` and the unrelated local lockfile remain
outside this checkpoint. Merge requires explicit user authorization.

## Efficiency follow-up — phases 1–4, 25 October 2026

Implementation and bounded offline evidence: [RESEARCH_EFFICIENCY.md](RESEARCH_EFFICIENCY.md).
Grouped independent collection, compact decision packets, conversation-owned
checkpoints/explicit continuations and question-coverage review are implemented.
The seven-case mechanical comparison uses 24 → 21 scripted decisions and
216,835 → 191,512 serialized prompt/schema bytes; these are not billed tokens.
The compared local reranker adds no measured coverage benefit and is not enabled
by default. Fresh live semantic/browser acceptance is still open. No new scraper
dependency, paid run, push or merge belongs to this step.

## Observability — mandatory follow-up, 25 October 2026

Latest integrated incident: reserve arithmetic closed collection before a read,
then clarification lost its reason and surfaced as `Worker validation failed`.
Budget admission and error propagation are corrected; research envelope is now
explicit/configurable (120k default) with observed-usage reserve floors. Integrated
checks additionally found Codex intermediate/final JSON concatenation and external
runtime/native-tool ambiguity. Native phases are respected and action instructions
are explicit. Rejected literal-quotation reports get bounded correction within
existing review/time/token limits, without relaxing validation.
Full findings and all failures: `../../tests/research-budget-admission/REPORT.md`.
The retained Python-3.13 evidence passes review, but the Python-3.7 comparison is
not established; fresh full-request and actual browser acceptance remain open.

User-authorized follow-up live continuation now passes decision + evidence review
in 15.503 s with two Luna-low Codex calls, 27,984 reported tokens. Three claims are
supported and a synthetic example remains unverified; coverage limits persist.
Live testing exposed generic Codex `$ref` optional-field restoration and an action
schema that still allowed question lists after planning; both are corrected without
loosening local validation. Five calls across four retained follow-up attempts;
no web acquisition and no change to the configured application model. See the
follow-up section of `../../tests/research-call-observability/REPORT.md` for failures,
budgets and remaining fresh-research/UI acceptance limits.

Initial implementation on `feat/front-decision-v1`: correlated per-call inference
JSONL, front/research lifecycle, HTTP and Codex transport milestones, explicit
unknown usage and exception type chains. 185 targeted offline tests pass. A single
authorized Luna-low replay returned in 7.294 s (11,240 input/689 output tokens),
but its self-assigned claim verdicts fail execution preflight. Native proposal
status is now restricted to `unverified`; no second live call. Full findings and
limits: `../../tests/research-call-observability/REPORT.md`. This does not complete
the broader observability acceptance below or validate full research delivery.

User requirement: diagnose failures across the complete request lifecycle, rather
than infer causes from a final exception. Cover intake, context/memory preparation,
provider admission and calls, research decisions, acquisition, review, bus delivery,
frontend receipt and terminal settlement. This is planned, not implemented here.

- Propagate session/turn/run/subtask/call IDs and parent relationships across all
  boundaries. Record structured start/end/outcome events with monotonic durations,
  active phase, deadlines, cancellation origin and chained exceptions.
- Record provider/model/effort, attempt, transport outcome, usage including unknown
  usage, and budget/reserve decisions. Distinguish local validation rejection,
  remote failure, deadline, missing evidence, delivery failure and disconnection.
- Separate bus, provider, tool/runtime and client lifecycle logs if useful, while
  retaining shared correlation and bounded rotation. Redact credentials, headers
  and personal data; full prompts/responses require explicit controlled capture.
- Detect missing terminal events and correlate late responses. Logging must not
  authorize execution or turn unknown causes into guessed diagnoses.
- Acceptance: fault injection for blocked provider, memory/tool failure, invalid
  decision, bus rejection, cancellation, disconnected client and missing terminal
  event; reconstruct each path from logs without exposing private content.

Latest observed live attempt: `839e09a7-ef59-4dba-b292-31fa137b654c`.
Plan completed at 7.79 s; search at 12.52 s; official pathlib page read at
17.71 s with five passages (signature, unlink behavior, absent file, ignored
FileNotFoundError and version-3.8 addition). A further decision began at 17.74 s
and the run reached its 90 s deadline without a decision outcome. No independent
review/conclusion was observed. The source URL was `/3/library/pathlib.html`, not
the requested pinned `/3.13/library/pathlib.html`. Collection succeeded partially;
version-specific acceptance and final assessment remain incomplete. The available
logs do not establish why the last provider decision did not return.

## Acquisition/context sub-plan — phase 5 implemented, 24 October 2026

The integration milestone is tracked in [`RESEARCH_ATELIER.md`](RESEARCH_ATELIER.md):
observed acquisition/selection phases, source restrictions and omitted sections,
live review supplements, durable replay, cancellation and conversation isolation.
The document also records the exact lexical selection behavior and its limits.
After complete validation and explicit user merge approval, start a fresh branch
from merged main to improve this sub-brain and evaluate real-web quality. The
current phase does not add a semantic reranker or paid campaign.
Validation: 1,467 Python tests passed, 8 optional benchmarks skipped; 125 UI
tests and the build passed. Seven real Chromium component/replay checks passed
on isolated synthetic observations; real-web semantic quality remains unvalidated.

## Acquisition/context sub-plan — phase 4 implemented, 24 October 2026

Question-based section retrieval, compact decision context and independent review
of the retained original source index are implemented. Omitted sections remain
addressable by observation-bound IDs; insufficient context/review budget is
explicit. Details and reproducible measurements: [`RESEARCH_CONTEXT.md`](RESEARCH_CONTEXT.md).
The frozen static comparison retains 16/16 accessible gold passages while
reducing decision evidence JSON by 30.8%; this is not a billed-token measurement.
Validation: 1,464 regression tests passed, 8 optional benchmarks skipped; all
106 final research controls passed, including real offline Chromium.
No reranking-model call was added. Next: phase 5 Atelier/runtime integration,
then phase 6 authorized real-web evaluation.

## Acquisition/context sub-plan — phase 3 implemented, 24 October 2026

Controlled HTTP/browser acquisition, source-aligned extraction, retained raw
observations and cache are implemented. Browser mode requires a prior HTTP
observation and its own budget; all allowed browser resources use the public
DNS-pinned transport. Details and measured validation:
[`RESEARCH_ACQUISITION.md`](RESEARCH_ACQUISITION.md).
The following phase-4 implementation is recorded above. No ranking-model choice
or paid LLM comparison was introduced in phase 3.
Validation: 1,445 regression tests passed, 8 optional benchmark tests skipped;
the final acquisition suite passed 21 tests, including real offline Chromium.

## Acquisition/context sub-plan — phases 1/2 complete, 24 October 2026

The frozen extraction corpus and phase-2 component comparison are in
[`tests/fixtures/research_corpus/PHASE2_RESULTS.md`](../tests/fixtures/research_corpus/PHASE2_RESULTS.md).
At equal character windows, static reference coverage improves from 11/16 with
the current reader to 16/16 with the source-aligned Trafilatura recall prototype.
The report preserves source/structure limitations and raw evidence. Nineteen
offline controls passed with pinned experimental dependencies; the production
reader/dependencies are unchanged. Crawlee was assessed through documentation
as an acquisition framework, not benchmarked as an extractor.

Sequence of this sub-plan: controlled HTTP/browser acquisition (3), contextual
selection (4), runtime/Atelier integration (5), real-web evaluation (6).
This numbering is distinct from the earlier runtime phases below.

## Avancement du 24 octobre 2026

Phases 1 et 2 autorisées : contrats versionnés, corpus hors ligne et boucle
observation/action avec lecture réelle des pages. Implémentation sur
`feat/research-evidence` ; détails et limites : `RESEARCH_EVIDENCE.md`.
Phases 3 et 4 autorisées puis reprises après les correctifs de démo poussés dans
`3f458b3` : revue séparée des sources/affirmations, citations observées,
contradictions et origines communes ; suivi et preuves conservés dans l'Atelier.
Implémentation sous validation hors ligne (64 tests recherche ciblés réussis),
pas encore validation de qualité par campagne réelle. Full-stack reporté.

Le plan phasé validé pour ces deux phases est conservé dans le dossier de travail
`../tests/bigbrain-research-plan-2026-10-24.md` à côté du document d'état.

Historique du cadrage initial : prochain jalon après validation utilisateur de la mémoire partagée et de la
réparation de projets existants, puis merge explicitement autorisé. Document de
cadrage, pas autorisation de démarrer l'implémentation. Aucun changement de code
ni recherche externe effectué pour rédiger ces notes.

## Rôle et priorité

ResearchBrain / Web Search Brain recherche, navigue et établit des conclusions
sourcées. WebAppBrain construit des applications : ce sont deux capacités
distinctes. La recherche doit aussi fournir aux agents de code des documentations
et références métier réellement consultées, sans prétendre résoudre à elle seule
toutes les erreurs métier.

La découverte de liens (Brave ou autre moteur) n'est qu'un outil du pipeline.
Éviter les délégations opaques : demande envoyée, attente indéterminée, résumé
final sans visibilité ni contrôle intermédiaire. Ne pas relancer de recherche
sur Scratchy v0 implicitement ; cette piste reste à examiner séparément.

## Boucle observable et contrôlable

1. Définir ce qu'il faut établir, les questions et les preuves attendues.
2. Choisir une action typée : recherche, ouverture, navigation, extraction,
   comparaison, arrêt ou demande de clarification.
3. Observer le résultat réel : contenu accessible, provenance, erreur, coût,
   limites et éventuel besoin de reformulation.
4. Accumuler les preuves, examiner les contradictions et décider de poursuivre
   ou de s'arrêter selon leur qualité et les budgets.
5. Présenter conclusions, sources, incertitudes et éléments non établis.

Étapes visibles, pages effectivement lues, résultats partiels consultables,
budgets de temps/appels/tokens/coût, Stop fiable et état durable sont requis.
Distinguer restauration du suivi et reprise effective du travail après restart.
Utiliser l'accès direct aux pages quand il suffit, un navigateur quand la tâche
l'exige. Les contenus web sont des données non fiables, jamais des instructions
autorisant des actions, des accès supplémentaires ou une modification des règles.

Pas de suffixe d'année automatique du type « sujet + 2026 ». La fraîcheur dépend
du besoin : version d'une documentation, état actuel d'une règle, comparaison
récente, ou concept stable. Distinguer date de publication, mise à jour et date
de l'événement ; ne pas déduire la validité de la seule récence d'une page.

## Fiabilité : source et affirmation sont deux objets distincts

Une page trouvée/citée n'est pas une information vérifiée. Évaluer séparément :

- La source : auteur identifiable, compétence pertinente, provenance, date,
  intérêts et historique de corrections accessibles. Source primaire lorsque
  pertinente ; source officielle ≠ garantie automatique de vérité ou d'exhaustivité.
- L'affirmation : preuve directe, opinion, inférence ou reprise d'un tiers ;
  contexte et périmètre, corroboration indépendante, contradictions, corrections
  et démentis. Un extrait de moteur de recherche ne remplace pas la page lue.

Pour chaque affirmation importante, conserver qui affirme quoi, sur quelles
preuves, à quelle date, et quelles sources indépendantes confirment ou contestent.
Relier les passages réellement consultés aux conclusions ; distinguer ce qui
vient d'une source et l'inférence du modèle. URL seule ou réputation du domaine
ne suffit pas. Détecter les reprises/citations circulaires : dix copies d'une
même dépêche ne sont pas dix confirmations indépendantes.

États proposés : **étayé**, **contesté**, **non vérifié**, **réfuté**, toujours
accompagnés du fondement et du périmètre, révisables si de nouvelles preuves
apparaissent. Non vérifié ne signifie pas faux ; absence de confirmation n'est
pas preuve de fausseté. Ne pas étiqueter « fake news » sur simple intuition du
modèle, réputation seule ou désaccord. Refuser toute source, lecture ou vérification
inventée ; signaler honnêtement un accès impossible ou des preuves insuffisantes.
Les exigences de preuve doivent être proportionnées à l'enjeu, pas un score de
confiance numérique arbitraire ou une majorité de liens.

## Préparer Laya sans en dépendre

Selon l'utilisateur, l'exemple de post-training de `near_agi` est un simulateur de
navigateur web. C'est une piste pertinente, pas une preuve de transfert au web
réel ; attendre les résultats `v2 bis`, ne pas supposer les capacités acquises.

Prévoir une interface stable, versionnée et indépendante du modèle :
**objectif + observation → action typée → résultat observé**. Séparer la politique
de décision du navigateur/outillage, des permissions et de la validation runtime.
Tracer ce que l'agent pouvait effectivement observer, l'action choisie, le résultat
réel, les preuves, l'erreur éventuelle et les coûts ; éviter les traces contenant
des informations futures indisponibles à la décision.

Constituer des évaluations reproductibles et un corpus gelé. Comparer d'abord
Laya hors ligne, puis en shadow mode (propositions sans exécution), avant de lui
confier des décisions limitées. Permissions, budgets, Stop et validations restent
imposés par le runtime, quel que soit le modèle. Mesurer qualité des preuves,
indépendance des corroborations, gestion des contradictions, abstention justifiée
et efficacité ; pas seulement fluidité du résumé, nombre de liens ou imitation
des décisions du modèle enseignant. La vérité des évaluations ne doit pas dépendre
uniquement du verdict de ce même modèle.

Collecte utile et minimisée : identifiants et schémas versionnés, provenance,
consentement/rétention/export/suppression à définir avant exploitation des traces
utilisateur pour l'entraînement ; pas de collecte brute opaque de navigation,
secrets, comptes privés ou données personnelles.

## Scénarios à intégrer à la future campagne

- Concept stable ne nécessitant pas de filtre de date, contre documentation
  d'une version précise ou information réellement sensible à la date.
- Source primaire contredite, page dépassée, titre trompeur, citation hors contexte.
- Multiples sites copiant la même origine ; ne pas gonfler la corroboration.
- Affirmation correcte d'une source peu connue, et affirmation non prouvée d'une
  source réputée : ni liste blanche absolue ni rejet réflexe.
- Source inaccessible, extrait insuffisant, contradictions non résolues : abstention
  et limites explicites plutôt qu'invention.
- Injection de prompt dans une page, Stop, timeout, budget atteint et restart.
- Évaluation de Laya sur observations/actions comparables, puis épreuve séparée du
  transfert simulateur → navigateur réel, sans présumer des performances.

## Ordre de suite

1. Validation réelle de `feat/shared-memory` et des réparations ; merge seulement
   après accord explicite de l'utilisateur.
2. Cadrer puis implémenter ResearchBrain observable, avec évaluation des sources
   **et des affirmations** dès le socle, et interfaces préparées pour Laya.
3. Campagnes de projets variés combinant mémoire, recherche et code ; reprise
   de la Morphable UI sur ces usages éprouvés. MCP/actions connectées, verticale
   CircuitPython/Arduino, puis Klipper restent au cap produit, pas abandonnés.
