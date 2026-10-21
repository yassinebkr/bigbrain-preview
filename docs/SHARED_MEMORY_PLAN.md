# Mémoire partagée et modification fiable — état local

## Clôture du lot et transition maintenance — 21/10

L'utilisateur autorise le merge du lot complet après contrôle des régressions,
puis une nouvelle branche `feat/project-maintenance` depuis main. Ne plus
développer sur `feat/shared-memory` après cette clôture.

Contrôle pré-merge effectué le 21/10 : 1158 tests Python réussis, 9 warnings
(155,18 s), 101 tests UI réussis et build Vite réussi. Warnings de chunks et
imports dynamiques UI conservés ; aucun assouplissement de test pour ce contrôle.

Ce lot livre les mécanismes de mémoire partagée, suivi UI et gates, **pas une
capacité de réparation de projets validée en conditions réelles**. La dernière
tentative G-code a échoué : tests prescriptifs sur la formulation, périmètre
approuvé sans implémentation modifiable, réparation au-delà du budget de sources
et revue sémantique inconclusive au-delà de son propre budget. Rollback confirmé
sans conflit. Les tests internes ne remplacent pas cette validation réelle.

La prochaine phase introduit une enquête progressive portée par le spécialiste,
un périmètre approuvé au niveau du projet, des patches révisionnés et une boucle
diagnostic/correction/vérification. Création et maintenance restent distinctes ;
les tests/contrats ne sont pas affaiblis et PythonBrain ne devient pas WebAppBrain.

Publication demandée le 21/10 : commit et push de `feat/shared-memory` pour
validation utilisateur. Aucun merge autorisé avant cette validation. Données
mémoire d'exécution et `uv.lock` hors périmètre du commit.

## Gates de livraison — état local du 21/10

Accord utilisateur : traiter les trois limites restantes, sans nouvelle repasse UI.

- **Environnement** : l'assemblage Python et pytest utilisent le même interpréteur de
  projet. Le diagnostic initial vise `.venv/bin/python` ; venv/pytest absent =
  inconclusif, jamais repli sur le Python de BigBrain. Lors de l'assemblage, le
  runner provisionne l'outil déclaré `pytest>=8,<10` dans ce venv si nécessaire ;
  échec d'installation = inconclusif, pas une réparation métier par le LLM.
  Le préfixe réel du venv est contrôlé ; un faux `.venv/bin/python` pointant sur
  le Python hôte ne peut ni fournir une preuve valide ni recevoir un pip install.
  La preuve inclut executable/prefix/version réellement interrogés. Les checks
  statiques AST/compile restent ceux du runtime (ce n'est pas une matrice de
  compatibilité de toutes les versions Python).
- **Rollback** : les modifications de projets existants ont un journal persistant
  privé sous `workspace/.bigbrain-transactions/`. Écritures bornées au périmètre
  approuvé + manifeste ; comparaison avant écriture ; commit après vérification.
  Échec = restauration des écritures BigBrain, créations retirées, ancien manifeste
  restauré. Stop : fencing des écritures, arrêt des workers/processus, restauration.
  Worker tardif refusé. Modification utilisateur concurrente = conservée, conflit
  explicite et nouveau run bloqué jusqu'à récupération. Pas de restauration tar
  globale ni de suppression récursive de projet. Journaux/sauvegardes conservés.
  Source : reprise d'un propriétaire disparu au prochain run si sans conflit.
  Build interrompu par crash : récupération explicite (enfants orphelins possibles).
- **Web** : ancien `dist` retenu par renommage ; build échoué retenu lui aussi,
  puis ancien build restauré. Empreinte du build validé contrôlée au commit.
  Les scaffolds conservés ne sont plus réécrits pendant un build ; un changement
  d'outillage demande une migration explicite. Preview refusée sur transaction
  ouverte/en conflit. Les caches, installations de dépendances et effets
  arbitraires de programmes hors des écritures contrôlées ne sont pas annulés :
  ce n'est ni isolation de processus ni transaction générale du système de fichiers.
- **Métier** : revue indépendante du contexte de génération, un appel LLM borné
  supplémentaire après réussite des tests. Chaque critère approuvé doit être relié
  à un ou plusieurs identifiants de tests réellement passés, avec justification
  issue des assertions et du code. Identifiants issus de hooks structurés pytest
  dans un rapport séparé, pas d'analyse des lignes PASSED/FAILED de stdout : les
  programmes peuvent imprimer de tels messages sans forger la preuve. Référence
  inventée, critère absent, contradiction,
  incertitude, fournisseur indisponible ou budget dépassé = inconclusif bloquant,
  sans réparation automatique destinée à faire disparaître l'arbitrage. Python
  et navigateur enregistrent cette étape dans Evidence ; contrat épinglé à sa
  révision approuvée. Python revérifie aussi la révision des sources autour de la
  revue. Une revue LLM n'est **pas une preuve exhaustive de vérité métier** : des
  oracles/références de domaine indépendants restent nécessaires pour du critique.
- **Routes natives** : l'édition mono-fichier conserve son action choisie par le
  LLM, mais ajoute une validation du projet avant livraison/commit. Manifeste
  d'entrée absent : demander un plan architecte de récupération, pas deviner.
  Une bibliothèque explicitement non exécutable passe aussi tests/revue ; seule
  l'exécution d'un point d'entrée est marquée non applicable, sans exit code fictif.

Tests réels isolés : dépendance uniquement dans le venv projet, pytest absent sans
fallback, patches/assemblage/gate/revue/commit de bout en bout, échec d'assemblage
avec restauration de sources/manifeste, conflit utilisateur, reprise du journal,
Stop avant restauration, échec React avec ancien `dist` restauré, faux identifiants
de tests refusés, revue signalant des tests vacuement verts bloquante, preview
d'une transaction bloquée.
Fournisseurs déterministes pour ces tests ; aucun appel LLM payant ni modification
manuelle du G-code réel. Validation : suite complète **1157 réussites / 9 warnings**
(151,44 s), puis **66 tests ciblés réussis** (15,50 s) après le dernier verrou
de préfixe du venv ; le fichier delivery_gates contient 24 cas. Diff sans erreurs
d'espaces. Merge en attente de validation utilisateur. Ces tests valident les mécanismes avec fournisseurs
déterministes, pas l'exactitude d'un modèle réel sur tous les domaines.

## Audit causal et durcissement du pipeline — 20/10, après 20:59

Historique du lot précédent ; ses trois limites ci-dessous sont remplacées par
les gates et le périmètre explicite de la section du 21/10.

Tentative analysée : `b28fb32d-8a65-4774-9b64-a78bdc21f144`, preuve
`run-32f7339111c3497e81d91a6ace884260`. Six patches, pas six fichiers neufs.
Entrée exécutée ; trois fonctions de test échouent (cinq échecs avec sous-tests).
Causes établies : enveloppe bus `{success,data}` non extraite par l'orchestrateur,
donc dépendances nouvellement produites ignorées au profit du snapshot initial ;
compaction susceptible de supprimer les sources ; pas de bilan de tests initial ;
attentes contradictoires entre workers ; diagnostic réduit aux 2000 derniers
caractères ; réparation refusée par le budget global de 120000 caractères.
L'ancien test M82/G91 exigeait un comportement contraire au code officiel Klipper.

Correctifs locaux, dans l'ordre demandé :

1. Normalisation unique des résultats reçus et des références historiques ;
   échec transport/interne jamais converti en réussite. Sources non compactées.
2. Diagnostic initial Python avant architecture : syntaxe, tests réels (30 s),
   échecs et hashes des sources ; pas de lancement arbitraire de l'entrée.
   La lecture reste sans exécution ; **le diagnostic est une étape distincte
   qui exécute les tests**, donc pas une garantie d'absence d'effets de bord.
   Environnement minimal, sans secrets hérités ; stdin fermé, cache pytest et
   bytecode désactivés. Ce n'est pas un sandbox OS. Modification d'une source
   inspectée pendant le diagnostic = arrêt et nouvelle inspection nécessaire.
3. Workers aval : nouvelle source upstream prioritaire ; hashes de dépendances
   vérifiés avant et après l'appel LLM, versions consommées dans le résultat.
4. Modifier des tests existants exige une décision structurée (chemin, raison,
   comportement, fondement), ajoutée au contrat soumis à l'utilisateur. Une
   contradiction déclarée non résolue arrête la planification sans retry LLM
   susceptible de l'effacer. Pas de garantie de détection sémantique exhaustive :
   une justification LLM n'est pas une preuve indépendante d'exactitude métier.
5. Réparation : critères réellement proposés/approuvés, bilan initial, diagnostics
   de tests jusqu'à 64000 caractères avec troncature explicite et cas échoués ;
   conservation comme artefact de preuve. Budget des seules sources Python,
   tests inclus et non modifiables dans la réparation automatique. Révision du
   contrat approuvé épinglée pour le gate, pas sélection aveugle de la dernière.

Tests dédiés : réception réelle d'enveloppe puis worker dépendant, refus d'une
dépendance modifiée pendant le LLM, conservation des sources lors de compaction,
bilan initial échoué, arbitrage obligatoire des changements de tests, contrat et
premier échec transmis à la réparation, gate épinglé malgré une proposition plus
récente. Aucun changement manuel au projet G-code ni appel LLM payant.
Validation finale (nuit du 20 au 21/10) : **1134 tests réussis**, 9 warnings,
139,89 s. Les 85 tests ciblés contrats/gate/compaction/pipeline passent aussi.
Le premier passage complet avait identifié l'ancienne attente qui exigeait
de supprimer les sources à la compaction ; ce test a été remplacé par leur
conservation exacte, puis la suite complète a été relancée avec succès.
`git diff --check` propre. UI inchangée, aucun push/merge de ce lot.
Limites : pas de transaction/rollback multi-fichiers, ni mapping exécutable exhaustif
de chaque critère à un test ; les routes natives mono-action gardent leur périmètre
et ne deviennent pas automatiquement une campagne de validation complète.
Le diagnostic pytest utilise encore le Python du runtime BigBrain, comme le gate
actuel, et non systématiquement le venv du projet : les dépendances tierces et
les écarts d'environnement restent à traiter explicitement. Les scénarios validés
ici ne prouvent pas la réussite future d'un modèle réel sur tout projet.

## Lot approuvé — modification fiable, design gelé

Accord utilisateur du 20/10 : inspection des sources/tests du seul projet ciblé
et transmission bornée au modèle configuré autorisées pour planifier/réparer.
Contrats avant modification : lecture sans liens symboliques ni fichiers sensibles
connus, puis diagnostic de tests avant approbation (voir distinction ci-dessus) ; limites et
omissions explicites. Le plan distingue conserver/modifier/créer. Les fichiers
conservés ne sont pas régénérés ; les modifications utilisent des fragments
exacts, sans repli silencieux vers une réécriture. Changement concurrent depuis
l'inspection = arrêt, pas d'écrasement. Les sources ne remplissent pas le contexte
du front à chaque tour. Acceptation : plusieurs petits projets Python et web,
préservation octet pour octet des fichiers non ciblés, refus des modifications
non inspectées/tronquées et des patches invalides, tests réels après modification.
Pas de nouvelle repasse esthétique ni modification manuelle du projet G-code.

Implémenté localement : inspection Linux no-follow par descripteurs, 64 fichiers,
48 kB/fichier, 128 kB au total ; inventaire/statuts/hashes et exclusions explicites.
Sources fournies à l'architecte comme données, pas au front par tour. La cible
reste épinglée en inode. Conserver ne crée aucun worker ; modifier exige un
patch JSON de fragments uniques et les hashes de base sont revérifiés après
l'appel LLM. Création refuse une collision apparue entre-temps. Les chemins
directs edit_file gardent leur routage natif mais reçoivent l'inspection et ne
passent plus par la réécriture de secours. Le contrat énumère les changements
et conserve l'inventaire/hashes, sans persister les sources dans son metadata.
Les critères approuvés sont transmis aussi aux générateurs de fichiers/tests.

Réparation automatique Python limitée aux fichiers modifiables du plan approuvé,
avec raisons de refus explicites dans le journal. Pour un projet web existant,
un échec navigateur réclame une nouvelle réparation ciblée ; l'ancien remplacement
automatique de fichiers complets est interdit. Ceci est une limite explicite du
lot, pas une boucle autonome complète de réparation web. Les garde-fous ne sont
ni un sandbox OS ni une preuve de cohérence sémantique de tous les tests. Pas
encore de campagne LLM réelle ou de lecture sélective au-delà du budget ; un
grand projet incompletement lu doit être traité comme tel, jamais comme inspecté.
Le filtrage des secrets connus n'est pas une garantie d'absence de secrets.
Les fichiers conservés sont aussi revérifiés avant chaque worker/assemblage.
Une nouvelle empreinte d'inspection impose une nouvelle révision du contrat.
Ce n'est pas une transaction multi-fichiers : si une étape ultérieure échoue,
les modifications déjà effectuées restent visibles et le run est en échec.

Campagnes : todo Python, calcul statistique Python (exécutés), widget JavaScript
avec clic/résultat dans Chromium, puis projet Python multifichier via plan,
patch et gate réel. Entrée/tests/docs conservés octet pour octet. Inspection
du G-code réel : 7 sources/tests, 105453 octets, aucune troncature, lecture seule.
Les fournisseurs de tests sont déterministes ; aucun appel LLM payant exécuté.
Validation : suite complète 1125 réussites / 9 warnings (140 s), puis ajout du
dernier test de révision d'inspection et 34 tests ciblés modification/contrats
réussis. Le nouveau fichier compte 18 cas. Un test WebSocket à attente fixe de
50 ms a échoué lors d'un premier passage chargé, puis réussi seul et dans les
passes complètes suivantes ; test non assoupli. UI inchangée dans ce lot.

## Tentative suivante et Atelier — 20/10, 15:25–15:34

Run `d1b354bb-35cc-4dcf-936d-da17f2921726`, preuve
`run-08ef39bb6a1e47d5bec9b5c81a0746c6` : écrit gcode_analyzer.py, main.py,
tests/test_gcode_analyzer.py et README.md. Anciens gcode.py/analysis.py et
tests/test_analysis.py conservés. Le pipeline de génération par fichier a donc
effectué une reconstruction parallèle, pas une réparation minimale prouvée.
Exécution de main.py réussie ; gate = 41 tests réussis / 9 échecs. Les tests
nouveaux exigent `--json`, absent du CLI généré, et un échec sans argument,
contraire au contrat approuvé de démonstration sans argument réussie. D'autres
échecs concernent G92, mouvements relatifs et températures : non qualifiés tous
individuellement à partir de la seule sortie de preuve, tronquée à 2000 chars.
Une tentative de réparation est annoncée, sans second verdict ensuite ; les
retours False de la réparation n'expliquent pas leur motif dans le journal.
Ne pas attribuer ce non-appliqué à un conflit précis sans preuve supplémentaire.
Aucun fichier du projet utilisateur corrigé manuellement.

UX locale : nom proposé/adopté pour la surface = Atelier. Contrat complet dans
l'Atelier visible et sélectionné sur le bon run, sinon retour complet dans le
chat ; aucune double approbation complète. Choix techniques et méthode de
validation dépliables, critères séparés avec lecture intégrale explicite pour
les longs textes. Indicateur d'activité hors journal fermé, distinct de
l'attente d'accord. Suivi de la nouvelle tentative même pour un ancien run
terminal sans chemin en cache ; une inspection manuelle d'historique reste
stable jusqu'au démarrage d'un nouveau travail, fermeture toujours respectée.

Limites constatées avant l'accord du lot ci-dessus : lecture non autorisée, édition
ciblée plutôt que réécriture, cohérence contrats/tests générés et explication
des refus de réparation restent à traiter. Le gate a correctement refusé la
livraison ; ne pas contourner les tests ni modifier à la main l'exemple.
Validation UI : 101 tests passent et build réussi. Chromium vérifie contrat
complet unique, repli vers chat à la fermeture puis retour dans l'Atelier,
préservation du brouillon/géométrie pendant les événements de travail, suivi
réparation → échec et historique/concurrence. Aucune erreur JS. Les étapes
actives se renouvellent avec une transition courte respectant reduced-motion,
avec compteurs d'étapes/fichiers réellement observés, sans faux pourcentage.

## Diagnostic critique de reprise — 20/10, tentative de 15:13

Journal réel, run `9c50e249-eb49-49c5-9081-79d77a9c3c58` : le front consulte
`projects.list`, retrouve le chemin, puis transforme l'ancien refus de manifeste
en tâche « rétablir .project.json ». L'architecte attend environ 104 s et échoue
en planifiant ce fichier caché. Aucun worker ne démarre. Ne pas confondre cette
nouvelle erreur architecte avec la précédente erreur de destination.

Correctifs locaux : manifeste exact `.project.json` écarté des fichiers source
planifiés (runtime seul propriétaire, publication après gate réussi), règle
explicite front/architecte ; autres chemins cachés toujours refusés, dépendance
sur le manifeste toujours invalide. Un plan uniquement manifeste doit être
replanifié, pas validé comme réparation. L'assembleur ne supprime plus les
modules hors plan lors d'une modification explicitement liée à un projet
existant. L'UI restaure le chemin du contrat même sur un run terminal en cache,
sans le réactiver ni réafficher une approbation.

Limite profonde encore ouverte : l'architecte planifie une réparation sans
lecture des sources existantes. L'ajout de sources au prompt du fournisseur
LLM a été bloqué par la revue de sécurité (risque d'exfiltration de code) :
aucune implémentation de cette transmission n'a été appliquée. Accord explicite
utilisateur requis pour poursuivre cette partie ; ne pas contourner le refus.
Ne pas présenter les corrections locales comme une preuve de réussite du
projet réel. Aucun projet exemple modifié manuellement, aucun appel LLM payant.
Validation ciblée : 56 tests backend passent, 98 tests UI/build passent, parcours
Chromium de reprise/navigation/concurrence réussi sans erreur JS.
Suite backend complète après ces correctifs : 1108 tests passent (142 s).

## Continuité des tentatives — correctif du 20/10

Envoi/reconnexion : un socket absent/fermé ne doit jamais simuler un envoi
réussi ; l'interface conserve la saisie hors connexion et expose les erreurs
d'envoi au lieu de laisser les points d'attente. Un snapshot d'historique ne
supprime plus un message utilisateur local non retrouvé côté serveur, même si
le snapshot est plus récent. La déduplication des messages de l'extension Codex
elle-même n'appartient pas à ce dépôt. Le journal du serveur redémarré à 15:02
ne contenait aucun nouvel envoi au moment du diagnostic ; cela ne démontre
pas à lui seul quelle déconnexion/reconnexion a eu lieu dans le navigateur.
La session concernée n'avait pas non plus été modifiée depuis 14:39. Validation
des protections d'envoi : 97 tests UI passent, build réussi.
Le parcours rapide suppression/navigation a aussi reproduit une ancienne vue
encore rendue alors que le store était déjà revenu au chat et contenait le
nouveau run. Suppression de l'attente de sortie globale `AnimatePresence wait` :
la vue suit immédiatement l'état, avec animation d'entrée conservée ; animations
de l'îlot inchangées. Le scénario navigateur couvre cette succession rapide.
Parcours Chromium réussi après modification : correction suivie jusqu'à
l'échec, navigation/historique/concurrence conservés, aucune erreur JS.

- Un projet partiellement généré peut ne plus avoir de `.project.json` après
  l'échec du gate. La reprise exige alors une destination explicite existante,
  une référence de destination dans le journal de cette conversation ET une
  écriture de fichier enregistrée pour ce run. Une proposition seule ne suffit
  pas. Les protections chemin/symlink/inode restent actives ; aucun manifeste
  exécutable n'est fabriqué pour contourner la validation.
- `task.routing` expose le chemin explicitement choisi dès la délégation ;
  `task.received` et les erreurs de préparation conservent cette association.
  L'îlot suit la tentative plus récente du même projet dans la même conversation,
  y compris un échec avant les workers, sans sélection d'un projet ressemblant
  ni capture par une tâche indépendante. Une fermeture explicite reste respectée.
- Le journal réel du projet G-code confirme la provenance requise (index
  temporaire uniquement, aucun fichier du projet exemple modifié).
- Validation après correctif : 1106 tests backend passent (138 s), 93 tests UI
  passent et build réussi. Cas couverts : reprise sans manifeste, refus d'une
  simple proposition sans fichier, session étrangère/supprimée, suivi de la
  tentative suivante sans sélection d'une tâche indépendante.
  Parcours Chromium réussi, sans erreur JS : sélection automatique de la
  correction du même projet, préparation visible puis échec visible dans l'îlot.

## Contrats lot 2 — avant code, 20/10

- `facts.search {query}` : recherche textuelle dans clés/valeurs/citations,
  5 faits actuels maximum. Ce moteur de recherche n'est pas du routage.
- `facts.read {key}` : valeur courante, révision, citation utilisateur et
  références source ; 3 révisions les plus récentes au maximum.
- `facts.write {key,value,quote,source_message_id,expected_revision}` : front
  uniquement. Source = message **utilisateur réellement persisté dans la session
  appelante**, citation littérale (≤500 caractères), valeur littérale incluse
  (≤300). Clé stable ≤80 caractères. Révision attendue 0 pour création, sinon
  révision lue : conflit explicite, aucune écriture écrasante. Une source plus
  ancienne ne remplace pas une source plus récente. Historique append-only,
  répétition identique idempotente. Le modèle ne certifie pas la vérité d'une
  proposition ; il enregistre une interprétation sourcée, qu'il faut évaluer.
- Le runtime communique seulement l'identifiant du message courant au front,
  pas une liste de souvenirs. Une absence d'identifiant empêche la promotion.
- Les workers lisent les mêmes références/faits avec la session de leur tâche,
  jamais celle proposée par le modèle. Écriture de faits personnels interdite
  aux workers. Premier branchement LLM : génération de fichiers Python et web,
  2 lectures maximum avant de rendre son fichier, pas d'injection automatique.
- Les faits sont partagés pour l'utilisateur local courant ; l'isolation entre
  plusieurs comptes utilisateurs n'est pas implémentée par ce lot.

Acceptation : fait utilisateur puis correction, redémarrage, anciennes révisions
conservées, refus de sources assistant/inexistantes/autre session, conflit de
révision/source ancienne, lecture par deux workers sans transfert de contexte,
aucun appel de lecture sur un résultat code ordinaire et budget borné.

## État courant — lots 1 et 2

Validation lot 2 : **1104 tests backend passent**, 9 warnings, 141 s. Sept tests
ajoutés : révisions/corrections, redémarrage, citations/sources rejetées,
concurrence, source serveur non falsifiable par le client, accès Python/web
en lecture et borne d'appels. Pas de modification UI ni appel LLM payant.

Validation lot 1 : **1097 tests backend passent**, 9 warnings, 139 s. Vérifications
mémoire/outils/vision ciblées relancées après durcissement du rôle des résultats
(données dans un message user balisé, jamais des instructions system). Aucun
appel LLM payant ; providers déterministes dans les tests. UI inchangée.

Implémentation locale sur `feat/shared-memory` : index SQLite incrémental,
outils `projects.list`, `projects.read`, `memory.search`, `facts.search/read/write`,
boucle JSON du front brain (3 opérations maximum), résultats bornés et hors transcript.
Le LLM reçoit le contrat des outils, sans projets/souvenirs ajoutés automatiquement.
Le soul existant et les vingt derniers messages restent le contexte de base.

`MemoryManager.consult` et `BaseBrain.consult_memory` fournissent l'accès commun.
Le front et la génération initiale de fichiers Python/web ont leur boucle LLM.
Les autres générateurs/repairs/research n'utilisent pas encore cette boucle.
Les workers n'ont que la lecture, avec 2 consultations max par génération ;
source/session fixées par le runtime. Les références projets viennent du journal.
Les faits sont des interprétations LLM reliées à une citation utilisateur validée,
avec révisions append-only, conflit explicite et refus d'une source plus ancienne.
Aucun appel d'extraction ajouté automatiquement à chaque tour.

Le serveur transmet l'identifiant du message utilisateur qu'il vient de persister,
en ignorant toute référence similaire du client. Le front peut ainsi proposer
une écriture vérifiable. Les anciens souvenirs Chroma restent consultables par
recherche ; ils ne sont pas massivement promus en faits structurés par ce lot.
Une recherche de faits peut retrouver une clé via une ancienne citation, mais
renvoie toujours la révision actuelle (pas l'ancien nom remplacé).

Lecture du **vrai** journal G-code vérifiée avec index temporaire : chemin exact,
statut failed et cinq fichiers retrouvés. Verdict détaillé inconnu dans cette
ancienne trace (pas de session sur l'événement Python) ; ne pas le reconstruire
par proximité temporelle. Les nouveaux événements Python de verdict sont
maintenant corrélés au contexte de tâche.

`query_report` distingue les statuts de récupération et journalise les erreurs.
L'API `query` historique reste compatible pour ses autres consommateurs ; le
front utilise le rapport explicite pour ses outils. Résultats sémantiques :
24 candidats, dédoublonnage/exclusion du contexte courant, au plus 4 résultats
sourcés retournés. Événement `memory.consulted` avec outil/statut, et pour le front
taille/mode lecture-écriture/numéro d'opération,
sans dupliquer le contenu ni la requête dans cet événement.

Limites restantes : déclenchement de lecture guidé par le prompt et évalué avec
provider déterministe, sans garantie qu'un modèle réel respectera toujours la
consigne. Pas encore de rétraction de fait, de résolution d'entités/synonymes
automatique, de benchmark de grand volume, de campagne LLM payante ou de vue UI
dédiée aux consultations. Citation littérale ≠ validation sémantique de l'attribut :
questions/négations et mauvaises associations de clé doivent être évaluées en réel.
Le premier indexage parcourt les journaux existants ; les lectures suivantes
ne consomment que les lignes nouvelles. Mesurer ce coût sur gros corpus au lot 4.
Ne pas annoncer la phase mémoire complète. Branche à valider avant tout merge.

## Contrats du premier lot — fixés avant code, 20/10

Le front utilise son protocole JSON LLM existant : une réponse intermédiaire
`{"memory":{"tool":"projects.list","arguments":{}}}` est exécutée localement,
puis le LLM reçoit le résultat comme donnée et reprend sa réponse/délégation.
Pas de détection de mots-clés dans le message utilisateur.

- `projects.list` : au plus 5 références compactes de la session courante.
- `projects.read` : argument `id`, au plus 20 fichiers et dernier verdict ;
  impossible de changer la session dans les arguments.
- `memory.search` : argument `query`, au plus 4 souvenirs avec source et rôle ;
  statut distinct pour vide/désactivé/indisponible/erreur.
- Trois consultations maximum par réponse ; résultat borné à 6000 caractères,
  aucune écriture ni exécution de code par ces outils de lecture.

Index SQLite partagé entre processus, sous le répertoire mémoire isolable ;
projection incrémentale du journal de bus, sans recopier les sorties volumineuses.
Les objets projets sont liés à session + run, jamais à la navigation globale.
Après échec et redémarrage, les références contractuelles et fichiers conservés
restent consultables. Les projets des sessions supprimées ne sont pas exposés.
Les résultats d'outils restent hors du transcript et hors de l'UI conversationnelle.
L'ancien rappel automatique est remplacé par la consultation choisie par le LLM.

Acceptation du lot : replay du cas G-code en provider déterministe sans appel
payant ; consultation puis délégation vers le chemin exact ; nouvelle session
sans fuite ; budget de trois lectures ; refus des outils/arguments inconnus ;
panne explicite ; aucun projet ni souvenir injecté avant consultation.
Les faits structurés modifiables et l'évaluation de grande échelle restent les
lots suivants de cette même branche ; ne pas présenter ce premier lot comme
une refonte mémoire complète ni une garantie de rappel du modèle.

Décision utilisateur du 20 octobre 2026. Branche `feat/shared-memory`, depuis
main après le merge du cycle Morphable UI P1. Ce document cadre la prochaine
phase ; aucune nouvelle architecture mémoire n'est implémentée dans le lot UI.

## Problème observé

La conversation G-code conserve la demande et l'erreur, et son journal connaît
`sandbox/klipper-gcode-offline` ainsi que ses fichiers. Le front brain ne reçoit
pas ces références et redemande le chemin. Ce défaut de continuité immédiate
doit être distingué du rappel sémantique de souvenirs anciens. Dans le cas
inspecté, la base mémoire existe, mais aucun souvenir ne contient ce chemin.

## Direction retenue

- Mémoire partagée accessible au front et aux sub-brains par outils ciblés.
- Recherche sémantique complétée par faits structurés : informations utilisateur,
  projets de conversation, fichiers, points d'entrée, verdicts et références.
- Lecture d'un résumé compact, approfondissement à la demande. Pas d'injection
  systématique des comptes rendus des sub-brains à chaque appel du front brain.
- Sources, dates, auteur, corrections et références aux preuves conservés.
  Gestion des doublons, contradictions, obsolescence et séparation des sessions.
- Consultation avant de déclarer inconnue une information déjà enregistrée ;
  décision LLM et contrôle observable, jamais de routage par mots-clés.
- Distinguer rappel vide, désactivé, indisponible et en erreur ; les exceptions
  actuellement masquées ne doivent plus rendre une panne indiscernable d'un vide.

## Ordre de travail

1. Auditer les écritures/lectures existantes et fixer les contrats/outils, les
   portées et les budgets de lecture, avec scénarios de validation avant code.
2. Assurer la continuité du travail courant par références durables consultables,
   y compris après échec/redémarrage, sans hériter du projet d'un autre onglet.
3. Ajouter faits personnels, provenance/corrections et recherche combinée.
4. Évaluer consultation LLM, erreurs explicites, volume, latence et tokens lus.

## Acceptation attendue

- « Corrige ce projet pour passer les tests » retrouve la cible G-code déjà
  créée dans cette conversation, après échec, reload et redémarrage.
- Rappel d'un fait personnel tel que le nom d'un animal, puis correction de ce
  fait : source utilisateur retrouvable, ancienne réponse assistant non prioritaire.
- Deux projets/conversations concurrents : aucune fuite de cible ni d'historique ;
  ambiguïté réelle clarifiée, pas de chemin deviné.
- Panne de récupération identifiée sans affirmer que l'utilisateur n'a rien dit.
- Volume croissant représentant des dizaines/centaines d'heures : mesurer rappel,
  coût en contexte et latence avec corpus de test isolé ; aucun seuil chiffré
  promis avant établissement d'une référence.

Pas de réparation manuelle du projet G-code pour faire paraître BigBrain capable.
La refonte générale du focus, Laya et les autres verticales restent au backlog.
