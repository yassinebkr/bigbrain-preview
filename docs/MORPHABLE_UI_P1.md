# Morphable UI P1 — premier prototype testable

Branche : `feat/morphable-ui-p1`, base `main` @ `209515b`.
État au 20/10 : clôture et merge explicitement autorisés par l'utilisateur.
Les sections ci-dessous conservent les étapes de l'expérimentation ; le bilan
de livraison courant est dans [MORPHABLE_UI_WIDGETS.md](MORPHABLE_UI_WIDGETS.md).
La phase suivante est cadrée dans [SHARED_MEMORY_PLAN.md](SHARED_MEMORY_PLAN.md).

**Lot courant : [premier catalogue de widgets](MORPHABLE_UI_WIDGETS.md).**
Son cadre/composition et son parcours Python remplacent l'inspecteur passif
décrit dans les sections historiques ci-dessous.

## Planning Python — correction de charge, à mesurer en réel

Trace du test G-code du 19/10 : budget architecte global de 120 s épuisé,
sans contrat ni exécution. La trace seule ne permet pas de séparer attente
provider, génération et éventuelle réparation. Le chemin Python routé utilise
désormais un prompt compact et 4096 tokens de sortie demandés, contre le
schéma général exhaustif/8192 auparavant. Interfaces typées, dépendances,
tests, contraintes utilisateur et 2–4 critères d'acceptation conservés ; pas
de hausse du délai, changement de modèle ou fallback silencieux. Réparation
toujours bornée par le même budget. 75 tests architecte/planning passent.
Pas de nouvel appel payant ni preuve de latence réelle améliorée à ce stade.
Suite backend complète après changement : **1068 passés**, 9 warnings (137 s).

## Assemblage Python : diagnostic et réparation bornée

L'essai `klipper-gcode-offline` démarrait correctement (exit 0, aide CLI), mais
son gate échouait : 23 tests passés, 2 échoués (diagnostic G92 absent ; test
sans arguments exigeant exit 2, code affichant l'aide avec exit 0). Le message
« not runnable » écrasait à tort la cause de vérification : corrigé.

L'assemblage conserve désormais stages et diagnostics réels. Une exception du
gate bloque la livraison, au lieu d'autoriser implicitement le résultat.
Si le gate échoue et qu'un provider existe : au plus deux propositions de
correction des sources Python déjà planifiées, 60 s/appel, contexte borné,
4096 tokens de sortie, remplacements exacts/uniques plutôt que réécriture
complète des fichiers (moins de sortie et refus des propositions ambiguës),
aucun changement des tests/conftest ni ajout de fichier/dépendance demandé.
JSON/chemins/syntaxe vérifiés avant écriture ; nouvelle exécution et gate complet
à chaque tentative, preuves numérotées et historique de réparation. Cache .pyc
des modules corrigés invalidé pour ne pas retester une ancienne source.
Conflit tests/contrat : ne pas affaiblir les tests pour livrer artificiellement ;
la réparation peut donc rester en échec et ne garantit pas la réussite du projet.
Ce mécanisme n'est pas un sandbox OS ni une preuve sémantique exhaustive.
16 tests multi-fichiers passent (vraies exécutions/tests, provider simulé pour
les propositions). Projet G-code utilisateur non modifié manuellement.
Suite complète : **1073 passés**, 9 warnings, 148 s ; format compact final
revalidé par les 16 tests multi-fichiers. Pas d'appel LLM réel ni push/merge.

## Cadrage courant — 19/10, remplace le contrat du prototype ci-dessous

La vision concerne **tout l'environnement adaptable à la tâche**, pas un
inspecteur latéral définitif. Le chat reste la page principale/par défaut ;
la zone latérale est le début de l'adaptation, pas sa frontière.

Premier incrément implémenté, UX à éprouver :

- Retour utilisateur sur capture : largeur par défaut **400 px** ; sur grand
  écran, réserver cette géométrie même avant le premier run ou après fermeture.
  L'apparition du contenu ne doit déplacer ni input ni bulles. Largeur choisie
  manuellement conservée ; agrandissement de l'activité toujours explicite.
- Échec global : les étapes encore en cours passent en échec, les étapes déjà
  réussies le restent. Les anciens runs restaurés avec une étape périmée ne
  montrent plus de spinner ni « En cours » après la terminaison du run.

- Sur écran large (≥1440 px), les vrais travaux alimentent automatiquement
  une surface à droite. Première sélection ancrée sur l'activité ; concurrence
  et fin n'imposent ni autre objet ni lancement de preview.
- Aucune bannière de travaux au-dessus du chat. Sur écran plus étroit, accès
  explicite à l'espace ; suivi existant conservé lorsque la surface est cachée.
- Une action explicite donne la place principale à l'activité : surface étendue
  et conversation compacte (360 px sur desktop), puis retour au chat principal.
  Le chat et la preview ne sont pas remontés lors de cette transition.
- Fermeture explicite respectée, objets et sélection conservés par conversation.
  Le resize latéral réserve de la place au chat ; les écrans étroits affichent
  une surface unique avec retour explicite. Pas de focus forcé.
- Préférences de disposition indépendantes des droits et de l'exécution ;
  aucun changement des brains, aucune nouvelle génération ni action physique.

Limite : première fondation de composition, pas encore un environnement métier
complet ni des mutations proposées par les agents. Catalogue réel encore limité
à activité/fichiers/vérifications/preview. Pas de fausse simulation électronique
ou CAO pour illustrer la vision. Les paragraphes suivants documentent le
prototype antérieur ; leurs règles d'ouverture et de barre haute sont remplacées
par ce cadrage.

Validation de cet incrément : **73 tests UI**, build réussi (avertissement de
taille bundle existant), parcours Chromium `check_morphable_p1` et
`check_ui_lifecycle` passés, zéro erreur JS. Transition activité principale ↔
chat vérifiée avec un marqueur DOM dans l'iframe (pas seulement localStorage),
brouillon conservé ; concurrence, reload, isolation sessions, mobile et baux
preview vérifiés. Fixtures isolées, aucun appel LLM ni validation produit
réelle. Capture de l'activité étendue inspectée. Backend inchangé ; suite
backend complète non relancée. Aucun push/merge.

## Révision UX après le premier essai utilisateur

Premier retour : intégration maladroite, modes techniques exposés, résultats
terminés en double en haut, preview trop petite dans le chat et espace de
droite occupé par le journal technique. Révision locale : le chat raconte,
la surface droite permet de consulter et d'agir.

- `lib/morphable.ts` : registre fermé Aperçu/Fichiers/Tests/Activité et
  reconciler pur ; sélection explicite prioritaire, aucune géométrie LLM.
- `store/workspaceStore.ts` : préférences utilisateur par session (mode,
  surface sélectionnée, largeur), persistées séparément de l'exécution.
- `ContextWorkspace` : résultat desktop redimensionnable
  (400–1000 px, défaut 680, au plus 60 % du conteneur), surface unique sous 1100 px,
  retour au chat, états/erreurs/agents réels et ouverture des fichiers existants.
- Le chat reste monté : arrivée du premier run ne détruit pas son champ
  d'entrée. Aucun panneau ne s'ouvre en grand sur événement. Fin du travail
  conserve la surface. Les états internes ne sont plus des modes à apprendre.
- Le suivi du bas est remplacé par celui du workspace, sans double popup.
  Les contrats restent dans le chat ; raccourci de retour si approbation requise.
- En haut, uniquement les travaux en cours ; les résultats terminés restent
  dockés dans le chat, sans catalogue permanent en double. Les cartes affichent
  un nom de projet issu des métadonnées et « Afficher le résultat ».
- Une application web terminée et vérifiée s'ouvre directement sur Aperçu à
  droite. Jamais d'iframe/port démarré par une carte du chat. Fermeture du
  résultat ou changement d'onglet libère le bail ; réouverture sur le port
  stable du projet pour retrouver localStorage. Même fonctionnement mobile.
- Layout chat utilise la largeur disponible, sans conserver une grande marge
  extérieure pendant que le panneau comprime la conversation.
- Fichiers et Tests accessibles à côté d'Aperçu ; activité résumée et journal
  technique replié, sans carte répétée par fichier et par worker.

Limites explicites de ce lot : preview à droite, éditeur existant en modal,
pas de
nouveaux templates métier ni d'intentions LLM ; sortie consultable mais pas
encore de suivi automatique intelligent des logs ; scroll local de chaque
surface conservé pendant sa fermeture/réouverture, pas persisté au reload.
Préférences de présentation locales au navigateur (pas de synchronisation
serveur/multi-utilisateur). Mesure de valeur UX encore à faire avec l'utilisateur.
Les champs non sauvegardés d'une app peuvent être réinitialisés au changement
d'onglet/rechargement de son iframe ; pas de promesse de persistance hors des
mécanismes de l'app (localStorage testé). Les données de test sont isolées.

## Contrat de ce lot

Sans LLM supplémentaire ni nouveau protocole, projeter les vrais runs de la
conversation dans un registre de surfaces identifiées et un reconciler pur.
L'état d'exécution reste dans appStore/backend ; le workspace ne conserve
que préférences de présentation, sélection et largeur. Aucun contenu factice.

- Chat seul par défaut ; pas de sélecteur Focus/Aperçu/Espace visible.
- Travail en cours : signal compact consultable, aucune colonne imposée.
- Résultat : sur action utilisateur, surface à droite sur écran large,
  surface unique sur écran étroit avec retour explicite au chat.
- Une discussion sans run ne doit rien ouvrir. Les événements n'imposent
  jamais l'ouverture du résultat ; une fermeture explicite reste respectée.
- Surface stable par session/run ; nouveau run concurrent ne remplace pas
  celui explicitement sélectionné. Fin/erreur ne ferme pas la surface.
- Fermer ≠ supprimer : préférences/sélection persistent par conversation,
  reload et navigation restaurent la consultation. Aucun changement de cible
  projet, d'agent ou d'autorisation à cause du layout.
- Catalogue P1 borné : preview vérifiée, activité, fichiers réellement signalés, verdict/stages
  de vérification. Raccourcis existants vers fichiers, Evidence et taskboard.
  Contrats et boutons d'approbation restent backend-driven dans le chat.
- Ne pas dupliquer l'iframe ni ouvrir un deuxième serveur preview. L'éditeur
  et le runner Python existants restent accessibles ; l'app web s'utilise
  dans la surface de résultat, avec ouverture externe optionnelle.
- Redimensionnement accessible au clavier sur desktop, largeur bornée ;
  pas de déplacement animé ni de focus automatique lors d'un événement.

## Vérification avant essai utilisateur

Tests purs : isolation sessions, choix stable, concurrence, fin/erreur,
fermeture sans perte, données sans run, surface étrangère/invalide refusée.
Tests composants : vraies valeurs projetées, pas de faux verdict/approbation.
Chromium sur UI compilée + backend isolé : ouvrir, changer de surface,
événement concurrent, fin, fermer/réouvrir, reload, changer de conversation,
viewport mobile sans débordement horizontal. Fixtures explicitement de test,
pas une campagne LLM. Rejouer les parcours existants chat/workspace/previews.

## Essais manuels et limites

Validation automatisée de la révision : **71 tests UI passés**, build réussi
(avertissement de taille bundle déjà connu). Contrôles Chromium sur serveur
isolé/UI compilée : brouillon/focus, aucun grand panneau imposé, concurrence,
fin persistante, fermeture/réouverture, reload, isolation des conversations,
resize clavier, lecture d'un vrai fichier, reflow à 390 et 320 px, zéro erreur
JavaScript. Non-régression chat/workspace/previews également passée, y compris
libération du port à la fermeture du résultat mobile et réacquisition au retour.
Vérifiés aussi : aucune iframe avant ouverture, une seule iframe ensuite,
localStorage conservé après changement d'onglet, disparition des travaux
terminés de la barre sans fermeture du résultat consulté.
Backend produit inchangé ; suite complète backend non relancée pour ce lot UI.
Scripts : `python -m tools.check_morphable_p1` et
`python -m tools.check_ui_lifecycle` (avec .venv, après build).

Comparer chat seul vs résultat ouvert sur un run web/Python, puis deux travaux
concurrents (projet + tâche). Noter : visibilité du brain actif, temps pour
retrouver un fichier/verdict, changements de surface involontaires, lisibilité
du chat et intérêt du mode compact. Pas de télémétrie utilisateur ajoutée
implicitement ; noter les observations, sans collecte distante.

P2 : templates curés et propositions LLM en shadow mode. P3 : sélection
collaborative/evidence vivante. P4 : compagnon ancré puis mouvement conditionnel.
La taskboard déléguée et renommer/supprimer les conversations restent des lots
distincts. Les audits ouverts du hardening restent suivis, pas masqués par P1.
