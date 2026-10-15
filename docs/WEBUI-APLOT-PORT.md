# Port Aplot AI — nouvelle base UI de BigBrain

**Décisions validées** (session du 15/10/2026) :

1. **Aplot (okcomputer_ui_v11) devient la base UI de BigBrain** — pas une inspiration, le code. React 18 + Vite + TypeScript + Tailwind + Framer Motion + Zustand + shadcn/ui. Fin du vanilla HTML/CSS/JS (`web/static`).
2. **Adaptation côté client** : `connection.ts` est réécrit pour parler le bus WS BigBrain — le serveur Python reste intact en dehors des frames manquantes.
3. **Emplacement** : `web-ui/` dans bigbrain-preview (un seul repo pendant la phase intense de changement de contrat ; extraction possible plus tard).
4. **Ordre** : Phase A = socle Aplot fonctionnel sur BigBrain. Phase B = morphable multi-workspaces en Framer Motion (séparé, après).

Référence : `/mnt/data4tb/bck_ssd/pccfai/projects/dev/okcomputer_ui_v11/` (design brief : `design-brief-kimi.md`).

## Contrat actuel — état des lieux

### Ce qu'Aplot attend (src/lib/connection.ts, 669 lignes)

- **Handshake** : frame `connect` à l'ouverture, réponse attendue avant `connected`
- **Envoi** : frames `chat.send` avec `messageId` ; statuts de message émis localement (`sending` → `queued` → `sent`), fallback HTTP `/api/send`
- **Réception** : frames typées → callbacks : `onMessage`, `onStreamDelta`, `onStatusChange`, `onAgentActivity`, `onQueueDrained`, `onQueueReplay`, `onSendError`, `onMessageStatus`, `onCanvasUpdate`, `onUserInfo`, `onReconnected`, `onRemoteUserMessage`, `onResumeCatchUp`, `onRunEnd`
- **Req/res** : `pendingRequests` (ex. `chat.history`), keepalive ping/pong, reconnexion (20 tentatives), synthèse de cycle de run
- **Auth** : cookies `scratchy_session`/`scratchy_auth` ou localStorage `aplot_auth_token`

### Ce que BigBrain expose (bigbrain/web/)

- `WebAdapter` (`adapter.py`, 348 lignes) : rend les messages/progress/brain_status/code_output/research_results, focus mode, workspaces, pipelines ; émet via `_emit_event`/`_emit_state` sur le bus
- `/ws` : chaque tab = 1 WS ; events du bus forwardés à tous les clients ; messages client forwardés au bus
- REST existants : `/api/focus` (GET/POST), `/api/status`, `/api/models`, `/api/usage`, `/api/auth/codex/*`, `/api/auth/mistral/*`
- **À vérifier en premier** : le chemin exact chat-input → front brain → réponse (le vieil UI passait par le bus ; identifier les shapes d'events), et si le front brain streame des deltas ou seulement des messages complets

## Architecture cible

```
bigbrain-preview/
├── bigbrain/                  # backend (ajouts minimaux de frames)
│   └── web/server.py          # + routes: sert web-ui/dist/, /assets
│                              # + frame chat.send → front brain
│                              # + handshake welcome + ping/pong
├── web-ui/                    # app Vite React d'Aplot
│   ├── src/lib/connection/
│   │   ├── types.ts           # interface ConnectionCallbacks (l'actuelle, conservée)
│   │   ├── scratchy-adapter.ts  # l'existant connection.ts, renommé (réutilisable)
│   │   └── bigbrain-adapter.ts  # NOUVEAU — parle le bus WS BigBrain
│   ├── src/store/appStore.ts  # inchangé (les callbacks couvrent déjà tout)
│   ├── src/components/        # + BrainStatusPanel.tsx, CodeOutputPanel.tsx
│   │                          #   TaskBoard ← events tasks du bus
│   └── vite.config.ts         # proxy dev → localhost:3007
```

**Règle d'or** : l'interface `ConnectionCallbacks` ne change pas — c'est le contrat entre adaptateur et store. Tout le travail de mapping vit dans `bigbrain-adapter.ts`.

## Plan d'implémentation — Phase A

### Étape 0 — Copie et nettoyage (réversible, 30 min)

- Copier `app/` → `web-ui/` (SANS node_modules, dist, .git)
- Fixer les ports : dev vite 3011 → proxy `localhost:3007` (port web bigbrain)
- `npm install && npm run build` → vérifier que ça build tel quel
- Commit d'import séparé (historique propre)

### Étape 1 — Inventaire du contrat (avant tout code de mapping)

- Lister chaque event émis par `WebAdapter._emit_event`/`_emit_state` (types + shapes)
- Identifier le chemin d'envoi de message du vieil UI (`chat-panel.js` → bus → front brain)
- Vérifier si le front brain streame des deltas (sinon : Phase A = messages complets, streaming en finition)
- Écrire ces shapes dans ce md (section "Frames BigBrain" ci-dessous, à remplir)
- Fixtures pytest : chaque frame émise attendue

### Étape 2 — Frames manquantes côté serveur (Python)

- `chat.send` : route WS → même chemin que le vieil UI (front brain), avec ack + messageId status
- Handshake : frame `welcome` à la connexion (auth si `BIGBRAIN_WEB_PASSWORD` actif)
- Ping/pong keepalive
- `chat.history` : renvoyer les N derniers messages du front brain
- Servir `web-ui/dist/` : `/` → index.html, `/assets/*` statiques, fallback SPA

### Étape 3 — `bigbrain-adapter.ts`

- Même classe `Connection` (API publique : `connect/send/disconnect/setCallbacks`), mêmes callbacks
- Handshake → welcome, frames bus → callbacks mappés :
  - event message/réponse front brain → `onMessage`
  - deltas (si existants) → `onStreamDelta`
  - brain status → `onAgentActivity` (type `brain_status`)
  - tasks → `onAgentActivity` (type `task_update`) pour TaskBoard
  - canvas/compaction → `onCanvasUpdate`
- Reconnexion + keepalive repris de scratchy-adapter (la logique est saine)
- Auth : Basic (web password) → le mode déjà en place ; token localStorage plus tard

### Étape 4 — App.tsx : choisir l'adaptateur

- `connectionFactory('bigbrain')` par défaut, `localStorage.aplot_backend='scratchy'` pour basculer
- Aucun changement de store attendu ; corriger les bugs listés dans le design brief au passage (streaming pop : le message finalisé remplace le slot streaming sans unmount — cf. brief §2)

### Étape 5 — Panels BigBrain en composants React

- `BrainStatusPanel` : liste des brains, statut idle/busy/error, indicateur plat (design Aplot, sans glow)
- `TaskBoard` existant ← brancher sur events tasks
- `CodeOutputPanel` + research results ← events existants de l'adaptateur
- `SettingsPanel` → endpoints `/api/models`, `/api/auth/codex/*`, `/api/auth/mistral/*` (fetch directs, déjà fonctionnels)

### Étape 6 — Cutover

- `python -m bigbrain --web` sert `web-ui/dist/`
- L'ancien `web/static` garde une route `/legacy` pendant la parité, puis suppression
- Les tests web pytest (87) qui testent le vieil UI : refactor sur les nouvelles routes serveur uniquement ; le comportement UI vit dans le build

### Étape 7 — Finition

- Streaming delta si manquant ; command palette ; mode mobile vérifié
- Le design brief d'Aplot (bugs §1, §2, mobile §3) traité

## Phase B (après validation de la Phase A)

- Morphable workspaces sur Framer Motion : `<motion.div layout>` + `LayoutGroup` + `AnimatePresence`, panels React clés par type (identité stable = morph fiable par construction)
- Déclencheurs : focus events + RT state stream du bus
- `morph.js`, `layout.js` artisanals : supprimés définitivement

## Risques / inconnues

| Risque | Mitigation |
|---|---|
| Le front brain ne streame pas de deltas | Phase A en messages complets, streaming en étape 7 |
| Shapes d'events bus non documentées | Étape 1 = inventaire + fixtures avant tout mapping |
| Bugs connus d'Aplot (history cassée, streaming pop) | Listés dans le brief, corrigés en étapes 3-4 |
| 87 tests pytest liés au vieil UI | Refactor à l'étape 6, pas avant |

## Frames BigBrain (inventaire — étape 1, validé dans le code)

### Serveur → client (toutes via `message.to_log_dict()`, forwardées à chaque tab)

Envelope commune :

```json
{ "type": "state|event|task|result|progress",
  "source": "...", "target": "...", "payload": { "event": "..." } }
```

À la connexion (dans cet ordre) : `focus.initial` (state), `system.status`
(event, bus stats), puis le replay buffer (frames passées, `_replay: true`).

Events applicatifs :

| `payload.event` | Shape | Source |
|---|---|---|
| `chat.message` | `{role: "assistant"\|"system", text, type}` | WebAdapter.render_message ← front brain |
| `task.progress` | `{task, progress?, status}` | WebAdapter.render_progress |
| `brain.status` | `{brain, state: "idle"\|"offline", running, ...}` (state frame) | WebAdapter.render_brain_status |
| `workspace.overview` | `{workspaces}` | WebAdapter.render_workspace_overview |
| `task.received / task.complete / task.failed` | events tâches | orchestrateur |
| `subtask.started / subtask.complete / subtask.failed` | events sous-tâches | orchestrateur |
| `brain.started / brain.complete` | events exécution | orchestrateur |

Replay buffer : 100 frames max, 5 min, types `result/progress` + les events
ci-dessus — les reconnectés ne perdent rien.

### Client → serveur (WS handler : source forcée `morphable_ui` → BusMessage)

| Frame client | Devenu | Note |
|---|---|---|
| Chat (ancien UI) | `{type: "task", target: "front_brain", payload: {type: "user_message", text}}` | front brain écoute `*`, filtre `payload.type == "user_message"` |
| Focus | `POST /api/focus` ou bus | — |

### Limites constatées → décisions

- **Pas de streaming** : front brain appelle `stream=False` partout ;
  les réponses arrivent en `chat.message` complet. Phase A = pas de
  `onStreamDelta` ; streaming en étape 7.
- **Pas de handshake ack ni ping/pong applicatif** : à ajouter (étape 2).
- **Pas d'historique chat serveur** : à ajouter (buffer simple, étape 2).
- **Ack de message** : rien aujourd'hui ; `message.status` à ajouter pour
  les statuts sending/queued/sent d'Aplot (étape 2).

### Mapping adaptateur (étape 3)

- `chat.send` → frame task user_message + ack `message.status`
- `welcome` (à créer) → connecté ; `chat.history` (à créer) → `setMessages`
- `chat.message` → `onMessage` ; `brain.status` + events brain → `onAgentActivity`
- events task/subtask → `onAgentActivity` (TaskBoard) ; `_replay` → `onQueueReplay`

## Backlog (retours live, à traiter plus tard)

1. **Feedback d'action agent** : quand l'agent crée un fichier, l'UI ne
   propose rien — ouvrir/proposer le workspace ou une vue code, highlight
   du bouton Workspace, lien vers le fichier écrit. C'est le job de la
   Phase B (morphable).
   - *Partiellement fait* : le RunPanel (v2 des pastilles, sous le chat)
     liste les fichiers écrits d'un run — cliquables, ils ouvrent le
     viewer du workspace. Reste le "proactive nudge" (highlight du bouton
     Workspace, ouvrir une vue code sans changer de layout).
2. **Port du harness déterministe fpga → python_brain** : la couche
   vérification déterministe outillée comme sur ../fpga (typed tools,
   replay des runs, vérifs déterministes avant review LLM). À explorer
   dans fpga/backend puis planifier avant implémentation.
3. Sessions persistées (l'historique est aujourd'hui mono-conversation).
4. Drag/drop move dans l'explorateur (l'endpoint /api/fs/move existe).
5. Premier plugin premium + paywall Stripe (billing scratchy à porter).

## Changelog UX récent

- **RunPanel v2** (`web-ui/src/components/RunPanel.tsx`) : remplace les
  pastilles d'activité. Visibilité dérivée de l'état du run
  (task.received → task.complete/failed), pas d'un timer par événement —
  corrige l'apparition/disparition périodique. Repliable : une ligne
  (statut, progression x/y, nb fichiers) ; déplié : plan (étapes, brain,
  durée), fichiers écrits cliquables, nudge sandbox, erreurs.
- **Mode global = projet sandbox** : sans projet sélectionné, les écritures
  des brains vont dans `workspace/sandbox/` (projet auto-créé avec manifest,
  visible dans le sélecteur de projets) au lieu du pool `python/` en vrac.
  `apply_current_project()` est appelé au démarrage ; le front brain
  annonce le contexte sandbox au LLM. Le RunPanel affiche un nudge quand
  des fichiers atterrissent en sandbox sans projet sélectionné.
- **Largeur du chat sur PC** : la colonne centrale passe de 720px à
  1200px à partir de md (Layout.tsx) — la vue "téléphone" est réservée
  aux vrais téléphones.
