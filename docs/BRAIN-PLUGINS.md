# Brains as Plugins — la couche business de BigBrain

**Vision** (exprimée par Yassine, oct. 2026) : la vue "Découverte" devait
permettre d'ajouter plusieurs sub-brains et de les proposer comme des
*plugins* payants. BigBrain = le harness ; les brains = les plugins.
La business logic « toujours cachée quelque part » — voici l'inventaire de
ce qui existe déjà, suivi de l'architecture.

## 1. Les pièces existent déjà (inventaire)

| Pièce | Où | État |
|---|---|---|
| **Billing complet** | scratchy `lib/billing/` : plans.js, stripe-client.js, webhook-handler.js | Fini, non réutilisé |
| **Quotas par tier** | scratchy `lib/usage-tracker.js` : free (50 msg/j, open-core), pro €14.99/mo, max | Fini |
| **Slot UI paywall** | Aplot `ProPlanBanner` ("Unlock more with Pro Plan → Upgrade Now") | Rendu, non branché |
| **Boutons "Apps"/"Explore"** | Sidebar Aplot (LayoutGrid retiré récemment avec compass) | La cible UI de la découverte |
| **Abstraction brain** | bigbrain `brains/base.py` + registre + tokens HMAC au bus | Fini — un plugin = un brain |
| **Catalogue de brains premium candidats** | les projets perso : A-FPGA (builder FPGA/ASIC), Open_MC (microcontrôleur), palmierWin (éditeur vidéo), cinemate, dmx-controller, BCI… | À empaqueter |
| **Workspaces qui mappent déjà** | bigbrain `WORKSPACE_DEFAULTS` : web-dev, 3d-printing, electronics | Chaque workspace = un cas d'usage plugin |

Aucun € encaissé à ce jour — mais le pipeline technique est bâti aux 3/4.

## 2. Architecture proposée

### Brain manifest (le plugin devient déclaratif)

```json
{
  "id": "fpga-builder",
  "name": "FPGA Brain",
  "version": "0.1.0",
  "description": "Synthesis, timing analysis, and bitstream generation",
  "icon": "fpga.svg",
  "category": "electronics",
  "entry": "bigbrain_fpga:register",
  "capabilities": ["code_exec", "file_write", "bus.task"],
  "price": { "model": "one_time", "amount_cents": 1900 }
}
```

- `entry` : une factory qui retourne un Brain (l'abstraction `base.py`
  existante — aucun changement du noyau, le plugin EST un brain)
- `capabilities` : délégation chère — cf. les contrats
  decision→authorization→handoff (`docs/ORCHESTRATION-SHOPIFAST-LESSONS.md` §2) :
  **installer un plugin = obtenir une authorization de capacités**, le
  chainage typé existant applique déjà les règles
- `price` : `free` | `one_time` | `subscription` — le paywall n'est qu'un
  check sur la license locale

### Découverte (la vue "Explore" ressuscitée)

- `GET /api/plugins` : catalogue — locaux (`data/plugins/`) + registre
  distant plus tard ; manifest + état (installed / available / licensed)
- Vue Discover : cartes par catégorie (Electronics, Media, Research…),
  install en un clic (télécharge/active, le brain rejoint le pool de
  l'orchestrateur), badge PRO sur les payants → ProPlanBanner existant
- Le bouton Apps de la sidebar redevient logique : **Apps = installés,
  Discover = catalogue**

### Licences & paiement

- Porter `lib/billing/` de scratchy (stripe-client + webhook) côté
  bigbrain ; le manifest porte le `price`, le webhook Stripe délivre une
  license signée (clé locale `data/licenses/`)
- Check cheap et local : license signée vérifiée offline, pas de call
  réseau au lancement d'un brain
- Open-core respecté : le harness + les brains de base restent libres ;
  les plugins premium et le cloud sont payants

## 3. Pourquoi ça colle avec le reste du plan

- **Route sémantique** (shopifast §1) : `capabilityFamilies` du routeur
  = les catégories du store — le routeur sait quels plugins un message
  requiert avant même de les charger
- **ClawOS** : "multi-agent as processes, scoped permissions" — le plugin
  avec manifest + capabilities est exactement ce modèle, version produit
- **Aplot/AI SaaS template** : `ai-saas-main` (repo Windows) avait déjà la
  structure SaaS (subscription-button, pro-modal, landing) — même couche

## 4. Ordre réaliste

1. Brain manifests + `GET /api/plugins` +Discover view (catalogue local,
   install/enable/désactivate réels sur les brains existants :
   python, researcher)
2. Empaqueter 1 brain premium candidat (FPGA le plus avancé) en plugin
   avec license signée — le pipeline bout-en-bout prouvé sur UN plugin
3. Porter le billing scratchy + checkout Stripe sur ce plugin
4. Multi-brain store + registre distant

Règle anti-utopie : pas de marketplace avant qu'un plugin payant
unique n'ait été installé, payé (même à soi-même en test), et utilisé
bout-en-bout.
