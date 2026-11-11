# Paiements GeniusPay : clés Render et test en bac à sable

## 1. Ce qui change

| Avant | Maintenant |
|---|---|
| `/webhook/geniuspay` créditait le portefeuille sans rien vérifier : n'importe qui pouvait envoyer un faux webhook et se créditer. | Chaque webhook est vérifié avec la signature HMAC-SHA256 de GeniusPay. Un webhook sans signature valide est refusé (401). |
| Un même webhook reçu deux fois créditait deux fois. | Chaque événement (`id`) et chaque paiement ne sont traités qu'une seule fois. |
| Le montant crédité était celui annoncé dans le webhook. | Le serveur compare avec le montant qu'il a lui-même demandé. S'il ne correspond pas : `amount_mismatch`, rien n'est crédité. |
| Une seule paire de clés. | Sandbox et Live sont séparés, avec un interrupteur (`GENIUSPAY_MODE`). |

L'app actuelle continue de marcher : `/create-payment` répond toujours `{status, checkout_url, transaction_id}`.

Les paiements sont enregistrés dans Firestore, dans la collection **`paymentOrders`**. Les journaux des webhooks sont dans **`webhookEvents`**.

## 2. Les clés à ajouter dans Render

Où les mettre : **Render → ton service `api-marabo` → Environment → Add Environment Variable.**
Ensuite, clique sur **Save, rebuild and deploy**.

Toutes les clés se trouvent dans ton tableau de bord GeniusPay, application par application (Sandbox d'un côté, Production de l'autre).

### Interrupteur

| Variable | Valeur | Rôle |
|---|---|---|
| `GENIUSPAY_MODE` | `sandbox` | Environnement utilisé par l'app. Mets `live` seulement quand les tests sont finis : les vrais paiements commencent alors. |

### Application SANDBOX (tests, argent fictif)

| Variable | Où la trouver | Commence par |
|---|---|---|
| `GENIUSPAY_API_KEY_SANDBOX` | App Sandbox → Clés API → clé publique | `pk_sandbox_` |
| `GENIUSPAY_API_SECRET_SANDBOX` | App Sandbox → Clés API → clé secrète | `sk_sandbox_` |
| `GENIUSPAY_WEBHOOK_SECRET_SANDBOX` | App Sandbox → Webhooks → ton webhook → secret de signature | `whsec_` |

### Application PRODUCTION (vrai argent)

| Variable | Où la trouver | Commence par |
|---|---|---|
| `GENIUSPAY_API_KEY_LIVE` | App Production → Clés API → clé publique | `pk_live_` |
| `GENIUSPAY_API_SECRET_LIVE` | App Production → Clés API → clé secrète | `sk_live_` |
| `GENIUSPAY_WEBHOOK_SECRET_LIVE` | App Production → Webhooks → ton webhook → secret de signature | `whsec_` |

Tes anciennes variables `GENIUS_API_KEY` / `GENIUS_API_SECRET` sont encore lues comme clés **Live** si les `_LIVE` sont absentes. Une fois les `_LIVE` ajoutées, tu peux les supprimer.

### Page de test

| Variable | Valeur | Rôle |
|---|---|---|
| `PAYMENT_TEST_KEY` | Un mot de passe long de ton choix, par exemple 30 caractères au hasard | Protège la page `/payments/test`. Sans cette variable, la page est fermée. |

### Facultatif (valeurs par défaut correctes)

| Variable | Défaut |
|---|---|
| `GENIUSPAY_BASE_URL` | `https://pay.genius.ci/api/v1/merchant` |
| `PUBLIC_BASE_URL` | `https://api-marabo.onrender.com` |

**Règles de sécurité :**
- Les clés `sk_…` et `whsec_…` ne vont **que** dans Render. Jamais dans l'app Flutter, jamais sur GitHub, jamais dans une capture d'écran.
- Si une clé a fuité, régénère-la chez GeniusPay, puis remplace-la dans Render.

## 3. Côté GeniusPay : les webhooks

Un secret `whsec_` n'est généralement affiché **qu'une seule fois**, au moment de la création du webhook. Si tu ne l'as pas noté, supprime le webhook et recrée-le.

**Webhook Sandbox** (celui que tu as déjà) :
- URL : `https://api-marabo.onrender.com/webhook/geniuspay`
- Événements : `payment.success`, **plus** `payment.failed`, `payment.cancelled`, `payment.expired`.
- Copie le secret → `GENIUSPAY_WEBHOOK_SECRET_SANDBOX`.

**Webhook Production** (à créer dans l'app Production) :
- Même URL, mêmes événements.
- Copie le secret → `GENIUSPAY_WEBHOOK_SECRET_LIVE`.

Une seule URL suffit : le serveur reconnaît l'environnement grâce à l'en-tête `X-Webhook-Environment` et utilise le bon secret.

## 4. Mise en ligne

1. Remplace `main.py` et ajoute `paiements.py` (à côté de `main.py`, comme `recrutement.py`). Ajoute aussi `PAIEMENTS_RENDER.md` si tu veux le garder.
2. Ajoute les variables d'environnement dans Render, puis déploie.
3. Dans les journaux Render, cherche cette ligne au démarrage :
   `💳 GeniusPay : mode SANDBOX · clés OK · webhook sandbox OK · webhook live …`
   Si tu vois `MANQUANTES` ou `absent`, une variable est mal nommée.
4. Firebase → Firestore → Règles : colle le nouveau `firestore.rules`, puis Publier. Il ajoute `paymentOrders` et `webhookEvents`.

## 5. Tester en bac à sable

1. Dans ton navigateur, ouvre :
   `https://api-marabo.onrender.com/payments/test?key=TA_PAYMENT_TEST_KEY`
2. Vérifie le tableau : il doit afficher ✓ pour les 3 clés Sandbox.
3. Dans le tableau de bord GeniusPay, sur ton webhook, clique **Tester** (événement `webhook.test`), puis clique « Actualiser » sur la page :
   - le résultat attendu est `test_ok` ;
   - si rien n'apparaît et que les journaux Render montrent `🚫 Webhook GeniusPay REFUSÉ : signature invalide`, c'est le secret `whsec_` qui est faux.
4. Clique **Lancer un paiement test SANDBOX (200 F)**, puis ouvre la page GeniusPay et paie avec le moyen simulé.
5. Reviens et actualise : le paiement doit passer à **paid**, validé par **webhook**.
6. Refais un essai en **annulant** sur la page GeniusPay : le statut doit devenir `cancelled` ou `failed`.
7. Dans l'app, fais une recharge Marabo Pay normale. Le solde ne doit augmenter qu'**après** le paiement, et d'un seul montant.

Le bouton **LIVE** de la page crée un vrai paiement de 200 F (+ frais). Ne t'en sers qu'une fois les clés Live en place, pour un dernier contrôle.

## 6. Lire les résultats

| Statut | Signification |
|---|---|
| `pending` | En attente : l'utilisateur n'a pas encore payé. |
| `paid` | Payé et validé, portefeuille crédité. |
| `failed` / `cancelled` / `expired` | Rien n'a été crédité. |
| `amount_mismatch` | Le montant payé est inférieur au montant demandé. Rien n'a été crédité : à examiner. |
| `error` | GeniusPay a refusé la création (le détail est dans le document Firestore). |
| `environment_mismatch` (dans webhookEvents) | Un webhook live a visé un paiement sandbox, ou l'inverse : il a été ignoré. |
