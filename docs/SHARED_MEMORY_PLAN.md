# Prochaine phase : mémoire partagée consultable

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
