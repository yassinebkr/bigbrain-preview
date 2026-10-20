# Morphable UI — premier catalogue de widgets

20/10/2026, livraison de `feat/morphable-ui-p1` ; clôture/push/merge autorisés.
Ce bilan prime sur les mentions historiques de validations intermédiaires.

Validation de clôture (Python 3.12 après restauration du venv) : suite complète
**1090 réussites / 1 timeout** (153 s), `test_noisy_brain_high_event_throughput`
à délai 5 s. Il a échoué aussi lors d'une relance de sa classe sous charge, puis
réussi seul après les contrôles concurrents, comme sur main `209515b` dans un
checkout temporaire. Chemin dispatch inchangé dans ce lot ; test non assoupli.
Cette intermittence reste à surveiller. **92 tests UI**, build et **deux parcours
Chromium** réussis, dont noms de fichiers après reload, console réelle,
composition acceptée, transitions, marges, historique et synchronisation.

Livré : zone contextuelle à widgets bornés, navigation en îlot vertical,
agrandissement/fermeture animés, marge basse et grille adaptative, console Python
partagée chat/panneau, journal lisible, propositions de composition de l'architecte
acceptables/réversibles, renommage/suppression des chats, restauration des noms
de fichiers (path/file_path) jusque dans les cartes terminées. Planning Python
compact, diagnostic d'échec gate conservé et réparation des sources bornée.

Historique et noms de fichiers validés par l'utilisateur ; design itéré à partir
de ses captures. Ne pas en déduire une validation de tous les usages produits.
Défaut connu reporté explicitement : le front brain ne retrouve pas toujours
la cible d'un projet de la conversation, même si ses cartes la connaissent.
Ce cas est prioritaire dans [SHARED_MEMORY_PLAN.md](SHARED_MEMORY_PLAN.md).

Décision utilisateur du 20/10 : traiter la mémoire dans la **branche suivante**,
séparée, après clôture du cycle courant (`feat/shared-memory` proposée depuis
main après merge). Ne pas ajouter son implémentation à ce lot UI. Roadmap de
référence : `../tests/bigbrain-preview-phase1.md` dans le dossier de travail
voisin du repo, §6. Mémoire partagée interrogeable par tous les brains, faits
structurés + recherche sémantique, provenance/corrections, lectures ciblées,
consultation vérifiable et erreurs observables ; éviter les injections de
comptes rendus des sub-brains à chaque tour.

**Historique design :** première version rejetée, puis plusieurs corrections
visuelles livrées. Ne pas considérer les tests techniques comme une validation design.

## Point 5 — repasse visuelle du 19/10

20/10 : historique validé par l'utilisateur. Libellés de progression Python/web
traduits (création/modification/enregistrement, environnement, exécution,
compilation et corrections) ; aucune étape interne inconnue exposée en libellé.
Première tentative masquée, numéro visible à partir de la deuxième seulement.
Correction complémentaire : Python émet `file_path`, web émet `path` ; les deux
sont reconnus. La projection historique conserve début + progression + fin,
pour appliquer les noms avant de terminer chaque étape. Les cartes terminées
en cache peuvent enrichir leurs libellés avec ces événements sans redevenir
actives. Rétroactif lorsque les événements corrélés sont présents dans le journal.
Événements et vérifications restent inchangés. Push/merge pas encore effectués.

Correction visuelle du 20/10 après capture utilisateur : hauteur du main et
ligne de grille bornées (min-height:0, minmax(0,1fr)), pour conserver le bord
arrondi et la marge basse même avec un long transcript/journal. Chat agrandi
en rail de 420 px avec bulles utilisant sa largeur. Deux colonnes de widgets
uniquement lorsque le conteneur dépasse 760 px, sinon pile cohérente ; suppression
du rowspan artificiel qui créait des espaces vides. Journal dans une carte
arrondie, étapes immédiatement visibles, sorties dépliables, sans double accordéon.
Historique : couleur de texte héritée explicitement du thème pour le renommage,
les icônes et la confirmation de suppression. Vérification navigateur ajoutée
pour marge basse à 1600/1200 px, repli des cartes, journal ouvert et contraste.

### Navigation et conversations

Le robot revient au chat courant ; seul le « + » crée un chat. Les autres
destinations sont conservées à ce stade. Piste de simplification : garder
Chat/Workspace/Tâches/Historique comme destinations fréquentes, placer les
outils avancés Agents/Preuves/Apps dans un accès secondaire, après validation UX.

Historique : renommage explicite (1–120 caractères, non écrasé par l'auto-titre),
suppression confirmée, erreurs serveur visibles. Suppression corrélée à la session :
arrêt via le hook des agents, annulation des envois, nettoyage du replay et des
états locaux (runs, contrats, widgets, corrélations console). Les onglets ouverts
sont informés ; les onglets reconnectés réconcilient les marqueurs de suppression.
Marqueur persistant sans transcript empêchant la recréation par une réponse tardive.
Projets/fichiers, mémoire partagée, preuves et journaux techniques conservés :
suppression d'historique, **pas une purge de données personnelles**. Les processus
manuels lancés depuis le workspace ont leur propre cycle de vie.
Validation : 36 tests backend ciblés, 91 tests UI, build et parcours Chromium
incluant renommage, annulation de suppression, suppression active dans deux
onglets, reload, autre conversation et fichier projet conservés. Les mutations
du parcours portent exclusivement sur des sessions temporaires isolées.

### Surfaces hors code — direction, pas de vues fictives livrées

La vue d'ensemble constitue le cadre commun ; les autres vues doivent dépendre
des objets réellement produits : code → aperçu/fichiers/vérifications ; recherche
→ synthèse/sources ; tâches → liste/décisions ; notes → document ; matériel/CAO
→ modèle/mesures/contrôles lorsque ces données existent. Ne pas généraliser
« Fichiers / Tests » à tous les métiers, ni créer des onglets vides pour annoncer
une capacité absente. L'agent propose dans le catalogue, le client vérifie les
données disponibles et conserve les règles d'autorité du point 4.

Référence : hybride éditorial/atelier/widgets des images utilisateur. Navigation
desktop en îlot vertical arrondi centré à gauche (précision utilisateur) ; panneau droit flottant arrondi, onglets en
pilules, identité/statut, cartes compactes pour le livrable, les fichiers et la
console. Vérifications résumées par leurs vrais stages, étapes récentes issues
du run, détails secondaires repliables. Vue agrandie en grille à deux colonnes.
Pas de visualisation métier inventée pour imiter la maquette.
Vue agrandie corrigée : livrable/actions à gauche, console/vérifications à droite,
alignés en haut ; console plus haute et preview pleine largeur. Chat compact
conservé. Ouverture/fermeture/agrandissement animent les colonnes sur 320 ms,
avec fondu/décalage du panneau (220 ms), sans remontage de l'iframe à
l'agrandissement. Préférence de réduction des mouvements respectée.

Fermeture explicite : la colonne réservée disparaît et le chat se recentre.
Avant le premier travail, la réservation reste active sur grand écran pour
éviter un saut à l'arrivée du premier événement. Une fermeture explicite reste
respectée par les événements suivants. Navigation mobile conservée en tiroir.

Validation : 91 tests UI, build, parcours Chromium morphable et lifecycle ;
captures inspectées, recentrage et géométrie de l'îlot contrôlés. Appréciation
visuelle finale laissée à l'utilisateur ; aucun push/merge.

## Point 4 — propositions contrôlées

Premier producteur autorisé : architecte, dans son appel de planning existant,
sans appel LLM supplémentaire. Champ optionnel `workspace_widgets` : 1–2 noms
distincts parmi files/verification/console/preview. Aucun contenu, chemin,
HTML, géométrie, action, mesure ou permission ne peut y être ajouté.
Métadonnée invalide rejetée sans casser une architecture par ailleurs valide.

L'orchestrateur émet `workspace.proposal` lié au session_id/task_id réel,
producteur architect, enveloppe version/revision/widgets. Journal durable et
replay conservent la dernière révision valide, pas un événement périmé/invalide.
Le client valide à nouveau : pas d'orphelin, mauvaise session, producteur non
autorisé, vieille révision ou extension arbitraire du contrat.
Le relais et le journal contrôlent aussi la source bus effective
`orchestrator_<workspace>` ; déclarer producer=architect ne suffit pas pour un
worker. Le bus HMAC reste l'autorité d'authentification de cette identité.

Proposition observée par défaut : aucune composition imposée. Dans la vue
d'ensemble, « Suggestion de composition » permet d'accepter ou de revenir au
standard. Le choix accepté est une copie figée par session/run/révision ; une
nouvelle suggestion ne le remplace pas. **Accepter une composition n'approuve
pas le contrat de code**, ne lance rien et ne change ni cible, taille, vue ni
surface sélectionnée. Données disponibles résolues depuis le vrai run ; widget
indisponible omis, pas fabriqué. Console déjà consultée et verdict non passé
restent prioritaires, dans deux emplacements secondaires maximum.

Limites : pas de propositions libres du front brain ou de tous les workers,
pas de génération de widgets/HTML à la volée, pas d'autonomie de layout. Les
anciens runs sans proposition gardent la composition standard. La prochaine
proposition réelle nécessite un nouveau planning après redémarrage du serveur ;
aucune proposition n'a été générée par un appel payant pendant ce lot.

Validation point 4 : 91 tests UI + build, 14 tests dédiés backend, tests architecte
et historique ciblés, deux parcours Chromium isolés avec acceptation, reload,
absence d'auto-preview, choix conservé, console réelle et navigation.
Suite backend finale : **1087 passés**, 9 warnings (141 s). Aucun push/merge.

## Points 1–3 — portée livrée, UX non validée

L'environnement entier peut s'adapter. Son état par défaut reste le chat large
et une zone droite de 400 px, espace réservé sur grand écran sans reflow lors
de l'arrivée d'un run. Sélection par conversation, fermeture explicite respectée,
travaux concurrents sans écrasement ; agrandissement réversible sans remontage
du chat ou de l'iframe. Mobile : ouverture explicite et retour au chat.

`WorkWidgets.tsx` compose un contenu principal et jusqu'à deux sections
secondaires, au lieu d'une liste de logs affichée par défaut :

- **Proposition** : cible figée, stack et critères du vrai contrat ; décisions
  via la même action backend que le chat. Session/plan/design doivent correspondre.
- **Travail courant** : étapes réellement actives, agents et durée reçue ; aucune
  liste de phases préfabriquée, pourcentage ou estimation de fin inventés.
- **Livrable** : point d'entrée déclaré représenté comme objet, fichiers disponibles,
  actions conditionnées au résultat. Taskboard ≠ projet, même avec métadonnées périmées.
- **Vérifications** : verdict/stages/tentative reçus, synthèse et détails dépliables.
  Démarrer le programme ≠ réussir ses tests. Le journal technique reste secondaire.
- **Résultat** : preview web existante à la demande ; console Python branchée sur
  le runner existant. Aucune interprétation de prose comme rapport structuré.

Cadre et actions stables, hiérarchie éditoriale, artefact identifié, animations
discrètes d'opacité/activité ; réduction des mouvements respectée. Pas de graphique
G-code/CAO factice. Les propositions bornées de l'architecte sont décrites ci-dessus.

## Exécution Python

Une action utilisateur lance `POST /api/fs/run` sur l'entrée exacte du run,
sans shell, argument inventé ou retargeting vers le projet sélectionné ailleurs.
`projectRunStore` corrèle session + run orchestré → runId manuel ; la carte du chat
et le panneau partagent le lancement. Double clic bloqué pendant HTTP/attente WS
et exécution. Console immédiatement visible, sorties WS échappées, suivi du bas
désactivable ; exitCode/timedOut et erreurs reflètent le contrat réel du serveur.

Navigation/agrandissement ne relancent rien. Les 30 dernières corrélations et
sorties **terminées** sont persistées localement. Reload pendant une exécution :
suivi potentiellement indisponible, état inconnu annoncé ; pas de succès fictif,
pas de relance automatique. Ce n'est pas une reprise durable des processus.
Ouvrir le projet met à jour la navigation workspace, jamais la cible d'un worker.
Le runner existant reste borné par son délai ; ce lot n'ajoute pas de Stop dédié
aux processus manuels ni d'interface interactive stdin/argv.

## Validation

85 tests UI et build ; deux parcours Chromium isolés. Catalogue/provenance,
approbation corrélée, tâches concurrentes, stabilité du chat, sessions, mobile,
reload, previews/baux, sortie Python réelle, lancement depuis la carte du chat,
restauration de console terminée. Les événements de génération sont des fixtures
de test explicites ; le script Python et ses sorties sont réellement exécutés.
Pas de nouvel appel LLM, ni campagne réelle de génération. Backend inchangé pour
ce lot ; suite backend complète non relancée (dernier résultat antérieur : 1073).
