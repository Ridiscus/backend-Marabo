# =============================================================================
#  MARABO — Moteur de paiement GeniusPay (sandbox + live)
#
#  À placer à côté de main.py. Branché dans main.py par :
#      from paiements import router as paiements_router, init_paiements
#      init_paiements(db)
#      app.include_router(paiements_router)
#
#  Principes :
#   1. C'est TOUJOURS le serveur qui crée un paiement (montant, motif, client)
#      et l'enregistre dans Firestore : payments/{paymentId}.
#   2. Un paiement n'est validé QUE par un webhook GeniusPay dont la signature
#      HMAC-SHA256(timestamp + "." + corps_brut, whsec_...) est correcte.
#   3. Idempotence : chaque événement (payload.id) n'est traité qu'une fois
#      (webhookEvents/{id}), et chaque paiement ne passe qu'une fois à « paid »
#      (transaction Firestore).
#   4. Filet de sécurité : /payments/{id}/status interroge GeniusPay si le
#      webhook n'est pas encore arrivé.
#
#  Variables Render : voir PAIEMENTS_RENDER.md
# =============================================================================
import hashlib
import hmac
import html
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from firebase_admin import auth as fb_auth
from firebase_admin import firestore

router = APIRouter()
_db = None
_push = None  # send_push_to_user(uid, title, body, data) fourni par main.py

# -----------------------------------------------------------------------------
# ⚙️ CONFIGURATION (variables d'environnement Render)
# -----------------------------------------------------------------------------
MODE = os.getenv("GENIUSPAY_MODE", "sandbox").strip().lower()  # sandbox | live
BASE_URL = os.getenv("GENIUSPAY_BASE_URL", "https://pay.genius.ci/api/v1/merchant").rstrip("/")
PUBLIC_URL = os.getenv("PUBLIC_BASE_URL", "https://api-marabo.onrender.com").rstrip("/")
TEST_KEY = os.getenv("PAYMENT_TEST_KEY", "")


def _env(name: str, mode: str) -> str:
    """GENIUSPAY_API_KEY_SANDBOX, GENIUSPAY_API_KEY_LIVE…
    En live, accepte aussi les anciennes variables GENIUS_API_KEY / GENIUS_API_SECRET."""
    value = os.getenv(f"GENIUSPAY_{name}_{mode.upper()}", "").strip()
    if not value and mode == "live" and name in ("API_KEY", "API_SECRET"):
        value = os.getenv(f"GENIUS_{name}", "").strip()
    return value


def api_keys(mode: str = MODE):
    return _env("API_KEY", mode), _env("API_SECRET", mode)


def webhook_secret(mode: str) -> str:
    return _env("WEBHOOK_SECRET", mode)


# Motifs de paiement acceptés et bornes de montant (XOF)
PURPOSES = {
    "topup": {"label": "Recharge Marabo Pay", "min": 200, "max": 1_000_000},
    "donation": {"label": "Don à Marabo", "min": 200, "max": 1_000_000},
    "premium": {"label": "Marabo Premium", "min": 200, "max": 1_000_000},
    "boost": {"label": "Boost d'annonce", "min": 200, "max": 1_000_000},
    "banner": {"label": "Affiche sponsorisée", "min": 200, "max": 1_000_000},
    "annonce": {"label": "Publication d'annonce", "min": 200, "max": 1_000_000},
    "test": {"label": "Paiement de test Marabo", "min": 200, "max": 200},
}

# -----------------------------------------------------------------------------
# 🏷️ CATALOGUE : les prix sont fixés ICI, jamais par l'app
# -----------------------------------------------------------------------------
PREMIUM_PLANS = {
    "mensuel": {"name": "Mensuel", "price": 2000, "days": 30},
    "trimestriel": {"name": "Trimestriel", "price": 5000, "days": 90},
    "annuel": {"name": "Annuel", "price": 7000, "days": 365},
}
BOOST_PACKS = {
    "eclair": {"name": "Pack Éclair", "price": 1500, "days": 3},
    "visibilite": {"name": "Pack Visibilité", "price": 3000, "days": 7},
    "maximum": {"name": "Pack Maximum", "price": 6000, "days": 15},
}
BANNER_PRICE_PER_DAY = 1000
BANNER_DAYS = (1, 3, 7, 14, 30)

# Publication d'annonces (entreprises) : 50 gratuites, puis 250 F l'annonce,
# illimité avec Premium. Compteur : users/{uid}.freeAnnoncesUsed (serveur seul).
FREE_ANNONCES = 50
ANNONCE_PRICE = 250

TIMESTAMP_TOLERANCE = 300  # 5 minutes


def init_paiements(db, push=None):
    global _db, _push
    _db = db
    _push = push
    k, s = api_keys()
    print(f"💳 GeniusPay : mode {MODE.upper()} · clés {'OK' if k and s else 'MANQUANTES'} · "
          f"webhook sandbox {'OK' if webhook_secret('sandbox') else 'absent'} · "
          f"webhook live {'OK' if webhook_secret('live') else 'absent'}")


# -----------------------------------------------------------------------------
# 🔐 OUTILS
# -----------------------------------------------------------------------------
def _uid_from_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return fb_auth.verify_id_token(authorization.split(" ", 1)[1].strip())["uid"]
    except Exception as e:
        print(f"⚠️ Paiement : jeton refusé : {e}")
        return None


def _check_test_key(key: str):
    if not TEST_KEY or not hmac.compare_digest(str(key), TEST_KEY):
        raise HTTPException(status_code=403, detail="Clé de test invalide (PAYMENT_TEST_KEY)")


def _gp_headers(mode: str) -> dict:
    key, secret = api_keys(mode)
    if not key or not secret:
        raise HTTPException(status_code=503, detail=f"Clés GeniusPay {mode} non configurées sur le serveur")
    return {"X-API-Key": key, "X-API-Secret": secret, "Content-Type": "application/json", "Accept": "application/json"}


def _php_json(obj) -> str:
    """Encodage façon json_encode de PHP (barres échappées, unicode \\uXXXX)."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).replace("/", "\\/")


def verify_signature(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Signature = HMAC-SHA256(timestamp + "." + corps, secret), en hexadécimal.
    On vérifie d'abord sur le corps brut (méthode officielle), puis sur les
    ré-encodages JSON usuels au cas où GeniusPay signe un JSON ré-encodé."""
    if not (secret and timestamp and signature):
        return False
    sig = signature.strip().lower()
    if sig.startswith("sha256="):
        sig = sig[7:]
    candidates = [raw_body]
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
        candidates += [
            _php_json(parsed).encode("utf-8"),
            json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            json.dumps(parsed, separators=(",", ":")).encode("utf-8"),
        ]
    except Exception:
        pass
    for body in candidates:
        expected = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, sig):
            return True
    return False


def _timestamp_ok(ts: str) -> bool:
    try:
        value = float(ts)
    except Exception:
        return False
    if value > 10_000_000_000:  # millisecondes
        value /= 1000
    return abs(time.time() - value) <= TIMESTAMP_TOLERANCE


# -----------------------------------------------------------------------------
# 💳 CRÉATION D'UN PAIEMENT
# -----------------------------------------------------------------------------
def create_payment(user_id: str, purpose: str, amount: int, *, mode: str = MODE,
                   customer: Optional[dict] = None, extra: Optional[dict] = None,
                   label: Optional[str] = None) -> dict:
    if purpose not in PURPOSES:
        raise HTTPException(status_code=400, detail="Motif de paiement inconnu")
    rule = PURPOSES[purpose]
    try:
        amount = int(amount)
    except Exception:
        raise HTTPException(status_code=400, detail="Montant invalide")
    if amount < rule["min"] or amount > rule["max"]:
        raise HTTPException(status_code=400, detail=f"Montant hors limites ({rule['min']} – {rule['max']} F)")

    label = label or rule["label"]
    payment_id = uuid.uuid4().hex
    ref = _db.collection("paymentOrders").document(payment_id)
    ref.set({
        "userId": user_id,
        "purpose": purpose,
        "label": label,
        "amount": amount,
        "currency": "XOF",
        "environment": mode,
        "status": "creating",
        "extra": extra or {},
        "createdAt": firestore.SERVER_TIMESTAMP,
    })

    body = {
        "amount": amount,
        "currency": "XOF",
        "description": f"{label} · Marabo"[:120],
        "success_url": f"{PUBLIC_URL}/payments/return?result=success&pid={payment_id}",
        "error_url": f"{PUBLIC_URL}/payments/return?result=error&pid={payment_id}",
        "metadata": {"payment_id": payment_id, "user_id": user_id, "purpose": purpose},
    }
    if customer:
        body["customer"] = {k: v for k, v in customer.items() if v}

    try:
        res = requests.post(f"{BASE_URL}/payments", json=body, headers=_gp_headers(mode), timeout=30)
        data = res.json() if res.content else {}
    except HTTPException:
        ref.update({"status": "error", "error": "keys_missing"})
        raise
    except Exception as e:
        ref.update({"status": "error", "error": str(e)[:300]})
        raise HTTPException(status_code=502, detail="GeniusPay injoignable, réessaie dans un instant")

    if res.status_code not in (200, 201) or not isinstance(data.get("data"), dict):
        ref.update({"status": "error", "error": json.dumps(data)[:500], "httpStatus": res.status_code})
        print(f"❌ GeniusPay création refusée ({res.status_code}) : {data}")
        raise HTTPException(status_code=502, detail=(data.get("message") or data.get("error") or "Paiement refusé par GeniusPay"))

    d = data["data"]
    checkout = d.get("checkout_url") or d.get("payment_url")
    ref.update({
        "status": "pending",
        "gpReference": d.get("reference"),
        "gpId": d.get("id"),
        "checkoutUrl": checkout,
        "expiresAt": d.get("expires_at"),
        "fees": d.get("fees"),
    })
    return {"paymentId": payment_id, "reference": d.get("reference"), "checkoutUrl": checkout,
            "environment": mode, "amount": amount, "label": label}


def _build_order(uid: str, user: dict, payload: dict) -> dict:
    """Vérifie la demande et calcule le montant côté serveur.
    Renvoie {purpose, amount, label, extra}."""
    purpose = str(payload.get("purpose") or "")
    is_company = str(user.get("type") or "").lower() == "entreprise"

    if purpose == "topup":
        amount = _int(payload.get("amount"))
        return {"purpose": purpose, "amount": amount, "label": "Recharge Marabo Pay", "extra": {}}

    if purpose == "donation":
        amount = _int(payload.get("amount"))
        message = str(payload.get("message") or "").strip()[:300]
        anonymous = bool(payload.get("anonymous"))
        name = str(user.get("username") or user.get("name") or "")
        return {"purpose": purpose, "amount": amount, "label": "Don à Marabo",
                "extra": {"message": message, "anonymous": anonymous, "userName": name}}

    if purpose == "premium":
        if not is_company:
            raise HTTPException(status_code=403, detail="Marabo Premium est réservé aux entreprises")
        plan = PREMIUM_PLANS.get(str(payload.get("plan") or ""))
        if not plan:
            raise HTTPException(status_code=400, detail="Formule Premium inconnue")
        return {"purpose": purpose, "amount": plan["price"], "label": f"Marabo Premium {plan['name']}",
                "extra": {"plan": payload.get("plan"), "planName": plan["name"], "days": plan["days"]}}

    if purpose == "boost":
        pack = BOOST_PACKS.get(str(payload.get("pack") or ""))
        if not pack:
            raise HTTPException(status_code=400, detail="Forfait de boost inconnu")
        annonce_id = str(payload.get("annonceId") or "")
        snap = _db.collection("opportunities").document(annonce_id).get() if annonce_id else None
        if not snap or not snap.exists or (snap.to_dict() or {}).get("postedBy") != uid:
            raise HTTPException(status_code=404, detail="Annonce introuvable")
        title = str((snap.to_dict() or {}).get("title") or "Annonce")
        return {"purpose": purpose, "amount": pack["price"], "label": f"{pack['name']} · {title}"[:90],
                "extra": {"pack": payload.get("pack"), "packName": pack["name"], "days": pack["days"],
                          "annonceId": annonce_id, "annonceTitle": title[:200]}}

    if purpose == "annonce":
        if not is_company:
            raise HTTPException(status_code=403, detail="Réservé aux entreprises")
        return {"purpose": purpose, "amount": ANNONCE_PRICE, "label": "Publication d'annonce", "extra": {}}

    if purpose == "banner":
        banner_id = str(payload.get("bannerId") or "")
        snap = _db.collection("banners").document(banner_id).get() if banner_id else None
        b = (snap.to_dict() or {}) if snap and snap.exists else None
        if not b or b.get("ownerId") != uid:
            raise HTTPException(status_code=404, detail="Affiche introuvable")
        if b.get("status") != "pending_payment":
            raise HTTPException(status_code=409, detail="Cette affiche est déjà payée")
        days = _int(b.get("durationDays"))
        if days not in BANNER_DAYS:
            raise HTTPException(status_code=400, detail="Durée d'affiche invalide")
        title = str(b.get("title") or "Affiche")
        return {"purpose": purpose, "amount": days * BANNER_PRICE_PER_DAY,
                "label": f"Affiche {days} jour{'s' if days > 1 else ''} · {title}"[:90],
                "extra": {"bannerId": banner_id, "days": days, "bannerTitle": title[:200]}}

    raise HTTPException(status_code=400, detail="Motif de paiement inconnu")


def _int(value) -> int:
    try:
        return int(float(value))
    except Exception:
        raise HTTPException(status_code=400, detail="Montant invalide")


@router.post("/payments/create")
def payments_create(payload: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Appelé par l'app (utilisateur connecté).
    Corps selon le motif :
      topup    { purpose, amount }
      donation { purpose, amount, message?, anonymous? }
      premium  { purpose, plan: mensuel|trimestriel|annuel }
      boost    { purpose, pack: eclair|visibilite|maximum, annonceId }
      banner   { purpose, bannerId }
    """
    uid = _uid_from_token(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    user = _db.collection("users").document(uid).get().to_dict() or {}
    order = _build_order(uid, user, payload or {})
    customer = {"name": user.get("username") or user.get("name"), "email": user.get("email")}
    result = create_payment(uid, order["purpose"], order["amount"], customer=customer,
                            extra=order["extra"], label=order["label"])
    return {"status": "success", **result}


# -----------------------------------------------------------------------------
# ✅ VALIDATION (commune au webhook et à la vérification manuelle)
# -----------------------------------------------------------------------------
FINAL_FAIL = {"payment.failed": "failed", "payment.cancelled": "cancelled", "payment.expired": "expired"}


def _now():
    return datetime.now(timezone.utc)


def _as_datetime(value) -> Optional[datetime]:
    """Accepte un Timestamp Firestore, un datetime ou une chaîne ISO."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _log_tx(transaction, pay_ref, pay: dict, gp: dict, tx_type: str, amount: int, **fields):
    doc = {
        "user_id": pay["userId"],
        "amount": amount,
        "type": tx_type,
        "provider": "geniuspay",
        "reference": gp.get("reference") or pay.get("gpReference"),
        "payment_id": pay_ref.id,
        "status": "completed",
        "date": firestore.SERVER_TIMESTAMP,
    }
    doc.update(fields)
    transaction.set(_db.collection("transactions").document(f"gp_{pay_ref.id}"), doc)


def _fulfil(transaction, pay_ref, pay: dict, gp: dict) -> dict:
    """Effets d'un paiement réussi, écrits dans la même transaction que le statut.
    Toutes les lectures sont faites AVANT la première écriture (règle Firestore).
    Si la cible a disparu (annonce ou affiche supprimée), le montant est crédité
    sur le solde Marabo Pay : l'argent n'est jamais perdu."""
    purpose = pay.get("purpose")
    amount = int(pay.get("amount") or 0)
    extra = pay.get("extra") or {}
    uid = pay["userId"]
    user_ref = _db.collection("users").document(uid)
    now = _now()

    def credit_wallet(reason: str) -> dict:
        transaction.set(user_ref, {"wallet_balance": firestore.Increment(amount)}, merge=True)
        _log_tx(transaction, pay_ref, pay, gp, "top_up", amount, note=reason)
        return {"walletCredited": amount, "reason": reason}

    if purpose == "topup":
        return credit_wallet("recharge")

    if purpose == "premium":
        user = user_ref.get(transaction=transaction).to_dict() or {}
        days = int(extra.get("days") or 30)
        current_end = _as_datetime(user.get("premiumEnd"))
        active = bool(user.get("isPremium")) and current_end and current_end > now
        start = current_end if active else now
        end = start + timedelta(days=days)
        transaction.set(user_ref, {
            "isPremium": True,
            "plan": extra.get("planName") or "Mensuel",
            "premiumStart": (user.get("premiumStart") if active else now.isoformat()),
            "premiumEnd": end.isoformat(),
        }, merge=True)
        _log_tx(transaction, pay_ref, pay, gp, "premium", amount, package_name=f"Premium {extra.get('planName', '')}".strip())
        return {"premiumEnd": end.isoformat(), "plan": extra.get("planName")}

    if purpose == "boost":
        ann_ref = _db.collection("opportunities").document(str(extra.get("annonceId") or "-"))
        snap = ann_ref.get(transaction=transaction)
        ann = snap.to_dict() if snap.exists else None
        if not ann or ann.get("postedBy") != uid:
            return credit_wallet("annonce introuvable : montant crédité sur le solde")
        days = int(extra.get("days") or 3)
        current_end = _as_datetime(ann.get("boostEndsAt") or ann.get("boostEndDate"))
        start = current_end if (ann.get("isBoosted") and current_end and current_end > now) else now
        end = start + timedelta(days=days)
        transaction.update(ann_ref, {"isBoosted": True, "boostEndsAt": end, "lastBoostDate": firestore.SERVER_TIMESTAMP})
        _log_tx(transaction, pay_ref, pay, gp, "boost_ad", amount,
                annonce_id=ann_ref.id, annonce_title=ann.get("title") or "Annonce", package_name=extra.get("packName"))
        return {"boostEndsAt": end.isoformat(), "annonceTitle": ann.get("title")}

    if purpose == "banner":
        b_ref = _db.collection("banners").document(str(extra.get("bannerId") or "-"))
        snap = b_ref.get(transaction=transaction)
        b = snap.to_dict() if snap.exists else None
        if not b or b.get("ownerId") != uid or b.get("status") != "pending_payment":
            return credit_wallet("affiche déjà payée ou supprimée : montant crédité sur le solde")
        days = int(b.get("durationDays") or extra.get("days") or 1)
        end = now + timedelta(days=days)
        transaction.update(b_ref, {"status": "active", "paidAt": firestore.SERVER_TIMESTAMP,
                                   "dateStart": now, "dateEnd": end, "paymentId": pay_ref.id})
        _log_tx(transaction, pay_ref, pay, gp, "ad_banner", amount, banner_id=b_ref.id,
                annonce_title=b.get("title") or "Affiche", package_name=f"{days} jour{'s' if days > 1 else ''}")
        return {"dateEnd": end.isoformat()}

    if purpose == "annonce":
        # Crédit de publication payé directement : l'app l'utilise aussitôt
        transaction.set(_db.collection("publishCredits").document(pay_ref.id), {
            "userId": uid, "type": "paid", "via": "geniuspay", "used": False,
            "paymentId": pay_ref.id, "createdAt": firestore.SERVER_TIMESTAMP,
        })
        _log_tx(transaction, pay_ref, pay, gp, "publish_ad", amount)
        return {"creditId": pay_ref.id}

    if purpose == "donation":
        transaction.set(_db.collection("donations").document(pay_ref.id), {
            "userId": uid,
            "userName": extra.get("userName") or "",
            "amount": amount,
            "currency": "XOF",
            "message": extra.get("message") or "",
            "anonymous": bool(extra.get("anonymous")),
            "channel": "geniuspay",
            "status": "confirmed",
            "paymentId": pay_ref.id,
            "reference": gp.get("reference") or pay.get("gpReference"),
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        })
        return {"donation": True}

    return {}  # "test" : rien d'autre que le statut


def apply_result(payment_id: str, status: str, gp: dict, source: str) -> str:
    """Passe un paiement à paid / failed / cancelled / expired, une seule fois."""
    pay_ref = _db.collection("paymentOrders").document(payment_id)

    @firestore.transactional
    def _tx(transaction):
        snap = pay_ref.get(transaction=transaction)
        if not snap.exists:
            return "unknown_payment"
        pay = snap.to_dict()
        current = pay.get("status")
        if current == "paid":
            return "already_paid"
        if status == "paid":
            # Contrôles anti-fraude : montant, devise, environnement
            paid_amount = float(gp.get("amount") or 0)
            if paid_amount + 0.5 < float(pay.get("amount") or 0):
                transaction.update(pay_ref, {"status": "amount_mismatch", "gpAmount": paid_amount, "updatedAt": firestore.SERVER_TIMESTAMP})
                return "amount_mismatch"
            if (gp.get("currency") or "XOF") != "XOF":
                transaction.update(pay_ref, {"status": "currency_mismatch", "updatedAt": firestore.SERVER_TIMESTAMP})
                return "currency_mismatch"
            result = _fulfil(transaction, pay_ref, pay, gp)
            transaction.update(pay_ref, {
                "status": "paid",
                "result": result,
                "paidAt": firestore.SERVER_TIMESTAMP,
                "paidVia": source,
                "gpReference": gp.get("reference") or pay.get("gpReference"),
                "provider": gp.get("provider") or gp.get("payment_method"),
                "fees": gp.get("fees"),
                "netAmount": gp.get("net_amount"),
                "customerPhone": gp.get("customer_phone"),
            })
            return "paid"
        if current in ("pending", "creating"):
            transaction.update(pay_ref, {"status": status, "updatedAt": firestore.SERVER_TIMESTAMP})
            return status
        return f"ignored_{current}"

    return _tx(_db.transaction())


# -----------------------------------------------------------------------------
# 🔔 WEBHOOK GENIUSPAY
#  URL à déclarer dans le tableau de bord (sandbox ET live) :
#      https://api-marabo.onrender.com/webhook/geniuspay
# -----------------------------------------------------------------------------
async def handle_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    event = request.headers.get("x-webhook-event", "")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return JSONResponse({"detail": "Corps illisible"}, status_code=400)

    env = (request.headers.get("x-webhook-environment") or payload.get("environment") or "").lower()
    env = "live" if env in ("live", "production", "prod") else "sandbox"
    event = event or payload.get("event", "")

    if not signature or not timestamp or not event:
        print("⚠️ Webhook GeniusPay : en-têtes manquants")
        return JSONResponse({"detail": "Required header is not present."}, status_code=400)

    if not verify_signature(raw, timestamp, signature, webhook_secret(env)):
        print(f"🚫 Webhook GeniusPay REFUSÉ : signature invalide (env {env}, événement {event})")
        return JSONResponse({"detail": "Invalid signature"}, status_code=401)

    if not _timestamp_ok(timestamp):
        print(f"🚫 Webhook GeniusPay REFUSÉ : horodatage trop ancien ({timestamp})")
        return JSONResponse({"detail": "Timestamp too old"}, status_code=400)

    event_id = str(payload.get("id") or request.headers.get("x-webhook-delivery") or "")
    data = payload.get("data") or {}
    log_ref = _db.collection("webhookEvents").document(event_id or uuid.uuid4().hex)

    # Idempotence : un même événement n'est traité qu'une fois
    try:
        log_ref.create({
            "event": event,
            "environment": env,
            "reference": data.get("reference"),
            "status": data.get("status"),
            "amount": data.get("amount"),
            "receivedAt": firestore.SERVER_TIMESTAMP,
            "outcome": "processing",
        })
    except Exception:
        existing = (log_ref.get().to_dict() or {}).get("outcome")
        if existing and existing != "processing" and not existing.startswith("error"):
            return {"success": True, "message": "Already processed"}

    try:
        outcome = _process_event(event, env, data)
        log_ref.update({"outcome": outcome, "processedAt": firestore.SERVER_TIMESTAMP})
        print(f"🔔 Webhook GeniusPay {event} ({env}) → {outcome}")
        return {"success": True, "message": "Webhook processed successfully", "outcome": outcome}
    except Exception as e:
        log_ref.update({"outcome": f"error: {str(e)[:200]}"})
        print(f"❌ Webhook GeniusPay : erreur de traitement : {e}")
        # 500 → GeniusPay réessaiera ; le traitement est idempotent
        return JSONResponse({"detail": "Failed to process webhook"}, status_code=500)


def _process_event(event: str, env: str, data: dict) -> str:
    if event == "webhook.test":
        return "test_ok"
    if not event.startswith("payment."):
        return "ignored_event"

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    payment_id = str(metadata.get("payment_id") or "")

    # Paiement créé par l'ancienne version de l'app (pas de payment_id) :
    # on le rattache par la référence GeniusPay, une seule fois.
    if not payment_id:
        payment_id = _legacy_payment(env, data, metadata)
        if not payment_id:
            return "no_payment_id"

    pay = _db.collection("paymentOrders").document(payment_id).get()
    if pay.exists and pay.to_dict().get("environment") != env:
        return "environment_mismatch"

    if event == "payment.success":
        if (data.get("status") or "completed") != "completed":
            return "success_not_completed"
        return apply_result(payment_id, "paid", data, "webhook")
    if event in FINAL_FAIL:
        return apply_result(payment_id, FINAL_FAIL[event], data, "webhook")
    return "ignored_event"


def _legacy_payment(env: str, data: dict, metadata: dict) -> Optional[str]:
    reference = str(data.get("reference") or "")
    user_id = str(metadata.get("user_id") or "")
    if not reference or not user_id:
        return None
    payment_id = "legacy_" + hashlib.sha256(reference.encode()).hexdigest()[:24]
    ref = _db.collection("paymentOrders").document(payment_id)
    try:
        ref.create({
            "userId": user_id,
            "purpose": "topup",
            "label": "Recharge Marabo Pay",
            "amount": int(float(data.get("amount") or 0)),
            "currency": data.get("currency") or "XOF",
            "environment": env,
            "status": "pending",
            "gpReference": reference,
            "legacy": True,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
    except Exception:
        pass  # déjà créé : apply_result garantit qu'on ne crédite qu'une fois
    return payment_id


# -----------------------------------------------------------------------------
# 🔎 STATUT (l'app interroge ; filet de sécurité si le webhook tarde)
# -----------------------------------------------------------------------------
def sync_with_geniuspay(payment_id: str) -> dict:
    snap = _db.collection("paymentOrders").document(payment_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    pay = snap.to_dict()
    if pay.get("status") == "pending" and pay.get("gpReference"):
        try:
            res = requests.get(f"{BASE_URL}/payments/{pay['gpReference']}", headers=_gp_headers(pay.get("environment", MODE)), timeout=20)
            d = (res.json() or {}).get("data") or {}
            gp_status = d.get("status")
            if gp_status == "completed":
                apply_result(payment_id, "paid", d, "status_check")
            elif gp_status in ("failed", "cancelled", "expired"):
                apply_result(payment_id, gp_status, d, "status_check")
        except HTTPException:
            raise
        except Exception as e:
            print(f"⚠️ Vérification GeniusPay impossible pour {payment_id} : {e}")
        pay = _db.collection("paymentOrders").document(payment_id).get().to_dict()
    return pay


@router.get("/payments/{payment_id}/status")
def payment_status(payment_id: str, authorization: Optional[str] = Header(None)):
    uid = _uid_from_token(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    snap = _db.collection("paymentOrders").document(payment_id).get()
    if not snap.exists or snap.to_dict().get("userId") != uid:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    pay = sync_with_geniuspay(payment_id)
    return {
        "status": pay.get("status"),
        "amount": pay.get("amount"),
        "purpose": pay.get("purpose"),
        "label": pay.get("label"),
        "reference": pay.get("gpReference"),
        "provider": pay.get("provider"),
        "checkoutUrl": pay.get("checkoutUrl") if pay.get("status") == "pending" else None,
        "result": pay.get("result") or {},
    }


@router.get("/payments/catalog")
def payments_catalog():
    """Prix officiels, lus par l'app pour l'affichage."""
    return {
        "premium": PREMIUM_PLANS,
        "boost": BOOST_PACKS,
        "bannerPricePerDay": BANNER_PRICE_PER_DAY,
        "bannerDays": list(BANNER_DAYS),
        "freeAnnonces": FREE_ANNONCES,
        "annoncePrice": ANNONCE_PRICE,
    }


# -----------------------------------------------------------------------------
# 📝 CRÉDITS DE PUBLICATION D'ANNONCE
#   L'app ne peut créer une annonce qu'avec un crédit publishCredits/{id} non
#   utilisé, délivré ici (règles Firestore). Ordre de décision :
#     1. un crédit déjà délivré et pas encore utilisé → on le rend
#     2. Premium actif                               → crédit « premium »
#     3. moins de 50 gratuites utilisées             → crédit « free »
#     4. method = "wallet" et solde ≥ 250 F          → débit + crédit « paid »
#     5. sinon → 402 : l'app propose solde / paiement direct / Premium
# -----------------------------------------------------------------------------
def _premium_active(user: dict) -> bool:
    end = _as_datetime(user.get("premiumEnd"))
    return bool(user.get("isPremium")) and end is not None and end > _now()


def _quota(user: dict) -> dict:
    used = int(user.get("freeAnnoncesUsed") or 0)
    return {
        "freeTotal": FREE_ANNONCES,
        "freeUsed": used,
        "freeLeft": max(0, FREE_ANNONCES - used),
        "premium": _premium_active(user),
        "price": ANNONCE_PRICE,
        "balance": int(user.get("wallet_balance") or 0),
    }


@router.get("/annonces/quota")
def annonces_quota(authorization: Optional[str] = Header(None)):
    uid = _uid_from_token(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return _quota(_db.collection("users").document(uid).get().to_dict() or {})


@router.post("/annonces/credit")
def annonces_credit(payload: dict = Body(default={}), authorization: Optional[str] = Header(None)):
    uid = _uid_from_token(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    method = str((payload or {}).get("method") or "auto")
    user_ref = _db.collection("users").document(uid)
    first = user_ref.get().to_dict() or {}
    if str(first.get("type") or "").lower() != "entreprise":
        raise HTTPException(status_code=403, detail="Réservé aux entreprises")

    # 1. Crédit déjà délivré mais pas encore utilisé (publication interrompue)
    for doc in _db.collection("publishCredits").where("userId", "==", uid).where("used", "==", False).limit(1).stream():
        return {"creditId": doc.id, "type": (doc.to_dict() or {}).get("type"), **_quota(first)}

    credit_ref = _db.collection("publishCredits").document(uuid.uuid4().hex)

    @firestore.transactional
    def _tx(transaction):
        user = user_ref.get(transaction=transaction).to_dict() or {}
        q = _quota(user)
        base = {"userId": uid, "used": False, "createdAt": firestore.SERVER_TIMESTAMP}
        if q["premium"]:
            transaction.set(credit_ref, {**base, "type": "premium"})
            return "premium", q
        if q["freeLeft"] > 0:
            n = q["freeUsed"] + 1
            transaction.set(user_ref, {"freeAnnoncesUsed": firestore.Increment(1)}, merge=True)
            transaction.set(credit_ref, {**base, "type": "free", "freeIndex": n})
            transaction.set(_db.collection("transactions").document(f"free_{credit_ref.id}"), {
                "user_id": uid, "amount": 0, "type": "publish_free", "free_index": n,
                "free_total": FREE_ANNONCES, "status": "completed", "date": firestore.SERVER_TIMESTAMP,
            })
            q = {**q, "freeUsed": n, "freeLeft": FREE_ANNONCES - n}
            return "free", q
        if method == "wallet" and q["balance"] >= ANNONCE_PRICE:
            transaction.set(user_ref, {"wallet_balance": firestore.Increment(-ANNONCE_PRICE)}, merge=True)
            transaction.set(credit_ref, {**base, "type": "paid", "via": "wallet"})
            transaction.set(_db.collection("transactions").document(f"pub_{credit_ref.id}"), {
                "user_id": uid, "amount": ANNONCE_PRICE, "type": "publish_ad", "status": "completed",
                "date": firestore.SERVER_TIMESTAMP,
            })
            q = {**q, "balance": q["balance"] - ANNONCE_PRICE}
            return "paid", q
        return None, q

    kind, q = _tx(_db.transaction())
    if kind is None:
        return JSONResponse({"detail": "Tes annonces gratuites sont utilisées.", "needPayment": True, **q}, status_code=402)

    # Prévenir quand il ne reste que 5 annonces gratuites, puis à la dernière
    if kind == "free" and q["freeLeft"] in (5, 0) and _push:
        try:
            if q["freeLeft"] == 5:
                _push(uid, "Plus que 5 annonces gratuites",
                      "Ensuite, chaque annonce coûte 250 F. Recharge ton solde Marabo Pay ou passe Premium pour publier sans limite.",
                      {"type": "quota_annonces"})
            else:
                _push(uid, "Tes 50 annonces gratuites sont utilisées",
                      "Les prochaines annonces coûtent 250 F, ou sont illimitées avec Marabo Premium.",
                      {"type": "quota_annonces"})
        except Exception as e:
            print(f"⚠️ Notification quota annonces : {e}")

    return {"creditId": credit_ref.id, "type": kind, **q}


# -----------------------------------------------------------------------------
# ↩️ PAGES DE RETOUR (après la page GeniusPay)
# -----------------------------------------------------------------------------
@router.get("/payments/return", response_class=HTMLResponse)
def payment_return(result: str = "success", pid: str = ""):
    ok = result == "success"
    title = "Paiement reçu ✅" if ok else "Paiement non abouti"
    text = ("Ton paiement est en cours de validation. Tu peux revenir dans l’application Marabo."
            if ok else "Le paiement a été annulé ou a échoué. Aucun montant n’a été débité. Tu peux réessayer depuis l’application Marabo.")
    return _page(title, f"<p>{text}</p>")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;background:#0A0D14;color:#F2F4F8;margin:0;padding:24px}}
.c{{max-width:760px;margin:0 auto}}h1{{font-size:24px}}p{{color:#C9CFDB;line-height:1.5}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}}td,th{{border-bottom:1px solid #222a3a;padding:7px;text-align:left}}
.ok{{color:#6BE69A}}.ko{{color:#FF7A7F}}.btn{{display:inline-block;background:#4C8DFF;color:#fff;padding:12px 18px;border-radius:12px;text-decoration:none;font-weight:700;border:0;font-size:15px;cursor:pointer}}
code{{background:#1B2130;padding:2px 6px;border-radius:6px}}</style></head><body><div class="c"><h1>{html.escape(title)}</h1>{body}</div></body></html>"""


# -----------------------------------------------------------------------------
# 🧪 PAGE DE TEST (protégée par PAYMENT_TEST_KEY)
#   https://api-marabo.onrender.com/payments/test?key=TA_CLE
# -----------------------------------------------------------------------------
@router.get("/payments/test", response_class=HTMLResponse)
def test_page(key: str = ""):
    _check_test_key(key)
    yes = '<span class="ok">✓ présent</span>'
    no = '<span class="ko">✗ absent</span>'
    ks, ss = api_keys("sandbox")
    kl, sl = api_keys("live")
    config = f"""<table>
<tr><th>Réglage</th><th>Sandbox</th><th>Live</th></tr>
<tr><td>Clé API (pk_)</td><td>{yes if ks else no}</td><td>{yes if kl else no}</td></tr>
<tr><td>Clé secrète (sk_)</td><td>{yes if ss else no}</td><td>{yes if sl else no}</td></tr>
<tr><td>Secret webhook (whsec_)</td><td>{yes if webhook_secret('sandbox') else no}</td><td>{yes if webhook_secret('live') else no}</td></tr>
</table><p>Mode actif de l’application : <b>{MODE.upper()}</b> · Webhook : <code>{PUBLIC_URL}/webhook/geniuspay</code></p>"""

    pays = _db.collection("paymentOrders").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(10).stream()
    rows = "".join(
        f"<tr><td>{html.escape(str(p.to_dict().get('purpose')))}</td><td>{p.to_dict().get('amount')}</td>"
        f"<td>{html.escape(str(p.to_dict().get('environment')))}</td><td><b>{html.escape(str(p.to_dict().get('status')))}</b></td>"
        f"<td>{html.escape(str(p.to_dict().get('gpReference') or ''))}</td><td>{html.escape(str(p.to_dict().get('paidVia') or ''))}</td></tr>"
        for p in pays)
    evs = _db.collection("webhookEvents").order_by("receivedAt", direction=firestore.Query.DESCENDING).limit(10).stream()
    erows = "".join(
        f"<tr><td>{html.escape(str(e.to_dict().get('event')))}</td><td>{html.escape(str(e.to_dict().get('environment')))}</td>"
        f"<td>{html.escape(str(e.to_dict().get('reference') or ''))}</td><td><b>{html.escape(str(e.to_dict().get('outcome')))}</b></td></tr>"
        for e in evs)

    body = f"""<p>Page réservée aux tests. Elle crée un vrai paiement de <b>200 F</b> dans l’environnement choisi,
puis affiche ce que le webhook a fait.</p>{config}
<form method="post" action="/payments/test/create?key={html.escape(key)}&mode=sandbox" style="margin:18px 0">
<button class="btn">Lancer un paiement test SANDBOX (200 F)</button></form>
<form method="post" action="/payments/test/create?key={html.escape(key)}&mode=live" onsubmit="return confirm('Paiement RÉEL de 200 F en LIVE ?')">
<button class="btn" style="background:#B45309">Lancer un paiement RÉEL LIVE (200 F)</button></form>
<h2>10 derniers paiements</h2><table><tr><th>Motif</th><th>Montant</th><th>Env.</th><th>Statut</th><th>Référence</th><th>Validé par</th></tr>{rows}</table>
<h2>10 derniers webhooks acceptés</h2><table><tr><th>Événement</th><th>Env.</th><th>Référence</th><th>Résultat</th></tr>{erows}</table>
<p>Les webhooks refusés (signature fausse) n’apparaissent pas ici : regarde les journaux Render (« 🚫 Webhook GeniusPay REFUSÉ »).</p>
<p><a class="btn" href="/payments/test?key={html.escape(key)}" style="background:#1B2130">Actualiser</a></p>"""
    return _page("Paiements GeniusPay · test", body)


@router.post("/payments/test/create", response_class=HTMLResponse)
def test_create(key: str = "", mode: str = "sandbox"):
    _check_test_key(key)
    mode = "live" if mode == "live" else "sandbox"
    result = create_payment("test-page", "test", 200, mode=mode)
    url = html.escape(result["checkoutUrl"] or "")
    return _page("Paiement test créé", f"""<p>Paiement <code>{result['paymentId']}</code> ({mode}) créé chez GeniusPay
(référence <code>{html.escape(str(result['reference']))}</code>).</p>
<p><a class="btn" href="{url}" target="_blank">Ouvrir la page de paiement GeniusPay</a></p>
<p>Paie (ou annule), puis reviens sur la page de test et clique « Actualiser ».</p>
<p><a href="/payments/test?key={html.escape(key)}">← Retour à la page de test</a></p>""")
