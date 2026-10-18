# Hardening pré-merge — livraison web

Date : 2026-10-18. Branche : `fix/web-app-hardening`, basée sur
`feat/web-app-brain` @ `845b54f` (poussée). Merge autorisé par l'utilisateur
le 18 octobre 2026, après validation du jalon ci-dessous.

État : jalon intégré sur accord utilisateur, sans déclaration de maturité
production. Les tranches ci-dessous sont couvertes par des régressions
déterministes ; les contrôles produit et points d'audit encore ouverts sont
conservés comme travail de suivi, pas déclarés résolus par ce merge.

Validation finale du jalon : **1 066 tests backend passés**, puis **4 tests
preview ciblés passés** (dont un contrôle supplémentaire), **58 tests UI passés**,
build frontend réussi, sans skip/xfail ajouté. Les deux échecs historiques
sont corrigés. Aucune campagne LLM payante/product live revendiquée ici.

## Objectif et limites

Fiabiliser le parcours réel demande → classification LLM → architecture →
contrat approuvé → workers spécialisés → validation → livraison → relance.
Les tests unitaires verts ne suffisent pas : une application navigateur ne
doit pas devenir un script Python après un échec de planification.

Pas de nouveau framework, de morphable UI, de Web Research opaque, ni de
travail sur scratchy v0 dans cette phase. PythonBrain reste spécialisé Python.
Pas de réparation manuelle des exemples utilisateur pour faire passer la démo.
Pas d'appels LLM payants en boucle : campagne live limitée et tracée, utilisant
les modèles configurés ; coût exact inconnu tant que le comptage n'est pas livré.

Signalement utilisateur : préparation du contrat de 30–45 s ou plus. La
latence est un critère transversal : mesurer séparément classification,
architecture, rédaction éventuelle et persistance ; supprimer les appels
redondants, afficher l'étape effective et borner chaque attente. Un timeout
clair n'est pas une livraison réussie. La réduction des appels ne prouve pas
encore un gain de latence en conditions réelles : campagne chronométrée requise.

## Lots et critères de sortie

1. **Routage et planification — en cours.** Classification structurée par le
   LLM (aucun keyword matching), `web_app` conservé jusqu'au ProjectSpec et
   aux actions WebAppBrain, y compris quand le LLM répond mode=script.
   JSON invalide, timeout, provider indisponible, architecte invalide ou
   livrable contradictoire : réparation de structure bornée si applicable,
   sinon échec explicite, aucun contrat/codage/passage Python par défaut.
   Les actions directes explicitement typées conservent leur routage natif.
2. **Contrats et projets.** Un contrat présente stack, destination réelle,
   entrée et validation ; nouveau projet distinct d'un ancien Blender,
   modification isolée du bon projet, chemins/symlinks/traversée/collision
   vérifiés. Contrat rejeté ou modifié : aucune écriture non approuvée.
3. **Cycle de vie et sessions.** Stop pendant classification, architecture,
   attente d'approbation, génération, npm/build, navigateur et réparation.
   Changement de page, reload, reconnexion et deuxième onglet : aucun run,
   texte ou contrat attribué à une autre conversation ; un seul résultat final.
   Réexécution sans duplication ; fin effective des processus et charge libérée.
4. **Workers, builds et preuves.** Exceptions, sorties incomplètes, imports
   incohérents, dépendance absente, erreur TS/build/JS/HTTP, navigateur absent,
   test échoué, délai dépassé : échec ou inconclusif réel. Maximum deux
   réparations, scénarios approuvés figés, logs/captures reliés à chaque
   tentative. Pas de métadonnées runnable héritées d'un ancien projet.
5. **Parcours UI.** Progrès visible dès l'envoi, attente compréhensible,
   contrats restaurés sans résurrection, docking à la fin, Preview/Open/Run
   accessibles, console visible après Run, autoscroll et erreurs lisibles.
   Aucune donnée factice ; contrôles uniquement adossés à un état réel.
6. **Campagne produit progressive.** Vraies applications indépendantes :
   compteur persistant ; todo avec filtres/édition ; apprentissage React
   sur quatre semaines avec notes/progression ; planning fitness avec
   contraintes et historique ; projet plus riche avec plusieurs vues/modules.
   Pour chaque essai : demande exacte, modèles, contrat, destination, run ids,
   verdicts, erreurs, captures, observations UX et relance après reload.
   Ajouter CLI Python témoin et modification d'une app existante pour vérifier
   les frontières. Scénarios déterministes d'injection de panne séparés des
   essais LLM réels : ne jamais présenter les premiers comme les seconds.

## Porte de merge

- Chaque lot a des preuves vérifiables et les anomalies bloquantes sont closes.
- Tests backend complets, tests UI et build passent ; les deux échecs historiques
  doivent être caractérisés/isolés, pas masqués. Toute nouvelle régression bloque.
- Campagne réelle validée par l'utilisateur, y compris le cas React mal routé.
- Docs et roadmap reflètent le réalisé, les limites et ce qui reste ouvert.
- Secrets, mémoire runtime et artefacts personnels exclus des commits.
- Push de la branche de hardening puis merge uniquement sur accord explicite.

## Journal

- Préparation : revue du chemin générique. Le classificateur émet
  `deliverable_type`, mais l'orchestrateur l'ignore ; architecture défaillante
  → planificateur legacy systématiquement Python ; erreur générale → routage
  Python par défaut. Ces trois chemins sont les premières régressions à couvrir.
- Première tranche implémentée : décision web préservée jusqu'au worker,
  petite app incluse ; classification stricte, pas de repli générique Python ;
  architecture avec une seule correction structurelle au maximum, sans
  changement de livrable. Le vieux planificateur reste présent comme code de
  compatibilité, mais n'est plus appelé par ce parcours. Erreur de préparation
  → un échec terminal explicite, aucun contrat ni dispatch worker.
- Architecture : graphes cycliques, dépendances absentes, doublons de fichiers
  et chemins dangereux refusés avant le contrat. Les critères d'acceptation
  viennent de l'appel architecte : parcours projet nominal = deux appels LLM
  après l'acquittement front (classification + architecture), sans troisième
  appel de rédaction. Délai maximal classification 20 s ; architecture et son
  éventuelle correction partageaient initialement 45 s (corrigé ci-dessous) ; anciens chemins sans ProjectSpec,
  rédaction bornée à 20 s et 768 tokens. Ce sont des plafonds d'attente, pas
  des objectifs de latence. Événements `planning.stage` chronométrés, montrés
  dans le panneau d'activité et conservés dans les logs du bus.
- Approbation : mauvais design, valeur non booléenne, décision périmée,
  preuve absente ou écriture impossible ne débloquent pas le plan. Double
  approbation = un seul dispatch. Rejet puis approbation et contrat reçu
  après Stop ne relancent pas le travail. Une demande répétée avec des
  critères différents crée une révision au lieu de recycler l'ancien contrat.
  L'UI attend le verdict du bus, pas seulement un HTTP 200, et conserve la
  carte avec erreur réessayable ; une réponse HTTP tardive ne touche pas une
  proposition plus récente.
- Tests historiques : test d'upstream context exécuté dans une vraie fixture
  asyncio (au lieu de supposer une boucle globale Python 3.13) ; test de
  parallélisme à barrière trois workers, plus strict sur la concurrence que
  le précédent seuil 250 ms sensible aux fsync/logs. Aucun xfail/skip ajouté.
- Validation initiale : 14 régressions reproduites sur la baseline avant
  correction. 137 tests ciblés passent après cette tranche ; suite complète,
  UI et build en validation finale. Ce sont des tests déterministes, pas une
  campagne de génération LLM réelle.

### Deuxième tranche — concurrence et isolation

- Stop web cible explicitement une session : seules ses livraisons chat,
  ses plans et leurs dispatchs workers sont annulés. Stop sans session ne
  signifie plus annulation globale ; le contrôle système global reste interne.
- Contexte front brain local à chaque coroutine : texte, deltas, fin de
  streaming et délégation restent dans leur session lors de réponses entrelacées.
  Les tours de la même conversation sont sérialisés, avec historique relu
  après la réponse précédente, même s'ils viennent de deux onglets.
  Le verrou est libéré après la réponse acquittée et persistée, identifiée
  par `turn_id`, pas après la planification déléguée : le chat reste disponible
  pendant la préparation du contrat. Enfants asyncio et événements d'attente
  nettoyés aussi sur annulation.
- Sans identifiant explicite, scope du socket, jamais du dernier onglet actif.
  Un socket neuf ne reçoit pas implicitement un autre historique ; reconnexion
  de l'adapter avec demande explicite de sa session.
- Runs et propositions conservés par conversation dans l'UI et persistés.
  Fin de A sans écrasement de B ; progression, fichiers et evidence workers
  portent session/plan/subtask. Replay et supersede ciblés par plan/sous-tâche,
  pas seulement par source orchestrateur.
- Course Stop après `subtask.started` mais avant livraison bus : aucun code
  dispatché, charge et suivi libérés. Stop pendant création de session ou
  upload bloque l'envoi différé, sans cibler l'ancienne conversation.
- `BIGBRAIN_MEMORY_DIR` isole aussi ProjectMemory, LongTermMemory et les
  learnings orchestrateur. Tests avec sentinelles ; chemins explicites
  prioritaires, comportement runtime inchangé si la variable est absente.
  Les fichiers mémoire déjà sales ne sont ni restaurés ni supprimés pour
  ne pas écraser un état utilisateur mélangé à l'ancien état de test.
- Un plan perdu au redémarrage produit une erreur d'approbation visible,
  sans reprise non approuvée. Ce n'est pas une restauration des plans.

### Retour live — timeout architecte du running tracker

- Le bus du 18 octobre confirme : classification `web_app` correcte en
  3 249 ms, puis interruption de l'architecture après 45 s. Aucun contrat ni
  dispatch worker sur cet essai. La configuration des rôles indique Sol 6.1
  via OpenRouter ; les logs ne permettent pas de distinguer temps de réflexion,
  génération et transport, ni de prouver quelle part explique la lenteur.
- Le prompt web ne réutilise plus le schéma exhaustif illustré par models.py
  et auth.py : schéma navigateur compact, interfaces TypeScript dans les notes,
  comportements et cas limites conservés, fichiers toolchain détenus par le
  serveur. Cible de sortie < 2 500 tokens, plafond 4 096 au lieu de 8 192 ;
  aucun gain de latence live revendiqué avant nouvel essai.
- Un seul budget total architecte, réparation comprise : 120 s par défaut,
  configurable via `BIGBRAIN_ARCHITECT_TIMEOUT_SECONDS` (5–300 s, valeur invalide
  → défaut sûr). Suppression des deux coupures concurrentes à 45 s. Pas de
  relance automatique sur timeout ; annulation de l'appel et erreur explicite,
  aucun plan partiel exécuté ni repli Python.
- Toutes les 5 s d'attente, événement de durée réellement écoulée, scoped à
  la conversation ; durée visible dans le panneau replié et développé. Ce
  signal signifie « appel toujours en attente », pas « modèle en progression ».
  Stop annule et attend le nettoyage de la tâche architecte enfant.
- Régressions déterministes : configuration invalide, budget unique partagé
  avec une réparation, timeout provider sans retry, schéma web, attente suivie
  de succès et attente suivie de Stop. La demande running réelle reste à
  retester par l'interface ; aucune application d'exemple réparée manuellement.
- Validation : suite complète **1 037 passés** ; après ajout du cas de timeout
  HTTP natif et derniers ajustements, **39 tests ciblés passés** (dont 17 sur
  la latence). **49 tests UI passés**, build frontend réussi. Les avertissements
  de dépréciation backend et de taille du bundle restent non bloquants.

### Retour live — mémoire, activités concurrentes et rechargement

- Diagnostic sur les vraies traces : le projet running est annoncé terminé
  et son dossier `workspace/sandbox/running-planner` existe, également listé
  par l'API workspace. La tâche taskboard a remplacé son unique run UI ;
  sa fin a hérité du manifeste Blender sélectionné. Ce n'était pas une
  absence totale de génération. Aucun exemple utilisateur corrigé à la main.
- L'historique et le titre correct existent dans SessionStore. Le client
  demandait le catch-up sans l'exploiter dans App, et relisait un ancien
  transcript localStorage global. Restauration par session maintenant branchée,
  titre rafraîchi après réponse, erreurs d'historique visibles et attente bornée.
  Les messages arrivés pendant le chargement sont conservés ; réponse tardive
  d'une autre conversation ignorée.
- Corrélation UUID depuis `task.routing` jusqu'au plan/worker/terminal.
  Stockage UI par run, sélection compacte parmi les activités d'une même
  conversation : une tâche secondaire ne remplace ni ne termine le projet.
  Fin de worker ne termine plus une réponse indépendante du front brain.
  Stop annule les activités de la conversation ciblée ; ce bouton peut donc
  rester disponible pendant que le front brain répond à autre chose.
- Les événements fsync du bus servent de source durable de restauration,
  indépendante du replay 5 min/100 messages : `chat.history` renvoie les
  derniers états par étape/fichier de 100 runs terminés et des runs ouverts.
  IDs, timestamps et métadonnées conservés ; cache de routage pré-UUID migré ;
  replay idempotent sans duplication de cartes. Plan ouvert d'un ancien
  processus marqué interrompu, jamais repris sans autorité. Lecture du journal
  hors boucle asyncio ; indexation incrémentale à envisager avant production.
- Résultat taskboard : type explicite et raccourci Taskboard. Aucun Open/Run
  ni preview d'un projet sélectionné sans rapport ; protection aussi pour les
  anciennes cartes via le brain de leurs étapes. Les vraies modifications
  mono-fichier conservent leurs actions projet grâce aux résultats fichiers.
- Suivi discret hors chat : une ligne permettant de revenir au travail en
  cours. Dans le chat, étapes réelles génération/build/tests/correction/preview
  reçues des messages PROGRESS (auparavant non consommés), sans pourcentages
  inventés. Ce n'est pas la future morphable UI ni une surface latérale neuve.
- Mémoire : audit en lecture seule puis requête sur une copie isolée de la
  vraie Chroma. Le nom existe ; questions répétées et ancienne réponse
  d'ignorance occupaient le top-4, le fait utilisateur arrivait au rang 7.
  Désormais 24 candidats, déduplication avant sélection, place réservée aux
  propos utilisateur et provenance conservée ; injection toujours limitée à
  quatre éléments de 200 caractères. Aucun appel LLM de plus. Vérification sur
  la copie réelle : le nom est retrouvé. Cela ne garantit pas le rappel de
  tout fait ancien ; une mémoire structurée reste un chantier ultérieur.
- Test Chromium reproductible : `.venv/bin/python -m tools.check_ui_lifecycle`
  après build UI. Serveur réel + UI compilée, données/événements de test isolés,
  aucun LLM ni probe fournisseur externe. Historique sans cache, web + taskboard,
  navigation Workspace/retour, reload, deux onglets, docking et absence d'erreur
  JavaScript vérifiés. Ce n'est pas une campagne de projets générés en live.
- Validation de cette tranche : **1 044 tests backend passés**, **57 tests UI
  passés**, build réussi ; scénario Chromium ci-dessus réussi. Pas de skip
  ajouté. Les mémoires runtime déjà modifiées restent hors des changements
  à publier ; elles ne sont ni restaurées ni supprimées.

### Séparation structurelle navigation / exécution

- La sélection `current_project.json` reste un état de navigation. Son hook
  ne change plus aucun `work_dir` de worker, même pendant un run. Le client
  transmet sa navigation par tour (`navigationProject`) ; le front ne relit
  plus une sélection globale pour construire sa réponse ou sa délégation.
- Le LLM déclare `project_target`: `new` (chemin optionnel) ou `existing`
  (chemin obligatoire). Sans déclaration, une création d'après architecture
  possède son dossier descriptif `sandbox/<project_name>` ; un script isolé
  son dossier `sandbox/run-<id>`. Une modification/exécution existante ambiguë
  échoue explicitement, jamais de reprise implicite du projet sélectionné.
  Compatibilité : un `project_path` explicitement fourni par un appel interne
  reste une cible existante, mais n'est plus enrichi depuis la navigation.
- `ExecutionTarget` immutable, attaché au TaskPlan avant le contrat : mode,
  chemin et racine figés. La destination est montrée dans une ligne dédiée
  du contrat et inscrite dans les métadonnées du DesignSpec immutable.
  Nouvelle cible ou autre destination → pas de recyclage d'un ancien contrat
  identique par son seul texte. Approbation vérifie la correspondance exacte.
- Le dossier d'une création est réservé exclusivement après approbation,
  avant dispatch. Collision → refus, sans transformer `new` en édition.
  Existant → manifeste obligatoire et identité du dossier épinglée ; liens
  symboliques, traversées et remplacement de dossier refusés lors des contrôles.
- Les messages aux outils fichiers portent le contexte protégé du run,
  injecté par l'orchestrateur, et non un chemin produit librement par le LLM.
  Python et Web utilisent un ContextVar par tâche : réutiliser un worker ou
  changer sa valeur par défaut ne déplace pas un appel déjà en cours.
  Les fichiers projet ne sont pas imbriqués une seconde fois sous son nom.
- Les métadonnées de livraison ne peuvent plus provenir d'un manifeste
  sélectionné sans lien : sans cible de run, pas de contrôles projet.
  Checkpoint et résultat se réfèrent au dossier lié au plan. Le ProjectSpec
  architecte est désormais conservé sur son propre plan, pas dans un cache
  partagé qui pouvait mélanger des architectures concurrentes.
- Tests : Python/Web en attente du provider pendant un changement de
  sélection, worker Python réutilisé pour deux dossiers, collisions, chemins
  dangereux, symlinks, remplacement de dossier, preuve du contrat et absence
  d'écriture avant approbation. Vrai bus + approbation + PythonBrain batch :
  seul le dossier approuvé reçoit le fichier, Blender reste inchangé.
- Limite explicite : c'est l'isolation de destination des outils intégrés,
  pas un sandbox OS. Un programme Python exécuté garde les permissions du
  processus ; une isolation de sécurité plus forte nécessite un autre travail.
  Plusieurs contrats simultanés par conversation restent à traiter.
- Validation : **1 063 tests backend passés**, **58 UI passés**, build réussi,
  scénario Chromium reload/navigation/deux onglets réussi. Contrôle F821 sans
  erreur ; trois variables inutilisées préexistantes demeurent hors de cette
  tranche. Aucun merge ni réparation d'un projet utilisateur.

## Audit restant avant la prochaine phase

- Lots 2–6 non clos malgré les régressions de concurrence et le parcours
  Chromium maintenant couverts. Approfondir redémarrage en plein build/test,
  pertes réseau et plusieurs projets/architectures/contrats simultanés :
  le stockage des propositions reste une proposition par conversation,
  contrairement aux runs désormais indépendants. Ne pas confondre restauration
  du suivi avec reprise de l'exécution après redémarrage.
- Vérifier les collisions de noms/dossiers, symlinks, choix nouveau projet vs
  édition, relance d'un build obsolète, processus/ports, dépendances réseau
  absentes et croissance des logs/output. Ne pas inférer ces garanties des
  seuls tests de planning.
- Isolation des sélecteurs workspace/navigation/taskboard désormais assurée
  par conftest ; maintenir cette frontière et couvrir
  les messages constitués uniquement de pièces jointes, échecs d'upload,
  provider sans vision, pertes réseau et envois interrompus à chaque étape.
- Tester la stabilité des scénarios d'acceptation réellement générés, leur
  lien au contrat approuvé et les révisions concurrentes du même DesignSpec.
- Exécuter la campagne progressive et relever le temps jusqu'au contrat,
  temps de génération/build/tests et qualité fonctionnelle/visuelle du
  résultat. Aucune revendication de campagne produit réussie à ce stade.

### Previews liées aux surfaces visibles (18 octobre 2026)

- L'URL/port d'un ancien résultat n'est plus une adresse durable : le chat
  réacquiert la preview à partir du projet vérifié, y compris après restart.
- Workspace : ouverture seulement sur Preview, fermeture sur Code, changement
  de fichier ou sortie de la surface. Chat : ouverture avec la carte web visible
  dans la conversation montée, fermeture en quittant celle-ci.
- Baux indépendants partagés par projet, renouvelés toutes les 15 s ; dernier
  départ ferme le serveur. Onglet masqué/page quittée : libération ; crash ou
  perte réseau : expiration après 45 s, balayage toutes les 10 s.
- Serveurs aiohttp loopback sur ports disponibles attribués par projet, liés au processus
  principal (pas de sous-processus UI orphelin). Aucun build/génération implicite.
  Validation du manifeste et du build React existant ; fichiers cachés,
  node_modules et sorties du dossier refusés. Origin séparée du serveur UI.
- Attribution durable workspace/.preview-ports.json : même origine lors des
  réouvertures/restarts pour conserver localStorage. L'attribution n'ouvre aucun
  port à elle seule. Port déjà attribué occupé ou registre invalide : erreur
  explicite, pas de rotation silencieuse qui masquerait les données stockées.
  Les données des anciennes origines :3200 ne sont pas migrées automatiquement.
- Le serveur temporaire utilisé par le gate navigateur est fermé à la fin du
  gate, pas conservé comme serveur utilisateur. /fs/run ne démarre plus de
  preview persistante ; les surfaces utilisent /fs/preview.
- Un onglet externe d'aperçu dépend de la surface qui l'a ouvert ; pas de bail
  autonome pour cette page générée. À expliciter/améliorer en UX ultérieure.
- Vérifications locales : suite backend 1066 passée (9 warnings), puis 4 tests
  preview ciblés repassés dont un contrôle supplémentaire du registre ;
  58 tests UI et build réussis ; contrôle Chromium
  sur UI compilée/serveur réel isolé : rechargement avec ancien port périmé,
  acquisition réelle, fermeture en quittant le chat, Preview workspace seulement
  au clic, fermeture au retour Code, aucune erreur JS. Fixtures déterministes,
  pas une campagne de génération LLM. Tests serveur : partage/dernier départ,
  expiration, arrêt, restart avec origine stable, origines distinctes et
  registre corrompu refusé ; builds React et gate navigateur réels vérifiés.

### Roadmap validée : taskboard comme hub de travail délégué

À concevoir dans une phase dédiée, non implémenté par le correctif previews.
Le board ne doit pas devenir une liste de corvées supplémentaires : les agents
peuvent proposer une organisation, décomposer et exécuter les tâches compatibles
avec leurs capacités. L'utilisateur arbitre et vérifie les résultats.

Autre évolution demandée pour une prochaine branche : renommer et supprimer
les conversations depuis l'historique. Réutiliser les opérations serveur
disponibles, confirmer la suppression et définir le traitement d'une
conversation avec runs actifs ; synchroniser titre/suppression entre onglets,
session active, historique persistant et surfaces dockées. Ne pas assimiler
suppression de conversation et suppression des projets/fichiers générés.

À la reprise après reset d'usage : repartir du main fusionné et synchronisé,
créer une nouvelle branche pour le périmètre choisi. Ne pas rouvrir une
ancienne branche de ce cycle ; nettoyage des branches intégrées au handoff.

- États proposés : à clarifier, proposé/à autoriser, prêt, en cours, bloqué,
  à vérifier, validé (et annulé). Résultat agent ≠ validation utilisateur.
- Chaque tâche garde projet/cible immuable, brain responsable, dépendances,
  critères d'acceptation, run, preuves, livrables et historique d'actions.
- Pas d'auto-exécution générale à l'ajout : autorisation explicite ou politique
  préapprouvée, budgets/coûts, contrôle des actions externes et destructives.
- Réorganisation suggérée par les agents, explicable et réversible ; ne pas
  changer silencieusement priorités, échéances ou engagement de l'utilisateur.
- Vue compacte centrée sur « À vérifier » et les vrais blocages, avec suivi
  détaillé à la demande ; cohérence multi-onglets, annulation et reprise.
- Fondations orchestrateur/observabilité d'abord ; intégration morphable UI
  ensuite. Distinguer WebAppBrain (produire une app) et ResearchBrain (enquêter).
