# ResearchBrain — cadrage décidé le 21 octobre 2026

Prochain jalon après validation utilisateur de la mémoire partagée et de la
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
