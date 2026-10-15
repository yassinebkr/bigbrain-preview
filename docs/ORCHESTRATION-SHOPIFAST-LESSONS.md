# Orchestration multi-agents — leçons de shopifast-local à appliquer à BigBrain

Source : `~/Documents/shopifast-local/canvas/server/` (runtime/ + agent/, ~15 000 lignes
avec tests). Ces leçons s'appliquent à `bigbrain/orchestrator/` et `bigbrain/front/`,
et connectent le port UI Aplot (`docs/WEBUI-APLOT-PORT.md`), la Phase B morphable,
et le fil Laya/near_agi.

---

## 1. Route sémantique validée par schéma AVANT tout dispatch

`runtime/modelRouter.mjs` — la leçon d'ouverture : **« le sens, la négation et
le contexte ne se classent pas de façon fiable avec des listes de mots »** (la
même conclusion que le prototype mots-clés de scratchy-v0).

La route est une décision LLM à schéma JSON strict, produisant :

| Champ | Valeurs | Sens |
|---|---|---|
| `intent` | execution / creative / clarification / inspect-* / approve-pending-decision | Nature du travail |
| `complexity` | simple / adaptive | Mono-op vs multi-dépendances |
| `continuation` | review / execute | Le résultat s'affiche pour approbation OU s'applique |
| `capabilityFamilies` | 1-4 familles | Quels domaines/outils |
| `requiresVisualEvidence` | bool | Preuve visuelle nécessaire |
| `pendingDecisionId` | id | Approuver une décision en attente (conditions strictes) |

**Application BigBrain** : aujourd'hui le front brain envoie des tâches à
l'orchestrateur sans contrat typé intermédiaire. La route sémantique devient
l'étage entre `front_brain.handle_user_input` et
`orchestrator.plan/dispatch`.

**Valeur seule, sans Laya ni Jev** : une seule call LLM small/fast avec
schéma strict évite le dispatch à l'aveugle — pas de sub-brain réveillé pour
une clarification, pas de plan DAG lancé pour une lecture simple. C'est
déjà très token-efficient et efficace : la classification coûte une petite
call et économise les grosses (planning, brains, tours de clarification).
C'est la base, elle se justifie toute seule.

Laya (§5) est la couche d'amélioration par-dessus, pas un prérequis :
- **taux de réussite** supérieur sur les cas limites (négation, ambiguïté,
  décisions en attente) — mesurable sur corpus gelé ;
- **vitesse décuplée** pour certaines actions et tool calls : un forward
  pass local <100ms remplace un aller-retour LLM de 1-2s — ce qui rend
  viable un routage *par tool call* et *par morph trigger*, trop lent et
  trop cher en LLM.

## 2. Contrats typés decision → authorization → handoff

`runtime/corePolicy.mjs` + `coreContracts.mjs` — le cœur dur :

- Trois contrats distincts et liés : `decision`, `authorization`, `handoff`.
  **Une décision ne peut jamais accorder d'outils ni autoriser une écriture** —
  c'est le rôle de l'authorization.
- Binding de version : `handoff.decisionId + decisionVersion +
  authorizationId` doivent correspondre — un handoff périmé est rejeté.
- Binding de portée : `projectId/storeId/requestId` identiques sur les trois.
- Authorization expirable et révocable.
- Preuves (evidence) : horodatées, pas de preuve du futur, pas de doublons.
- `decision_not_ready`, `adaptive_work_requires_planning` : l'adaptatif ne
  part jamais sans plan.

**Application BigBrain** : `orchestrator/task_tracker.py` + les messages bus
gagnent ce chainage typé. Concrètement : un `TaskMessage` du bus ne suffit pas
à exécuter une écriture ; il faut la chaîne decision (front brain) →
authorization (politique, expire) → handoff (orchestrateur, version liée).
Renforce V5 (human gate) et matérialise « the human is root » de ClawOS.

## 3. Orchestration d'outils conservatrice

`runtime/toolScheduler.mjs` + `toolExecutionPolicy.mjs` :

- **Seules les lectures certifiées indépendantes peuvent se chevaucher** ;
  tout le reste est une barrière (écritures, prérequis, génération, états
  terminaux) — l'ordre reste garanti.
- `maxConcurrency` plafonné (2), file incrémentale.
- **Réservation de budget par appel** avant dispatch (`reserveBudget`) —
  un appel non budgété est skippé, pas exécuté.
- Abort signal propre, résultats marqués `skipped`.

**Application BigBrain** : le pool `python_brain_*` (parallélisme non
ordonné, cf. le test flaky `test_pool_dispatches_to_multiple_workers`)
gagne la même discipline : lectures parallèles, écritures en barrière,
budget lié au `UsageTracker` (Phase 5 déjà portée — il manque la
réservation *avant* dispatch).

## 4. Décisions en attente + continuation review/execute

`runtime/pendingSectionDecision.mjs`, `decisionStore.mjs`, `creativeDecision.mjs` :

- Une décision créative devient un objet persisté avec id, proposé à
  l'utilisateur ; `continuation: review` = montrer et attendre,
  `execute` = appliquer.
- L'approbation est stricte : « accepte la proposition exacte sans
  condition » — une réponse conditionnelle/modifiée/ambiguë **n'approuve
  pas** (`approve-pending-decision` du routeur).

**Application BigBrain** : `front/focus_manager.py` + la Phase B du port
UI — les décisions en attente sont le pendant UX du morphable : une
décision créative ouvre le workspace correspondant avec le rendu à
approuver. Et V5 human gate devient pilotable depuis l'UI au lieu d'un
timeout de 300s.

## 5. Discipline Jev : évaluation en ombre, corpus gelé — LE point Laya

`agent/systemOneShadow.mjs` (via chat.mjs) + `runtime/jevCorpus.v1/v2.mjs` :

- **La réponse de Jev est de la télémétrie inerte** — même en désaccord,
  même si ses champs ressemblent à des outils ou des autorisations, elle
  n'influence jamais l'exécution en prod tant qu'elle n'est pas validée.
- Corpus d'évaluation gelé et versionné (`jev-shadow-v2`, question set
  `shopifast-routing-v2`), labels ground truth **séparés des prédictions**,
  exécutable par des évaluateurs offline.
- Question sets versionnés — la comparaison corpus/model est reproductible.

**Application BigBrain + near_agi** : c'est le pattern exact pour évaluer
Laya fine-tuné comme routeur local (le v002bis de near_agi) : mode ombre
sur le vrai trafic BigBrain, corpus gelé versionné de routes BigBrain,
labels séparés. La leçon v001 de near_agi (raccourcis de surface features)
est déjà le complément : le corpus doit randomiser identifiants/chemins.
Un Laya local qui bat les baselines sur le corpus gelé remplace Jev
hébergé — et la route sémantique (§1) devient locale et mesurable.

## 6. Mémoire typée partagée entre agents

`runtime/typedMemory.mjs`, `sharedProjectMemory.mjs`, `projectMemory.mjs` :

- Mémoire typée par projet, partagée entre agents avec contrats de lecture/
  écriture, pas de blob informes ; caches de lectures par requête
  (`requestReadCache.mjs`).

**Application BigBrain** : `memory/memory_manager.py` (ChromaDB) gagne des
contrats typés par espace (brain/project/workspace) — même direction que
`SharedContextStore` de scratchy-v0.

## 7. Déjà porté, à étendre

- `usageLedger` → déjà porté en Phase 5 (`llm/usage.py`) ; manque la
  réservation de budget par appel (§3).
- `performanceTrace` → le pattern de spans existe dans codexProvider ;
  l'orchestrateur BigBrain gagnerait des spans par tâche (decision→plan→
  dispatch→verify) pour mesurer où part le temps.

---

## Ordre d'application proposé

1. **Après le port UI Aplot (Phase A)** : la route sémantique (§1) côté
   front brain — déjà efficace et token-efficient SANS Laya/Jev (petite
   call LLM, schéma strict, économie sur planning/brains/clarifications).
2. **Mode ombre Laya** (§5) : option d'amélioration une fois la base en
   prod — corpus gelé BigBrain + ombre sur trafic réel (réutilise le
   harnais near_agi et le pattern shopifast). Gain : taux de réussite sur
   les cas limites, et vitesse quasi instantanée qui rend viable le
   routage par tool call / par morph trigger.
3. **Contrats decision→authorization→handoff** (§2) dans l'orchestrateur,
   en même temps que les décisions en attente côté UI (§4) — les deux
   se valident mutuellement.
4. **Scheduler conservateur + budgets** (§3) sur le pool python_brain.
5. Mémoire typée (§6) et spans orchestrateur (§7) en fin de parcours.
