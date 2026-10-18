# Hardening pré-merge — livraison web

Date : 2026-10-18. Branche : `fix/web-app-hardening`, basée sur
`feat/web-app-brain` @ `845b54f` (poussée). Aucun merge autorisé.

État : phase en cours, pas une déclaration de préparation au merge. Les
tranches ci-dessous sont couvertes par des régressions déterministes ; les
contrôles produit et les points d'audit encore ouverts restent bloquants.

Validation du jalon : **1 021 tests backend passés**, **47 tests UI passés**,
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
  éventuelle correction partagent 45 s ; anciens chemins sans ProjectSpec,
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

## Audit restant avant la prochaine phase

- Lots 2–6 non clos malgré les régressions de concurrence couvertes. Tester
  les vrais onglets de bout en bout, l'attente au-delà de la durée du buffer,
  le redémarrage serveur et plusieurs plans simultanés dans une conversation
  (le stockage UI reste un run par session).
- Vérifier les collisions de noms/dossiers, symlinks, choix nouveau projet vs
  édition, relance d'un build obsolète, processus/ports, dépendances réseau
  absentes et croissance des logs/output. Ne pas inférer ces garanties des
  seuls tests de planning.
- Étendre l'isolation des tests aux sélecteurs workspace/taskboard et couvrir
  les messages constitués uniquement de pièces jointes, échecs d'upload,
  provider sans vision, pertes réseau et envois interrompus à chaque étape.
- Tester la stabilité des scénarios d'acceptation réellement générés, leur
  lien au contrat approuvé et les révisions concurrentes du même DesignSpec.
- Exécuter la campagne progressive et relever le temps jusqu'au contrat,
  temps de génération/build/tests et qualité fonctionnelle/visuelle du
  résultat. Aucune revendication de campagne produit réussie à ce stade.
