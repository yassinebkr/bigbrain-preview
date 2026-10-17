# Recherche approfondie — Generative UI, agents et interfaces morphables

État de l'art au 17 octobre 2026 · Rapport de recherche (GPT-6 Thinking, high) pour la
phase "morphable UI" (item 7) de BigBrain. Sauvegardé tel quel hors artefacts de rendu.

## Synthèse exécutive

La vision est techniquement réalisable, mais ses trois composantes n'ont pas la même
valeur produit ni le même niveau de risque.

L'idée la plus solide n'est pas le robot flottant. C'est la combinaison d'un espace de
travail contextuel, d'un catalogue de composants contrôlé et d'un état partagé entre
l'agent et l'interface.

| Priorité | Composante | Verdict |
|---|---|---|
| 1 | Templates par tâche + composants contraints | Valeur élevée, risque maîtrisable. Construire autour de surfaces stables, de données typées et de règles explicites de composition. |
| 1 | Surface de travail droite contextuelle | Potentiel élevé pour la recherche, le code et les opérations longues. Principal risque : l'instabilité spatiale. |
| Expérimental | Compagnon flottant et mobile | Différenciation visuelle intéressante, bénéfice fonctionnel non démontré. À tester contre une simple présence ancrée. |

Ces niveaux de priorité sont des jugements d'architecture produit, pas des scores
scientifiques.

### Une distinction fondamentale : trois couches, trois responsabilités

| Couche | Technologie de référence | Responsabilité |
|---|---|---|
| Communication et exécution | AG-UI | Flux agent ↔ frontend, états, outils, interruptions |
| Description de l'interface | A2UI ou schéma propriétaire | Déclarer quoi afficher et quelles interactions autoriser |
| Orchestration de l'espace | Notre reconciler | Décider où, quand et comment afficher les surfaces |

Ce découpage est déterminant : A2UI ne remplace pas AG-UI, et aucun des deux ne
résolvent à eux seuls le problème du layout morphable.

Découverte importante : A2UI v0.9 n'est plus la version courante — v0.9.1 est la
version de production, v1.0 est candidate. Examiner les différences avant de figer
un schéma interne.

**Recommandation centrale : l'agent choisit une intention de présentation, jamais la
géométrie de l'écran. Le produit garde la maîtrise du placement, de la visibilité, du
focus, des transitions et des autorisations.**

## 1. État de l'art : protocoles, produits et recherche

### 1.1. A2UI — la référence la plus proche de notre architecture

Spécification publique (Google / open source), v0.9.1 courante. A2UI décrit des
interfaces sous forme de messages JSON indépendants, transportables en JSONL,
WebSocket ou autre. Le renderer transforme ces descriptions en composants natifs.
Ce n'est ni du HTML généré par le modèle ni de l'exécution de JS arbitraire.

Opérations serveur → client (v0.9) :

| Opération | Fonction |
|---|---|
| `createSurface` | Créer une surface avec `surfaceId`, `catalogId`, thème optionnel |
| `updateComponents` | Ajouter/modifier les composants de la surface |
| `updateDataModel` | Mettre à jour les valeurs liées aux composants |
| `deleteSurface` | Supprimer une surface et son contenu |

Les composants ont des identifiants stables et forment un arbre par références
d'identifiants. Données séparées de la structure, accessibles par JSON Pointers.
Renderer progressif.

Exemple conforme v0.9 :

```
{"version":"v0.9","createSurface":{"surfaceId":"run_evidence","catalogId":"https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"}}
{"version":"v0.9","updateComponents":{"surfaceId":"run_evidence","components":[{"id":"root","component":"Card","child":"status"},{"id":"status","component":"Text","text":{"path":"/run/status"}}]}}
{"version":"v0.9","updateDataModel":{"surfaceId":"run_evidence","path":"/run","value":{"status":"Analyse en cours"}}}
```

Dans notre produit, le `catalogId` désignerait notre propre catalogue versionné.

**Interactions et callbacks (point crucial)** :
- Actions serveur (`submit_form`) avec `surfaceId`, `sourceComponentId`, timestamp, contexte.
- Fonctions locales `functionCall`, exécutées par le renderer seulement si enregistrées dans son catalogue.
- Validations locales prédéfinies (`required`, `regex`, `email`).
- `sendDataModel` optionnel — renvoie l'état complet de la surface quand actif : recommander des événements ciblés ou projections minimales plutôt qu'un partage intégral systématique.

Une action A2UI n'est pas un tool call d'agent : le bouton émet une intention ; le
contrôleur serveur décide si elle déclenche un outil, un changement d'état ou une
confirmation.

**Adopter / adapter / ignorer** :

| Décision | Élément | Justification |
|---|---|---|
| Adopter | Surfaces identifiées et persistantes | Plusieurs espaces actifs sans confusion |
| Adopter | Catalogue validé côté serveur | Contraint le vocabulaire de l'agent |
| Adopter | Séparation composants / données | Pas de reconstruction d'UI pour un changement de statut |
| Adopter | Mises à jour incrémentales | Idéal pour code, résultats, evidence streamés |
| Adapter | `createSurface` | Ne doit pas signifier automatiquement « ouvrir un panneau » |
| Adapter | `deleteSurface` | Masquer ou conserver dans l'historique plutôt que détruire |
| Adapter | Actions client → serveur | Registre d'actions autorisées + permissions |
| Adapter | `sendDataModel` | Partager uniquement les champs nécessaires |
| Différer | Multiples renderers natifs | Inutile tant qu'on cible React Web |
| Ignorer | Transport A2A obligatoire | Notre WebSocket suffit |
| Éviter | Génération libre de propriétés stylistiques | L'agent ne devient pas responsable du design system |

A2UI doit être une **inspiration de contrat et d'interopérabilité**, pas une
dépendance imposée dès la première phase. Privilégier un schéma interne réduit,
compilable vers A2UI v0.9.1 quand la compat externe devient utile. La v1.0 candidate
introduit `actionId`, `actionResponse` RPC client, évolutions de surface — ne pas
implémenter comme si v0.9.

### 1.2. AG-UI — le modèle de synchronisation à retenir

Protocole événementiel agent ↔ application (ne prescrit pas l'apparence).

| Famille | Événements utiles |
|---|---|
| Exécution | `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR` |
| Étapes | `STEP_STARTED`, `STEP_FINISHED` |
| Chat | `TEXT_MESSAGE_START/CONTENT/END` |
| Outils | `TOOL_CALL_START/ARGS/END/RESULT` |
| État | `STATE_SNAPSHOT`, `STATE_DELTA` (JSON Patch RFC 6902) |
| Activité | Événements subagents, attribution |

**Le « working memory partagé »** est la partie la plus intéressante pour notre
vision : l'agent expose un état structuré observable par l'interface ; le frontend
peut faire évoluer des champs autorisés. Snapshot → base cohérente ; deltas →
modifications ciblées ; resynchronisation prévue si les patchs deviennent
incohérents.

Mais état bidirectionnel ≠ propriété indifférenciée. Trois domaines recommandés :

| État | Autorité principale | Exemple |
|---|---|---|
| Exécution | Backend / orchestrateur | Étape active, statut, artefacts, progression |
| Workspace | Frontend / utilisateur | Panneau épinglé, dimension, onglet actif |
| Collaboratif | Partagé, mais arbitré | Sélections board, annotations, propositions |

Un modèle qui peut lire l'état du layout n'a pas le droit de l'écraser : il propose,
une politique d'application décide. AG-UI ne résout pas automatiquement conflits,
permissions, persistance — sa doc recommande explicitement de les traiter.

**Décision : emprunter le vocabulaire AG-UI pour normaliser notre bus existant ;
ne migrer vers son runtime complet que si interopérabilité réelle.**

### 1.3. OpenAI : ce qui est effectivement livré

- **Canvas** (oct. 2024) — collaboration côte à côte ; l'enseignement reste : séparer
  un artefact persistant du flux conversationnel.
- **Apps SDK / MCP Apps** (2025–2026) — widgets interactifs dans le chat, pilotés par
  des outils MCP ; UI web en iframe communiquant avec l'hôte.
- **ChatGPT Work** (juil. 2026) — tâches longues, artefacts, suivi de l'avancement,
  correction de cap, approbation d'actions.
- **Intelligent UI** (7 oct. 2026) — LA découverte majeure : composants natifs
  streamables, compilateur incrémental qui traite l'interface pendant la génération,
  entraînement du modèle à décider de l'organisation, de l'interactivité, et des
  situations où du texte simple suffit. Le point clé : un bon système GenUI apprend
  **quand ne pas générer d'interface**. Valide le couple catalogue contraint +
  rendu incrémental ; ne démontre pas que le modèle doit contrôler toute
  l'organisation persistante d'un workspace.

**Open-JSON-UI** : présenté par AG-UI/CopilotKit comme standardisation du schéma
interne OpenAI, mais **aucune source primaire OpenAI vérifiable** d'un schéma
normatif versionné. Verdict : piste de veille, pas un fondement. Pour implémenter
aujourd'hui : A2UI et AG-UI sont bien mieux documentés.

### 1.4. Apple : ce qu'il faut réellement retenir

- **Liquid Glass** : hiérarchie contenus/contrôles, couches translucides, navigation
  contextualisée. Recommandations officielles : réserver aux contrôles et
  navigation, éviter l'accumulation dans la couche de contenu. Ce n'est PAS une
  démonstration de l'efficacité des interfaces génératives — c'est un langage visuel.
- **visionOS Ornaments** : le modèle conceptuel directement utilisable pour notre
  compagnon — un contrôle secondaire peut flotter près d'une fenêtre, rester **lié**
  à elle et conserver sa position au défilement. « Flottant visuellement, ancré
  fonctionnellement. » Recommandations : limiter le nombre de fenêtres, éviter les
  mouvements périphériques distrayants.
- **Siri contextuel (App Intents WWDC26)** : relier les éléments visibles à des
  entités et actions métier (« le troisième », « cette conversation »). pertinent
  pour notre board : l'agent a besoin des **identifiants structurés** de la
  sélection courante, pas d'une capture d'écran. → Proposition d'un **context
  registry** exposant sélection, artefacts visibles, run actif. Plus innovant
  qu'un robot qui suit le pointeur.
- Aucune spécification Apple n'établit un « Siri spatial » animé libre sur desktop
  comme pattern éprouvé.

### 1.5. Recherche académique : résultats favorables et défavorables

| Étude | Résultat | Conséquence pour nous |
|---|---|---|
| Chen et al., 2025 — Generative Interfaces for LMs | Préférence humaine pour les interfaces générées dans >70 % des cas | La présentation interactive peut dépasser le chat linéaire |
| Cao et al., CHI 2025 — Generative and Malleable UIs | Problèmes de continuité et de contrôle liés à la régénération | Structures et data models évolutifs, pas des remplacements complets |
| Peng et al., avr. 2026 — Efficient Personalization | 12 000 jugements ; divergences marquées entre designers | Le layout optimal n'est pas universel : enregistrer préférences et corrections |
| Design Theater, juil. 2026 | Sur 120 UI générées, >25 % des justifications de design et 34 % des exigences fonctionnelles non reflétées dans le résultat | **Ne jamais valider un layout sur l'explication convaincante du LLM** |
| EvoGenUI-Bench, août 2026 | Meilleur modèle : 74,9 % de réussite par tour, seulement 37,3 % d'épisodes complets de 5 tours | Le vrai problème est la stabilité multi-tour, pas la génération initiale |
| GenUI-Harness, oct. 2026 | Workflows avec bases de données : tours de dialogue moyens 3,4 → 1,2 | Les représentations structurées réduisent la friction dans des workflows précis |

Conclusion nuancée : la GenUI a un intérêt empirique, mais les modèles restent
sensiblement moins fiables quand une interface doit **survivre à plusieurs
modifications**. Cela soutient fortement l'idée de templates curés. Les trois
dernières publications sont des prépublications décrivant leurs propres benchmarks.

Pour le spatial : « Context Matters! » (oct. 2026) propose un cadre spatial/social/
sémantique pour agents incarnés — cadre préliminaire AR, pas une validation d'un
robot flottant desktop.

## 2. Templates par type de tâche : critique et proposition

### 2.1. Le piège : supposer qu'une tâche = un template

Fonctionne pour des intentions simples (recherche, code, rédaction, board) mais
devient ambigu pour des tâches multi-agents (« Recherche les implémentations de
Madgwick en C++, compare-les, crée un benchmark et ajoute les conclusions au
board »). La bonne unité de composition n'est pas la tâche globale mais **la phase
active du workflow et les artefacts qu'elle produit**.

Architecture à deux niveaux : Task Intent (objectif, type de travail, artefacts
attendus) → Workspace Reconciler (permissions, focus, surfaces existantes,
préférences, espace) → Surface contextuelle (vue de l'artefact actif). Le changement
de template = changement de mode de présentation, pas remplacement du workspace.

### 2.2. Les templates à construire

| Template | Surface principale | Éléments secondaires | Déclenchement |
|---|---|---|---|
| `conversation` | Chat | Statut compact | Question simple, discussion |
| `research` | Evidence / sources | Synthèse, citations, progression | Recherche multi-sources |
| `code` | Éditeur / diff / résultat | Tests, terminal, logs | Code en production/exécution |
| `document` | Artefact éditable | Historique, commentaires | Rédaction ou transformation |
| `board` | Canvas structuré | Inspecteur, evidence, relations | Manipulation d'objets |
| `review` | Comparaison / validation | Risques, changements, approbation | Décision utilisateur requise |

Ajouter une couche de composition transversale (ex. `EvidencePanel` partagé entre
`research` et `code`). Distinguer composants **visuels** (texte, bouton, liste,
tabs, conteneur) des composants **métier** (`RunOutput`, `EvidenceCard`,
`DiffViewer`, `ArtifactPreview`, `ApprovalCard`, `BoardSelection`). Commencer avec
le catalogue actuel, n'ajouter que les composants métier dont les tests prouvent
la valeur.

### 2.3. Comment l'agent choisit le template

Ne pas demander au LLM « quelle interface afficher ? » (trop imprécis, instable à
chaque tour). Trois étapes : (A) détection d'intention — l'objectif et les artefacts
attendus ; (B) **proposition de présentation typée** ; (C) réconciliation
déterministe — le frontend accepte, ajuste ou rejette.

```ts
type TemplateId = "conversation" | "research" | "code" | "document" | "board" | "review";
type SurfaceId = "evidence" | "run-output" | "artifact" | "board" | "diff" | "approval";

type PresentationProposal = {
  proposalId: string;
  runId: string;
  template: TemplateId;
  primarySurface?: SurfaceId;
  secondarySurfaces: SurfaceId[];
  reason: "artifact-created" | "tool-running" | "evidence-ready"
        | "review-required" | "user-requested";
  urgency: "background" | "normal" | "blocking";
};
```

Ce qui manque volontairement : `positionX`, `positionY`, `width`, `height`,
`zIndex`, `html`, `css`. **L'agent indique le besoin ; le renderer décide de la
géométrie.** C'est cette séparation qui rend le système prévisible.

### 2.4. Le reconciler : le véritable cœur du produit

Cinq responsabilités :
1. **Validation** — schéma, artefacts réels, provenance, permissions.
2. **Résolution** — intention → configuration compatible (largeur, template actif, préférences).
3. **Conservation** — sélection, focus, scroll, formulaires en cours, composants épinglés.
4. **Application** — ensemble cohérent de modifications, pas une succession de déplacements visibles.
5. **Récupération** — rejouer la dernière configuration valide après erreur, reconnexion WS, proposition invalide.

```ts
function shouldApply(proposal: PresentationProposal, workspace: WorkspaceState): boolean {
  if (workspace.userLocked) return false;
  if (workspace.isEditing && proposal.urgency !== "blocking") return false;
  if (workspace.pinnedSurface && proposal.primarySurface !== workspace.pinnedSurface) return false;
  return true;
}
```

(Pseudo-code architectural — la version réelle vérifie aussi permissions, identité
du run, ordre des événements, existence des surfaces.)

**Trois niveaux d'autonomie** : Automatique (mettre à jour les données d'un composant
visible, statut compact) / Suggestion (nouvelle surface, changement de template) /
Confirmation (action externe sensible, écrasement, suppression). « Une interface qui
change toute seule n'est pas forcément une interface intelligente » (Horvitz, CHI
1999 : coûts d'une initiative automatique mal synchronisée).

### 2.5. Layout libre vs templates curés : verdict

Le layout libre peut inventer des compositions imprévues, mais : validation
ergonomique, continuité entre tours, surface d'attaque, repères de l'utilisateur —
quatre difficultés sérieuses (CHI 2025, EvoGenUI-Bench).

**Rétention : 80–90 % de structure décidée par notre design system, 10–20 % de
composition contextuelle pilotée par l'agent.** (Orientation de conception, pas un
résultat expérimental.) Le modèle doit avoir assez de liberté pour choisir quoi
montrer, pas assez pour réinventer les conventions.

## 3. Le robot compagnon : interaction, attention et anthropomorphisme

### 3.1. Le meilleur argument CONTRE le concept vient de la recherche

Rickenberg & Reeves (CHI 2000) : des personnages donnant l'impression de surveiller
l'activité **augmentaient l'anxiété et dégradaient la performance**, tout en
accroissant la confiance accordée au site. Un personnage peut rendre une interface
plus engageante ou crédible **sans améliorer la qualité du travail** — exactement le
piège potentiel de notre robot.

Calm technology (Weiser & Brown, 1995) : l'information doit pouvoir passer entre le
centre et la périphérie de l'attention sans solliciter constamment. Le robot doit
être un **périphérique informationnel**, pas un personnage cherchant à être regardé.

### 3.2. Le bon comportement : une machine à états

| État | Signal visuel | Mouvement |
|---|---|---|
| `idle` | Présence minimale, éventuellement masquée | Aucun |
| `working` | Activité discrète, étape en cours | Animation locale très subtile |
| `result-ready` | Indicateur de résultat disponible | Transition courte, uniquement si utile |
| `needs-input` | Demande explicite d'attention | Ancrage près de la zone d'action |
| `blocked` | Échec ou conflit identifié | Signal d'état, pas d'agitation |
| `user-engaged` | Commandes rapides ouvertes | Immobilité pendant l'interaction |

Un robot qui se déplace continuellement pour montrer qu'il travaille n'apporte guère
plus qu'un indicateur d'activité animé. Un robot qui permet de comprendre quel
agent travaille, sur quoi, avec quel résultat et quelle intervention est attendue
peut devenir une vraie interface.

### 3.3. Politique de mouvement

- **Déplacement justifié** : invocation par l'utilisateur, drag volontaire, rattachement demandé.
- **Transition discrète** : une surface s'ouvre, le compagnon préserve un ancrage cohérent sans masquer le contenu.
- **À proscrire** : suivre le curseur, traverser le chat, flotter devant le code, se repositionner à chaque changement de sub-agent, attirer l'attention pour un résultat mineur.
- **Règle simple** : aucun déplacement autonome pendant une interaction exigeant de la précision (rédaction, sélection, édition de code, drag, comparaison d'evidence).

Transitions framer-motion courtes, easing cohérent, respect de
`prefers-reduced-motion` (WCAG 2.2 : risques des animations non essentielles).
150–250 ms comme point de départ à tester.

### 3.4. Ancrage : trois variantes à tester

Ancré (coin inférieur, position persistante connue) — **défaut recommandé** ;
Contextuel (rattaché à la surface active selon règles déterministes) — sur demande ;
Libre — à évaluer. ISMAR 2026 : aucune stratégie d'ancrage ne domine universellement.
« Beyond Activation » (oct. 2026, AR) : le résultat le plus transférable n'est pas le
regard comme déclencheur mais la **clarté des transitions d'état**.

### 3.5. Signaux anthropomorphiques

L'apparence doit correspondre aux capacités réelles. Iconographie expressive pour
les statuts : oui. Animations prétendant manifester émotion/inquiétude/impatience :
mise en scène superflue. Le robot représente l'activité du système, pas une
personnalité humaine. **Garder un mode « sans compagnon »** offrant exactement les
mêmes actions — indispensable pour déterminer si le robot est fonctionnellement
utile.

## 4. La surface droite : une meilleure utilisation de l'espace

### 4.1. Apparition selon la valeur de l'information

« C'est vide, donc il faut le remplir » est dangereux : l'espace vide participe à la
concentration. Règle : **ouvrir une surface supplémentaire uniquement quand elle
permet d'agir, de vérifier ou de comparer plus facilement que dans le chat.**

Trois états : **Focus** (chat seul, espace libre) → **Peek** (résultat compact sans
imposer un changement de layout) → **Workspace** (surface ouverte). Le peek est
particulièrement intéressant.

### 4.2. Quand ouvrir, remplir ou fermer

| Événement | Comportement recommandé |
|---|---|
| Réponse conversationnelle simple | Ne rien ouvrir |
| Début de recherche | Statut compact |
| Première source utile | Proposer un accès à l'evidence |
| Plusieurs éléments à comparer | Ouvrir la comparaison si non bloquée par l'utilisateur |
| Exécution de code | Afficher l'activité ; sortie détaillée si elle apporte de la valeur |
| Test en échec | Rendre l'échec accessible immédiatement, priorité supérieure |
| Document généré | Proposer le document éditable |
| Agent en attente d'approbation | Demande claire dans une zone stable |
| Utilisateur épingle une surface | Ne plus la remplacer automatiquement |
| Run terminé | Conserver les résultats ; permettre de replier |
| Nouvelle conversation | Restaurer ou fermer selon la politique utilisateur |

Deux principes : ne jamais confondre **fermeture et destruction** (un panneau peut
disparaître visuellement en conservant état et artefacts) ; pas de disparition
automatique par défaut (si l'utilisateur inspecte une evidence, la fin du run ne
ferme pas le composant).

### 4.3. La surface droite ne doit pas devenir un second chat

Le panneau représente des objets stables que le texte linéaire représente mal :

| Domaine | Ce que l'utilisateur manipule |
|---|---|
| Recherche | Evidence sourcée, extraits, provenance, contradictions |
| Code | Diff, fichiers, tests, stdout/stderr, artefacts |
| Écriture | Texte éditable, historique, suggestions acceptées/rejetées |
| Board | Nœuds, liens, sélections, propriétés |
| Multi-agent | Étapes, délégations, propriétaires des résultats, blocages |

```ts
type Evidence = {
  id: string; runId: string; producerAgentId: string;
  sourceId: string; sourceUrl?: string; retrievedAt?: string;
  claim: string; excerpt?: string;
  verificationStatus: "unverified" | "supported" | "conflicting";
};
```

Le `verificationStatus` doit résulter du pipeline de provenance, pas d'une
affirmation libre de l'agent — éviter qu'un résultat agent soit présenté comme une
preuve vérifiée parce qu'il est dans une belle carte.

### 4.4. Responsive et continuité spatiale

Desktop large : split-view redimensionnable. Viewport intermédiaire : surface unique
bascuable. Mobile : panneau plein écran / drawer / navigation explicite. Seuils
déterminés par les tailles minimales réelles des composants, pas par la seule
classification mobile/tablette/desktop. WCAG 2.2 : reflow sans perte.

Règle : une surface ouverte ne change pas d'identité parce que l'agent change de
sous-tâche — nouvelles informations dans des onglets identifiés, sélection stable.

## 5. Architecture technique et plan d'implémentation

### 5.1. Architecture cible adaptée à notre stack

Ne pas remplacer React, Zustand ou le WebSocket. Construire une couche de gestion
des présentations AU-DESSUS de l'existant :

```
Backend multi-agents + Event Bus
  (text deltas · run events · tool events · artefacts · UI proposals)
    → WebSocket Protocol Adapter (framing · séquencement · validation · reconnexion · compat AG-UI)
    → Event Store (événements · runs · états · artefacts)
    → Workspace Reconciler (policies · focus · permissions · propositions)
    → Zustand (projection de l'état — PAS un bus d'événements supplémentaire)
    → React 18 + TypeScript + Vite + framer-motion (Surface Renderer · Chat · Companion)
```

Flux : `WebSocket → validation → event reducer → état normalisé → reconciler →
renderer`. Les composants React n'interprètent jamais directement les messages du
LLM. L'état durable du run vit côté serveur ; Zustand n'est pas la source de
vérité de l'exécution.

### 5.2. Synchronisation multi-agents : identités et concurrence

```ts
type AgentEvent = {
  eventId: string; sessionId: string; runId: string; agentId: string;
  seq: number; type: string; payload: unknown;
};
```

`seq` : ordre monotone par run (un horodatage ne suffit pas). Stratégie : événements
idempotents (pas de doublon après reconnexion), snapshot + deltas ordonnés,
détection de trous de séquence + resynchronisation, révisions d'état contre les
écritures concurrentes silencieuses, attribution des surfaces à leur producteur
vérifié, reprise de l'inspection d'un artefact après échec WS.

### 5.3. Sécurité : le catalogue est nécessaire mais insuffisant

Une interface déclarative contraint ce que le modèle produit ; elle ne neutralise
pas les injections indirectes (un document de recherche malveillant peut demander au
LLM de créer un composant trompeur ou une action non autorisée — OWASP LLM01).

| Risque | Défense |
|---|---|
| Composant inconnu | Validation stricte, rejet |
| Propriété non autorisée | Schéma fermé |
| Action arbitraire | Registre d'actions + permissions serveur |
| Faux agent privilégié | Identité du bus authentifié, pas du payload |
| HTML/script injecté | Rendu React sûr, Markdown/URL stricts |
| Surface recouvrant des contrôles critiques | Contraintes géométriques du layout engine |
| Trop de composants | Limites de profondeur, volume, fréquence |
| Événement ancien écrasant le nouveau | Révisions + numéros de séquence |
| Fausse confirmation de succès | Statut dérivé du résultat réel de l'outil |
| Exfiltration via URL | Politique d'URL, contrôle des origines |

Jamais un agent ne modifie les permissions, ne masque un contrôle de sécurité, ni ne
génère une demande d'approbation hors du mécanisme d'autorisation du produit. Un
`ApprovalCard` est alimenté par une demande authentifiée par le backend.

### 5.4. Plan incrémental en quatre phases

**Phase 1 — Workspace adaptatif déterministe** (fondations, instrumentation).
`WorkspaceStore`, `SurfaceRegistry`, `WorkspaceReconciler` ; trois états de panneau
(fermé / peek / ouvert). **Pas de LLM dans le choix d'interface à ce stade** —
déclencher sur les événements existants (artefact créé, run lancé, evidence prête).
Testable : stabilité du focus, restauration après rechargement, responsive,
absence de perte d'artefacts, performance. Risque : des transitions qui perturbent
alors même que le choix des surfaces est correct.

**Phase 2 — Templates curés et propositions LLM** (intelligence de présentation).
Templates `research/code/document/board/review` ; schéma de proposition validé,
règles de priorité, mécanisme de refus. **Shadow mode d'abord** : l'agent propose,
l'UI de référence ne change pas ; comparer aux scénarios attendus, puis activer
progressivement ce qui est sûr. Testable : pertinence, stabilité entre tours,
changements évitables, taux de rejet, conformité catalogue. Risque : interpréter
une proposition séduisante comme un besoin réel.

**Phase 3 — État collaboratif et evidence vivante** (avantage fonctionnel).
Snapshots/deltas, identifiants durables d'artefacts, contexte de sélection partagé,
actions frontend autorisées. Ex. : une sélection d'evidence sur le board devient une
référence structurée dans la demande suivante. Cycles de validation :
proposition d'action → approbation → exécution → résultat → trace. Testable :
synchronisation multi-agents, reprise WS, conflits, provenance. Risque : confusion
entre état de présentation, état métier et autorité d'exécution.

**Phase 4 — Compagnon contextuel et orchestration avancée** (différenciation, sous
condition de preuve). Machine à états, **mode ancré d'abord** ; déplacement
contextuel derrière un feature flag. Testable : temps d'accès aux commandes,
interruptions, erreurs de clic, gêne perçue, désactivation volontaire. Risque :
investir dans une signature visuelle dont la contribution fonctionnelle reste faible.

### 5.5. Stratégie de tests

Comparaisons contrôlées : (A) chat + artefacts accessibles manuellement ; (B) chat +
surface contextuelle déterministe ; (C) B + propositions de présentation de l'agent.
Le robot en expérimentation **séparée**.

Métriques prioritaires : temps jusqu'à l'information utile ; taux de complétion ;
actions de navigation évitées ; erreurs de contexte (mauvais artefact/run) ;
changements de layout non souhaités ; perte de focus ; stabilité multi-tour ;
charge subjective.

Scénarios reproductibles : recherche multi-sources, exécution de code en échec,
changement de sub-agent, modification du board pendant un run, reconnexion,
injection malveillante, désactivation des animations. **Chaque scénario inclut
plusieurs tours successifs**, pas une capture finale.

## 6. Évaluation critique de la vision

| Hypothèse produit | Évaluation | Ce qui doit être prouvé |
|---|---|---|
| Le robot donne une sensation de travail vivant | Plausible | La présence améliore-t-elle la compréhension des statuts ? |
| Le déplacement libre rend l'agent plus naturel | **Faiblement étayé** | Réduit-il les interactions, plutôt que de les perturber ? |
| Le template par tâche réduit la friction | Solide, sous conditions | Meilleure continuité sur les tâches hybrides ? |
| Un catalogue contraint améliore la fiabilité | Fortement justifié | Limite-t-il réellement les erreurs et surfaces non désirées ? |
| Le panneau droit contextuel améliore l'efficacité | Prometteur | Accélère-t-il l'inspection et la comparaison ? |
| Un état partagé agent/UI améliore la collaboration | Très prometteur | Évite-t-il références ambiguës et répétitions ? |
| Une UI totalement morphable est toujours supérieure | **Non démontré** | Les gains excèdent-ils le coût de l'instabilité spatiale ? |
| L'interface doit être livrée avec l'agent | Bonne direction | Quelles décisions le modèle doit-il réellement contrôler ? |

**Où se situe l'avantage compétitif** : pas dans l'apparence du compagnon ni dans le
nombre de layouts d'un LLM, mais dans la capacité à rendre un travail d'agent
**immédiatement inspectable, manipulable, vérifiable et reprenable**. Une interface
qui permet de comprendre le processus (agent collecte → artefact → exécution →
erreur → correction → décision) et d'intervenir au bon niveau, sans explorer des
dizaines de messages.

> The interface follows the work, not the agent's imagination.
> The interface ships with the agent — but control stays with the user.

## 7. Bibliographie

### Protocoles et implémentations
- A2UI officiel : https://a2ui.org — Spec v0.9 : https://a2ui.org/specification/v0.9-a2ui/ — v0.9.1 : https://a2ui.org/specification/v0.9.1-a2ui/ — v1.0 candidate : https://a2ui.org/specification/v1.0-a2ui/ — Evolution Guide : https://a2ui.org/specification/v0.9.1-evolution-guide/
- A2UI + A2A Extension : https://github.com/a2ui-project/a2ui/blob/main/specification/v0_9/docs/a2ui_extension_specification.md
- AG-UI : https://github.com/ag-ui-protocol/ag-ui — Events : https://docs.ag-ui.com/concepts/events — State : https://docs.ag-ui.com/concepts/state — Generative UI specs : https://docs.ag-ui.com/concepts/generative-ui-specs
- CopilotKit Generative UI : https://github.com/CopilotKit/generative-ui — Dojo : https://dojo.ag-ui.com/

### OpenAI et Apple
- OpenAI Intelligent UI (7 oct. 2026) : https://openai.com/index/gpt-6-for-everyone/
- OpenAI Generative UI Structured Outputs : https://github.com/openai/openai-structured-outputs-samples/blob/main/generative-ui/README.md
- OpenAI Structured Outputs : https://developers.openai.com/api/docs/guides/structured-outputs
- Canvas : https://openai.com/index/introducing-canvas/ — Apps SDK : https://openai.com/index/introducing-apps-in-chatgpt/
- Apple Materials/Liquid Glass : https://developer.apple.com/design/human-interface-guidelines/materials
- Apple Ornaments : https://developer.apple.com/design/human-interface-guidelines/ornaments
- Apple Spatial Layout : https://developer.apple.com/design/human-interface-guidelines/spatial-layout
- App Intents / Siri : https://developer.apple.com/documentation/appintents/apple-intelligence-and-siri-ai — WWDC26 session 343 : https://developer.apple.com/videos/play/wwdc2026/343/

### Recherche académique
- Chen et al. (2025), Generative Interfaces for Language Models : https://arxiv.org/abs/2508.19227
- Cao, Jiang & Xia (CHI 2025), Generative and Malleable User Interfaces : https://doi.org/10.1145/3706598.3713285
- Peng et al. (2026), Efficient Personalization of Generative User Interfaces : https://arxiv.org/abs/2604.09876
- Imteyaz et al. (2026), Design Theater : https://arxiv.org/abs/2607.22928
- Peng et al. (2026), EvoGenUI-Bench : https://arxiv.org/abs/2608.29387
- Li et al. (2026), When Interfaces Speak : https://arxiv.org/abs/2610.11123
- Cunningham et al. (2026), Context Matters! : https://arxiv.org/abs/2610.21484
- Ma et al. (2026), Beyond Activation : https://arxiv.org/abs/2610.09284
- IEEE ISMAR 2026, Spatial User Interfaces : https://www.ieeeismar.net/2026/papers/
- Rickenberg & Reeves (CHI 2000), The Effects of Animated Characters… : https://doi.org/10.1145/332040.332406
- Horvitz (CHI 1999), Principles of Mixed-Initiative User Interfaces : https://doi.org/10.1145/302979.303030
- Iqbal & Bailey (CHI 2008), Effects of Intelligent Notification Management… : https://doi.org/10.1145/1357054.1357070
- Weiser & Brown (1995), Designing Calm Technology : https://calmtech.com/papers/designing-calm-technology

### Sécurité et accessibilité
- OWASP LLM Prompt Injection : https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- WCAG 2.2 Animation from Interactions : https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions
- WCAG 2.2 Reflow : https://www.w3.org/WAI/WCAG22/Understanding/reflow.html

## Conclusion — décisions recommandées

1. Conserver le WebSocket et le catalogue React existants. Introduire A2UI/AG-UI
   progressivement, sans migration imposée par principe.
2. Construire le reconciler AVANT de laisser un LLM modifier les surfaces.
3. Templates = modes de travail composables, pas six écrans exclusifs.
4. Panneau droit = espace d'artefacts, pas un second flux conversationnel.
5. Reporter le robot mobile à une expérimentation isolée ; un compagnon ancré,
   discret et immédiatement utile est une base plus défendable.

Premier jalon concret : un utilisateur lance une tâche, voit apparaître seulement
les surfaces nécessaires, consulte preuves et sorties en temps réel, modifie le
board, reprend le travail sans perte de contexte ni réorganisation intempestive.
**Si cette expérience fonctionne sans robot, l'essentiel du problème est résolu.**
Le compagnon devient ensuite l'interface incarnée de cette capacité, au lieu
d'essayer de la remplacer.
