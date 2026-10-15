# Harness déterministe — plan de portage fpga → bigbrain

Exploration de `../fpga/backend` (25–26 oct. 2026) et plan d'implémentation.
Protocole convenu : ce document d'abord, le code ensuite.

## 1. Pourquoi

Aujourd'hui le PythonBrain annonce « hello.py créé, il affiche Hello, World! »
sur la foi de son propre run. Rien ne prouve le claim : pas d'enregistrement
auditable, pas de vérification systématique avant de marquer un subtask
complete, pas de possibilité de rejouer. Le backend fpga a résolu exactement
ce problème pour le matériel — on porte les mêmes idées pour Python.

Principes directeurs (empruntés à fpga) :
- **Le chat n'est pas une source de vérité.** Chaque run laisse un
  `RunManifest` versionné, immuable une fois complété.
- **Un outil absent ou inconclusif n'est jamais un pass.** (Verilator →
  ici : pytest absent = `inconclusive`, pas `passed`.)
- **La gate est conservatrice** : une étape obligatoire failed OU
  inconclusive n'autorise jamais le « task complete ».
- **Policy et exécution séparés** : décrire les règles (quoi vérifier)
  est distinct de les exécuter (comment).

## 2. Ce qui existe côté fpga (sources)

| Fichier | LOC | Idée à porter |
|---|---|---|
| `evidence.py` | 1 219 | `DesignSpec` (ce qui est demandé, indépendant du code), `StageResult`, `RunManifest` (inputs exacts, outils, stages, métriques, artefacts hashés sha256), `EvidenceReport` (dérivé, face humaine), `EvidenceRepository` (stockage durable, immuabilité des runs complétés, artefacts adressés par contenu) |
| `verification_pipeline.py` | 851 | Orchestration en adaptateurs : le pipeline possède l'ordre, la sémantique de gate, l'evidence et le cycle de vie ; les moteurs sont des adaptateurs sync/async interchangeables |
| `verification_policy.py` | 660 | Règles/assertions/waivers déclarés, indépendants de l'exécution |
| `verification_executor.py` | 554 | Adaptateurs d'exécution concrets ; sortie brute conservée en artefact ; outil manquant = `inconclusive` |
| `golden_models.py` | 332 | Corpus de référence indépendant du code généré |
| `differential_regression.py` | 557 | Différentiel corpus ↔ code généré ; run = job durable (survit à une déconnexion WS), log + manifeste persistés |
| `jobs.py` | 738 | Jobs avec annulation, timeout, streaming de sortie |

## 3. Ce qui existe côté bigbrain (point de départ)

- `verification/pipeline.py` : niveaux V1–V5, activés V4+V1 (Lightning).
- `verification/v4_deterministic.py` (~330 LOC) : `DeterministicValidator` —
  syntaxe, structure du résultat, mypy/pytest optionnels. Superficiel :
  pas d'evidence, pas d'artefacts, pas de manifeste, résultats non
  corrélés au run qui les a produits.
- `brains/python_brain.py` : la boucle interne Honk existe déjà
  (`_generate_and_execute` : generate → execute → retry avec feedback
  d'erreur au LLM, MAX_RETRIES=5). C'est le point d'accroche naturel :
  la gate déterministe s'y branche, elle ne remplace pas la boucle.
- `llm/usage.py` : comptabilité tokens — à référencer dans le manifeste
  (coût par run), pas à dupliquer.

## 4. Architecture cible

```
bigbrain/verification/
  evidence.py      ← port adapté de fpga/evidence.py (pas de constraints/
                     FPGA : DesignSpec simplifié = user_request + contrats
                     textuels ; artefacts = code, stdout, résultats)
  executors.py     ← stages déterministes Python :
                       1. syntax      : ast.parse (toujours, gratuit)
                       2. compile     : py_compile
                       3. run         : exécution bornée (timeout), capture
                       4. tests       : pytest si fichiers test présents,
                                        sinon inconclusive (pas skip-pass)
                       5. contracts   : le fichier demandé existe au bon
                                        endroit (ex. "hello.py" dans le
                                        projet) — le bug du "script créé
                                        sous un autre nom" ne peut plus
                                        passer
  gate.py          ← sémantique conservatrice : échec/inconclusif sur une
                     étape obligatoire → subtask FAILED avec détails,
                     la boucle Honk relance le LLM avec l'erreur
data/evidence/
  runs/<run_id>/manifest.json     ← immuable après complétion
  runs/<run_id>/artifacts/<sha>   ← code, stdout, stderr, tests
```

Intégration :
- `python_brain._generate_and_execute` et `_run_existing_file` appellent
  `gate.verify_run(...)` après chaque exécution ; le manifeste capte
  chaque tentative (attempt 1..N) avec ses artefacts.
- `orchestrator` : `subtask.complete` n'est émis que si la gate est
  verte (le brain le fait déjà remonter via success — le rend explicite
  dans le payload : `verification: {stages, verdict}`).
- WS/web : `verification.run_recorded` event → le RunPanel affiche le
  verdict par étape (pastilles façon agent console fpga — backlog UI).

## 5. Phases

### P1 — Evidence core (sans toucher au flow existant) — ✅ FAIT
- Port `evidence.py` : `DesignSpec` (user_request + contracts, hash
  sémantique), `StageResult` (statuts dont `inconclusive` = terminal),
  `RunManifest` (verdict dérivé conservateur : le pire résultat
  obligatoire gagne ; références d'artefacts validées croisées),
  `EvidenceRepository` (JSON canonique, écritures atomiques fsync,
  artefacts sha256 dédupliqués, immuabilité des runs terminaux,
  `BIGBRAIN_EVIDENCE_ROOT` surchargeable).
- Layout retenu : `data/evidence/{specs,runs,artifacts/sha256}` (flat,
  artefacts globaux adressés par contenu — dédup entre runs).
- Tests : `tests/test_evidence.py` (24) — roundtrip, immuabilité
  (même run_id), verdict conservateur, dédoublonnage, traversal refusé.

### P2 — Stages déterministes + gate — ✅ FAIT
- `executors.py` : stage_syntax (ast.parse), stage_compile (compile),
  stage_run (verdict SUR l'exécution déjà faite — la gate ne rejoue
  jamais le code), stage_tests (pytest si fichiers test présents ;
  absents = not_applicable, pytest manquant = inconclusive),
  stage_contracts (le fichier nommé dans la requête existe au bon
  endroit — attrape le "hello.py créé sous un autre nom").
- `gate.py` : RunGate.evaluate_attempt — spec + artefacts sha256
  (code, stdout, stderr, sortie tests) + manifeste terminal immuable,
  chaînage des tentatives via parent_run_id, verdict conservateur.
- Branché dans la boucle Honk (`_generate_and_execute`) et
  `_run_existing_file` : verdict failed → feedback au LLM (retry),
  inconclusive → pas de retry (l'environnement n'est pas réparable par
  le LLM) mais jamais revendiqué "verified" ; la gate ne casse JAMAIS
  la génération (erreur interne → verdict None, comportage legacy).
- Kill switch : BIGBRAIN_EVIDENCE=0.
- Tests : `tests/test_harness_gate.py` (24) — stages unitaires, gate
  end-to-end, chaînage des tentatives, intégration Honk (succès,
  cassé→corrigé, run_file).

### P3 — Replay & différentiel (pattern golden models)
- Rejouer un run depuis son manifeste (mêmes inputs → comparaison des
  outputs ; non-déterminisme détecté).
- Corpus de cas de référence (hello, fibonacci, file IO) pour la
  régression des brains eux-mêmes.
- *Done :* un run rejoué produit un diff manifeste vs replay.

### P4 — Surface UI
- Event `verification.run_recorded` → RunPanel : verdict par étape,
  artefacts cliquables. Pastilles agent console fpga (backlog).

## 6. Non-goals (P1–P3)

- Pas de sandbox OS (V2) — reste hors périmètre, comme en preview.
- Pas de review LLM croisée (V3) — déjà couverte ailleurs.
- Pas de portage de `jobs.py` complet : l'exécution bornée existante du
  PythonBrain suffit ; le replay P3 réutilise le même chemin.
- Pas d'outillage FPGA/EDA : uniquement les patterns, zéro import fpga.

## 7. Risques / points d'attention

- **Ne pas casser la boucle Honk** : la gate enrichit le feedback
  (erreurs déterministes précises), elle n'ajoute pas une seconde
  boucle de retry.
- **Coût zéro** : stages 1–2 sont gratuits ; 3 réutilise l'exécution
  déjà faite (pas de double run — le manifeste capture le run Honk,
  il ne le rejoue pas).
- **Chemin des manifestes** : `data/evidence/` est déjà ignoré
  (runtime), rien à re-tracker.
