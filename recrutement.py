# =============================================================================
#  MARABO — Module Recrutement (phase A)
#  À placer à côté de main.py. Branché dans main.py par :
#      from recrutement import ...
#      init_recrutement(db, send_push_to_user)
#      app.include_router(recrutement_router)
#
#  Contenu :
#   • vérification du jeton Firebase (Authorization: Bearer <idToken>)
#   • photo du profil au moment de la candidature (profileSnapshot)
#   • calcul du score de correspondance (l'âge n'entre JAMAIS dans le score)
#   • liens temporaires (15 min) vers les CV / lettres, réservés à l'entreprise
#     et au candidat concernés
#   • recalcul des scores quand l'entreprise modifie ses critères
#   • rappels d'entretien 24 h et 1 h avant (candidat + entreprise)
#  Phase B :
#   • sessions d'entretiens : le candidat réserve lui-même son créneau
#   • relance la veille de la fin des réservations
#   • clôture d'une offre (manuelle « Pourvu » ou 7 jours après la fin)
#  Phase C :
#   • CVthèque anonyme : recherche, profil, invitation à postuler (quota/jour)
#   • le téléphone de l'entreprise ne reçoit JAMAIS nom, photo, contacts, CV ni âge
# =============================================================================
import hashlib
import hmac
import os
import random
import re
import string
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, Body, Header, HTTPException
from firebase_admin import auth as fb_auth
from firebase_admin import firestore, storage

router = APIRouter()

_db = None
_push = None
_scheduler = None

# Mettre REQUIRE_AUTH_APPLY=1 sur Render quand tous les utilisateurs auront
# la nouvelle version de l'app : /apply refusera alors les envois sans jeton.
REQUIRE_AUTH_APPLY = os.getenv("REQUIRE_AUTH_APPLY", "0") == "1"

MATCH_VERSION = 1


def init_recrutement(db, push_fn):
    """À appeler une fois dans main.py, après la définition de send_push_to_user."""
    global _db, _push
    _db = db
    _push = push_fn


# -----------------------------------------------------------------------------
# 🔐 AUTHENTIFICATION
# -----------------------------------------------------------------------------
def uid_from_header(authorization: Optional[str]) -> Optional[str]:
    """Renvoie l'uid Firebase si le jeton est valide, sinon None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        return fb_auth.verify_id_token(token)["uid"]
    except Exception as e:
        print(f"⚠️ Jeton Firebase refusé : {e}")
        return None


def require_uid(authorization: Optional[str]) -> str:
    uid = uid_from_header(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return uid


# -----------------------------------------------------------------------------
# 🔤 NORMALISATION
# -----------------------------------------------------------------------------
def norm(value) -> str:
    s = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9+#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _compact(s: str) -> str:
    return s.replace(" ", "")


def skill_matches(wanted: str, have: str) -> bool:
    a, b = norm(wanted), norm(have)
    if not a or not b:
        return False
    if a == b or _compact(a) == _compact(b):
        return True
    # « flutter » ⊂ « flutter dart », « excel » ⊂ « microsoft excel »
    if len(a) >= 3 and re.search(r"(^| )" + re.escape(a) + r"( |$)", b):
        return True
    if len(b) >= 3 and re.search(r"(^| )" + re.escape(b) + r"( |$)", a):
        return True
    return False


def level_rank(value) -> Optional[int]:
    """Rang d'un diplôme, quel que soit le libellé (profil candidat ou critère)."""
    n = norm(value)
    if not n:
        return None
    if "doctorat" in n or "phd" in n:
        return 6
    if re.search(r"bac ?\+? ?5", n) or "master 2" in n or "ingenieur" in n:
        return 5
    if re.search(r"bac ?\+? ?4", n) or "master 1" in n:
        return 4
    if "master" in n:
        return 5
    if re.search(r"bac ?\+? ?3", n) or "licence" in n:
        return 3
    if re.search(r"bac ?\+? ?2", n) or "bts" in n or "dut" in n:
        return 2
    if "bac" in n or "lycee" in n:
        return 1
    if "bepc" in n:
        return 0
    return None


_STOP = {"et", "de", "des", "la", "le", "les", "du", "en", "&"}


def _tokens(value) -> set:
    return {t for t in norm(value).split() if t not in _STOP and len(t) > 1}


def _to_int(v, default=0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", ".").strip())
    except Exception:
        return None


# -----------------------------------------------------------------------------
# 👤 PROFIL AU MOMENT DE LA CANDIDATURE
#     L'âge n'est volontairement PAS copié : l'entreprise ne le voit pas.
# -----------------------------------------------------------------------------
SNAPSHOT_FIELDS = [
    "name", "username", "profileImageUrl", "job", "city", "level", "domain",
    "speciality", "skills", "experienceYears", "languages", "availability",
    "mobility", "profileType",
]


def build_profile_snapshot(uid: str) -> dict:
    doc = _db.collection("users").document(uid).get()
    data = doc.to_dict() if doc.exists else {}
    snap = {k: data.get(k) for k in SNAPSHOT_FIELDS if data.get(k) not in (None, "", [])}
    if "name" not in snap and "username" in snap:
        snap["name"] = snap["username"]
    snap.pop("username", None)
    return snap


# -----------------------------------------------------------------------------
# 🎯 SCORE DE CORRESPONDANCE
#     Compétences 40 · Domaine 20 · Niveau 15 · Lieu 15 · Expérience 10
#     + Questions (préférences) 10. Seuls les critères renseignés comptent ;
#     le score final est ramené sur 100.
#     Une compétence indispensable absente ou une question éliminatoire ratée
#     place le candidat dans « Écartés » (son statut, lui, ne change pas).
# -----------------------------------------------------------------------------
def evaluate_answer(question: dict, answer) -> Optional[bool]:
    qtype = question.get("type", "yesno")
    expected = question.get("expected")
    if answer is None or str(answer).strip() == "":
        return False
    if qtype == "yesno":
        if expected in (None, ""):
            return None
        return norm(answer) == norm(expected)
    if qtype == "number":
        a, e = _to_float(answer), _to_float(expected)
        if e is None:
            return None
        return a is not None and a >= e
    return None  # question ouverte : lue par le recruteur, pas notée


def compute_match(opp: dict, profile: dict, answers: list) -> Optional[dict]:
    crit = opp.get("recruitment") or {}
    questions = opp.get("questions") or []
    if not crit and not questions:
        return None

    profile = profile or {}
    parts = []      # {key, label, earned, max}
    reasons = []    # {ok, label}
    eliminated = False
    elim_reason = None

    # --- Compétences (40) ---
    skills = [s for s in (crit.get("skills") or []) if isinstance(s, dict) and str(s.get("name", "")).strip()]
    if skills:
        have = [str(x) for x in (profile.get("skills") or [])]
        total_w, got_w = 0, 0
        missing_required = []
        for s in skills:
            name = str(s["name"]).strip()
            required = bool(s.get("required"))
            w = 2 if required else 1
            total_w += w
            if any(skill_matches(name, h) for h in have):
                got_w += w
                reasons.append({"ok": True, "label": name})
            else:
                reasons.append({"ok": False, "label": name, "required": required})
                if required:
                    missing_required.append(name)
        parts.append({"key": "skills", "label": "Compétences", "earned": round(40 * got_w / total_w), "max": 40})
        if missing_required:
            eliminated = True
            elim_reason = "Compétence indispensable manquante : " + ", ".join(missing_required)

    # --- Domaine (20) ---
    domain = str(crit.get("domain") or "").strip()
    if domain:
        cand = profile.get("domain") or ""
        if cand and norm(cand) == norm(domain):
            earned = 20
        elif cand and (_tokens(cand) & _tokens(domain)):
            earned = 10
        else:
            earned = 0
        parts.append({"key": "domain", "label": "Domaine", "earned": earned, "max": 20})
        if earned < 20:
            reasons.append({"ok": False, "label": "Autre domaine" if cand else "Domaine non renseigné"})

    # --- Niveau d'études (15) ---
    min_rank = level_rank(crit.get("minLevel"))
    if min_rank is not None:
        cand_rank = level_rank(profile.get("level"))
        if cand_rank is not None and cand_rank >= min_rank:
            earned = 15
        elif cand_rank is not None and cand_rank == min_rank - 1:
            earned = 7
        else:
            earned = 0
        parts.append({"key": "level", "label": "Niveau d’études", "earned": earned, "max": 15})
        if earned == 15:
            reasons.append({"ok": True, "label": str(crit.get("minLevel"))})
        else:
            reasons.append({"ok": False, "label": f"{crit.get('minLevel')} requis"})

    # --- Lieu (15) ---
    work_mode = norm(crit.get("workMode"))
    offer_city = crit.get("city") or opp.get("location") or ""
    if work_mode == "teletravail":
        parts.append({"key": "location", "label": "Lieu", "earned": 15, "max": 15})
    elif offer_city:
        cand_city = norm(profile.get("city"))
        offer_n = norm(offer_city)
        same = bool(cand_city) and (cand_city == offer_n or re.search(r"(^| )" + re.escape(cand_city) + r"( |$)", offer_n))
        if same:
            earned = 15
        elif profile.get("mobility") is True:
            earned = 10
        else:
            earned = 0
        parts.append({"key": "location", "label": "Lieu", "earned": earned, "max": 15})
        first_city = str(offer_city).split(",")[0].strip()
        if earned == 15:
            reasons.append({"ok": True, "label": first_city})
        elif earned == 10:
            reasons.append({"ok": True, "label": f"Mobile vers {first_city}"})
        else:
            reasons.append({"ok": False, "label": f"Hors {first_city}"})

    # --- Expérience (10) ---
    min_exp = _to_int(crit.get("minExperience"), 0)
    if min_exp > 0:
        cand_exp = _to_int(profile.get("experienceYears"), 0)
        if cand_exp >= min_exp:
            earned = 10
        elif cand_exp >= min_exp - 1:
            earned = 5
        else:
            earned = 0
        parts.append({"key": "experience", "label": "Expérience", "earned": earned, "max": 10})
        label = f"{min_exp} an{'s' if min_exp > 1 else ''} requis"
        reasons.append({"ok": earned == 10, "label": f"{cand_exp} an{'s' if cand_exp > 1 else ''} d’exp." if earned == 10 else label})

    # --- Questions ---
    by_id = {str(a.get("id")): a.get("answer") for a in (answers or []) if isinstance(a, dict)}
    pref_total, pref_ok = 0, 0
    for q in questions:
        if not isinstance(q, dict):
            continue
        result = evaluate_answer(q, by_id.get(str(q.get("id"))))
        if result is None:
            continue
        if q.get("eliminatory"):
            if result is False:
                eliminated = True
                elim_reason = elim_reason or f"Question éliminatoire : {q.get('text', '')}"
                reasons.append({"ok": False, "label": "Éliminatoire ratée", "required": True})
        else:
            pref_total += 1
            pref_ok += 1 if result else 0
    if pref_total:
        parts.append({"key": "questions", "label": "Questions", "earned": round(10 * pref_ok / pref_total), "max": 10})

    total_max = sum(p["max"] for p in parts)
    total = sum(p["earned"] for p in parts)
    score = round(100 * total / total_max) if total_max else 100

    if eliminated:
        tier = "ecarte"
    elif score >= 85:
        tier = "forte"
    elif score >= 60:
        tier = "partielle"
    else:
        tier = "faible"

    # Raisons : manques indispensables d'abord, puis autres manques, puis atouts
    reasons.sort(key=lambda r: (r["ok"], not r.get("required", False)))

    return {
        "score": score,
        "tier": tier,
        "breakdown": parts,
        "reasons": reasons[:8],
        "eliminated": eliminated,
        "eliminatedReason": elim_reason,
        "version": MATCH_VERSION,
        "computedAt": datetime.now(timezone.utc),
    }


def match_fields(match: Optional[dict]) -> dict:
    """Champs à écrire dans applications/{id}."""
    if not match:
        return {"match": None, "matchScore": None, "matchTier": None}
    return {"match": match, "matchScore": match["score"], "matchTier": match["tier"]}


# -----------------------------------------------------------------------------
# 📄 DOCUMENTS PRIVÉS (lien valable 15 minutes)
# -----------------------------------------------------------------------------
def copy_profile_document(uid: str, kind: str, dest_path: str) -> Optional[str]:
    """Copie le CV / la lettre du profil (users_docs/) dans le dossier de la candidature."""
    try:
        bucket = storage.bucket()
        src = bucket.blob(f"users_docs/{uid}_{kind}.pdf")
        if not src.exists():
            return None
        bucket.copy_blob(src, bucket, dest_path)
        return dest_path
    except Exception as e:
        print(f"⚠️ Copie du document de profil impossible ({kind}) : {e}")
        return None


@router.get("/applications/{app_id}/document")
def application_document(app_id: str, kind: str = "cv", authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    doc = _db.collection("applications").document(app_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    d = doc.to_dict()
    if uid not in (d.get("companyId"), d.get("applicantId")):
        raise HTTPException(status_code=403, detail="Accès refusé")

    path = d.get("cvPath" if kind == "cv" else "lmPath")
    if path:
        blob = storage.bucket().blob(path)
        url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=15), method="GET")
        return {"url": url, "expiresInMinutes": 15}

    legacy = d.get("cvUrl" if kind == "cv" else "lmUrl")  # anciennes candidatures
    if legacy:
        return {"url": legacy}
    raise HTTPException(status_code=404, detail="Document absent")


# -----------------------------------------------------------------------------
# 🔁 RECALCUL APRÈS MODIFICATION DES CRITÈRES
# -----------------------------------------------------------------------------
@router.post("/opportunities/{opp_id}/recompute-match")
def recompute_match(opp_id: str, authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    opp_doc = _db.collection("opportunities").document(opp_id).get()
    if not opp_doc.exists:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    opp = opp_doc.to_dict()
    if opp.get("postedBy") != uid:
        raise HTTPException(status_code=403, detail="Accès refusé")

    count = 0
    batch = _db.batch()
    for app_doc in _db.collection("applications").where("opportunityId", "==", opp_id).stream():
        a = app_doc.to_dict()
        profile = a.get("profileSnapshot") or build_profile_snapshot(a.get("applicantId", ""))
        batch.update(app_doc.reference, match_fields(compute_match(opp, profile, a.get("answers") or [])))
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = _db.batch()
    batch.commit()
    return {"status": "success", "updated": count}


# -----------------------------------------------------------------------------
# ⏰ RAPPELS D'ENTRETIEN
#     interviews/{id} : startAt (Timestamp), status proposed|confirmed|…,
#     reminders (bool), reminder24Sent, reminder1hSent
# -----------------------------------------------------------------------------
FORMAT_LABEL = {"visio": "en visio", "appel": "par appel vocal", "presentiel": "en présentiel"}


def _notify(user_id: str, title: str, body: str, app_id: str, for_company: bool):
    if not user_id:
        return
    try:
        _db.collection("users").document(user_id).collection("notifications").add({
            "title": title,
            "body": body,
            "message": body,
            "isRead": False,
            "createdAt": firestore.SERVER_TIMESTAMP,
            # « candidature » ouvre déjà la discussion côté entreprise
            "type": "candidature" if for_company else "interview",
            "applicationId": app_id,
        })
    except Exception as e:
        print(f"⚠️ Notification d'entretien non enregistrée : {e}")
    if _push:
        _push(user_id=user_id, title=title, body=body, data={"type": "chat", "applicationId": app_id})


def _claim(doc, field: str) -> bool:
    """Marque le rappel comme envoyé seulement si personne ne l'a fait entre-temps."""
    try:
        doc.reference.update({field: True}, option=_db.write_option(last_update_time=doc.update_time))
        return True
    except Exception:
        return False


def send_interview_reminders() -> int:
    if _db is None:
        return 0
    now = datetime.now(timezone.utc)
    sent = 0
    query = (_db.collection("interviews")
             .where("startAt", ">=", now - timedelta(minutes=5))
             .where("startAt", "<=", now + timedelta(hours=24, minutes=15)))
    for doc in query.stream():
        d = doc.to_dict()
        if d.get("status") not in ("proposed", "confirmed") or d.get("reminders") is False:
            continue
        start = d.get("startAt")
        if not isinstance(start, datetime):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        left = start - now
        hour = start.strftime("%H:%M")  # Abidjan = UTC+0
        fmt = FORMAT_LABEL.get(d.get("format"), "")
        title_offer = d.get("opportunityTitle") or "ton entretien"
        app_id = d.get("applicationId", "")

        if left <= timedelta(hours=1, minutes=10) and not d.get("reminder1hSent"):
            if not _claim(doc, "reminder1hSent"):
                continue
            body_c = f"Ton entretien {fmt} pour « {title_offer} » commence à {hour}."
            if d.get("format") in ("visio", "appel"):
                body_c += " Ouvre la discussion pour le rejoindre."
            _notify(d.get("applicantId"), "Entretien dans 1 heure ⏰", body_c, app_id, False)
            _notify(d.get("companyId"), "Entretien dans 1 heure ⏰",
                    f"Avec {d.get('applicantName', 'le candidat')} à {hour} — {title_offer}.", app_id, True)
            sent += 1
        elif timedelta(hours=2) < left <= timedelta(hours=24, minutes=15) and not d.get("reminder24Sent"):
            if not _claim(doc, "reminder24Sent"):
                continue
            body_c = f"Demain à {hour} : entretien {fmt} pour « {title_offer} » avec {d.get('companyName', 'l’entreprise')}."
            _notify(d.get("applicantId"), "Rappel : entretien demain 📅", body_c, app_id, False)
            _notify(d.get("companyId"), "Rappel : entretien demain 📅",
                    f"Demain à {hour} avec {d.get('applicantName', 'le candidat')} — {title_offer}.", app_id, True)
            sent += 1
    if sent:
        print(f"⏰ {sent} rappel(s) d'entretien envoyé(s).")
    return sent


def _safe_reminders():
    for job in (send_interview_reminders, process_sessions, process_auto_closures):
        try:
            job()
        except Exception as e:
            print(f"❌ Tâche recrutement {job.__name__} : {e}")


def start_recrutement_scheduler():
    """Planificateur léger, indépendant du scraping : rappels toutes les 5 minutes."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_safe_reminders, "interval", minutes=5, next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30))
    _scheduler.start()
    print("⏰ Planificateur des rappels d'entretien démarré.")


def stop_recrutement_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@router.get("/cron/interview-reminders")
def cron_interview_reminders(key: str = ""):
    """À appeler toutes les 5 min par un cron externe (cron-job.org) : garde Render éveillé
    et garantit les rappels même si le serveur s'est endormi. Protégé par CRON_SECRET."""
    secret = os.getenv("CRON_SECRET", "")
    if secret and key != secret:
        raise HTTPException(status_code=403, detail="Clé invalide")
    sent = send_interview_reminders()
    process_sessions()
    closed = process_auto_closures()
    return {"status": "success", "sent": sent, "closedOffers": closed}


# =============================================================================
#  PHASE B
# =============================================================================
_RAND = random.SystemRandom()


def jitsi_link(company_name: str, fmt: str) -> str:
    slug = norm(company_name).replace(" ", "-")[:18] or "entretien"
    code = "".join(_RAND.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(8))
    base = f"https://meet.jit.si/Marabo-{slug}-{code}"
    return base + "#config.startWithVideoMuted=true" if fmt == "appel" else base


_FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def fr_when(dt: datetime) -> str:
    """« mercredi 5 novembre à 10:20 » (Abidjan = UTC+0)."""
    return f"{_FR_DAYS[dt.weekday()]} {dt.day} {_FR_MONTHS[dt.month - 1]} à {dt.strftime('%H:%M')}"


def _as_utc(v) -> Optional[datetime]:
    if not isinstance(v, datetime):
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _chat_message(app_ref, sender_id: str, text: str, unread_field: str, extra_msg: Optional[dict] = None, extra_app: Optional[dict] = None, transaction=None):
    msg_ref = app_ref.collection("messages").document()
    msg = {"type": "text", "text": text, "senderId": sender_id, "createdAt": firestore.SERVER_TIMESTAMP}
    if extra_msg:
        msg.update(extra_msg)
    upd = {"lastMessage": text, "lastMessageTime": firestore.SERVER_TIMESTAMP, unread_field: firestore.Increment(1)}
    if extra_app:
        upd.update(extra_app)
    if transaction is not None:
        transaction.set(msg_ref, msg)
        transaction.update(app_ref, upd)
    else:
        b = _db.batch()
        b.set(msg_ref, msg)
        b.update(app_ref, upd)
        b.commit()


# -----------------------------------------------------------------------------
# 🗓️ RÉSERVATION D'UN CRÉNEAU
#  interviewSessions/{id} = { companyId, companyName, opportunityId,
#     opportunityTitle, format, durationMin, address, message, reminders,
#     slots:[{id, start}], invited:[applicationId], deadline, status open|closed,
#     takenSlots:[slotId], bookedBy:{applicationId: slotId},
#     interviewBy:{applicationId: interviewId}, deadlineReminderSent }
# -----------------------------------------------------------------------------
@router.post("/sessions/{session_id}/book")
def book_slot(session_id: str, payload: dict = Body(...), authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    app_id = str(payload.get("application_id") or "")
    slot_id = str(payload.get("slot_id") or "")
    if not app_id or not slot_id:
        raise HTTPException(status_code=400, detail="Créneau manquant")

    session_ref = _db.collection("interviewSessions").document(session_id)
    app_ref = _db.collection("applications").document(app_id)
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def _book(transaction):
        s_snap = session_ref.get(transaction=transaction)
        a_snap = app_ref.get(transaction=transaction)
        if not s_snap.exists or not a_snap.exists:
            raise HTTPException(status_code=404, detail="Session introuvable")
        sess, app = s_snap.to_dict(), a_snap.to_dict()
        if app.get("applicantId") != uid:
            raise HTTPException(status_code=403, detail="Accès refusé")
        if app_id not in (sess.get("invited") or []):
            raise HTTPException(status_code=403, detail="Tu n'es pas invité à cette session")
        deadline = _as_utc(sess.get("deadline"))
        if sess.get("status") != "open" or (deadline and deadline < now):
            raise HTTPException(status_code=410, detail="Les réservations sont terminées")

        slot = next((x for x in (sess.get("slots") or []) if str(x.get("id")) == slot_id), None)
        if not slot:
            raise HTTPException(status_code=404, detail="Créneau introuvable")
        start = _as_utc(slot.get("start"))
        if not start or start < now + timedelta(minutes=30):
            raise HTTPException(status_code=410, detail="Ce créneau est passé")

        booked_by = dict(sess.get("bookedBy") or {})
        taken = list(sess.get("takenSlots") or [])
        previous = booked_by.get(app_id)
        if slot_id in taken and previous != slot_id:
            raise HTTPException(status_code=409, detail="Ce créneau vient d'être pris")
        if previous == slot_id:
            return {"already": True, "start": start}

        if previous and previous in taken:
            taken.remove(previous)
        taken.append(slot_id)
        booked_by[app_id] = slot_id

        interview_by = dict(sess.get("interviewBy") or {})
        old_iv = interview_by.get(app_id)
        if old_iv:
            transaction.update(_db.collection("interviews").document(old_iv), {"status": "replaced", "updatedAt": firestore.SERVER_TIMESTAMP})

        fmt = sess.get("format", "visio")
        link = "" if fmt == "presentiel" else jitsi_link(sess.get("companyName", ""), fmt)
        iv_ref = _db.collection("interviews").document()
        interview_by[app_id] = iv_ref.id
        transaction.set(iv_ref, {
            "applicationId": app_id,
            "opportunityId": sess.get("opportunityId", ""),
            "opportunityTitle": sess.get("opportunityTitle", ""),
            "companyId": sess.get("companyId"),
            "companyName": sess.get("companyName", ""),
            "applicantId": uid,
            "applicantName": app.get("applicantName", ""),
            "format": fmt,
            "startAt": start,
            "durationMin": int(sess.get("durationMin") or 30),
            "link": link,
            "address": sess.get("address", ""),
            "message": "Créneau réservé par le candidat.",
            "status": "confirmed",
            "reminders": sess.get("reminders", True) is not False,
            "reminder24Sent": False,
            "reminder1hSent": False,
            "sessionId": session_id,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        transaction.update(session_ref, {"takenSlots": taken, "bookedBy": booked_by, "interviewBy": interview_by})
        text = f"📅 J'ai réservé le {fr_when(start)}."
        _chat_message(app_ref, uid, text, "unreadCountCompany",
                      extra_msg={"type": "interview", "interviewId": iv_ref.id},
                      extra_app={"nextInterviewAt": start, "lastInterviewId": iv_ref.id},
                      transaction=transaction)
        return {"already": False, "start": start, "companyId": sess.get("companyId"),
                "applicantName": app.get("applicantName", "Un candidat"), "title": sess.get("opportunityTitle", "")}

    result = _book(_db.transaction())
    if not result.get("already") and _push and result.get("companyId"):
        body = f"{result['applicantName']} a choisi le {fr_when(result['start'])} — {result['title']}."
        _notify(result["companyId"], "Créneau réservé 🗓️", body, app_id, True)
    return {"status": "success", "start": result["start"].isoformat()}


def process_sessions() -> int:
    """Relance la veille de la fin des réservations, puis ferme les sessions échues."""
    if _db is None:
        return 0
    now = datetime.now(timezone.utc)
    relaunched = 0
    for doc in _db.collection("interviewSessions").where("status", "==", "open").stream():
        s = doc.to_dict()
        deadline = _as_utc(s.get("deadline"))
        if not deadline:
            continue
        if deadline < now:
            doc.reference.update({"status": "closed"})
            continue
        if deadline - now <= timedelta(hours=24) and not s.get("deadlineReminderSent"):
            if not _claim(doc, "deadlineReminderSent"):
                continue
            booked = set((s.get("bookedBy") or {}).keys())
            for app_id in s.get("invited") or []:
                if app_id in booked:
                    continue
                relaunch_unbooked(s, app_id, deadline, automatic=True)
                relaunched += 1
    return relaunched


def relaunch_unbooked(session: dict, app_id: str, deadline: Optional[datetime], automatic: bool):
    app_ref = _db.collection("applications").document(app_id)
    snap = app_ref.get()
    if not snap.exists:
        return
    app = snap.to_dict()
    when = f" avant {fr_when(deadline)}" if deadline else ""
    text = f"⏰ Petit rappel : choisis ton créneau d'entretien{when}. Les horaires disponibles sont juste au-dessus."
    _chat_message(app_ref, session.get("companyId", ""), text, "unreadCountCandidate")
    if _push:
        _push(user_id=app.get("applicantId"), title="Choisis ton créneau 🗓️",
              body=f"{session.get('companyName', 'Une entreprise')} attend ta réservation{when}.",
              data={"type": "chat", "applicationId": app_id})


@router.post("/sessions/{session_id}/relaunch")
def relaunch_session(session_id: str, authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    snap = _db.collection("interviewSessions").document(session_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Session introuvable")
    s = snap.to_dict()
    if s.get("companyId") != uid:
        raise HTTPException(status_code=403, detail="Accès refusé")
    booked = set((s.get("bookedBy") or {}).keys())
    count = 0
    for app_id in s.get("invited") or []:
        if app_id not in booked:
            relaunch_unbooked(s, app_id, _as_utc(s.get("deadline")), automatic=False)
            count += 1
    return {"status": "success", "relaunched": count}


# -----------------------------------------------------------------------------
# 🏁 CLÔTURE D'UNE OFFRE
#  opportunities/{id}.closure = { trigger: filled|after_end, sendRefusal,
#     keepTop, closeApplications, cancelInterviews, message, status
#     scheduled|done, doneAt, stats }
# -----------------------------------------------------------------------------
DEFAULT_REFUSAL = ("Bonjour {prenom}, merci pour l’intérêt que vous avez porté au poste « {poste} » chez {entreprise}. "
                   "Après étude attentive, nous ne pouvons pas donner suite cette fois. Nous gardons votre profil pour de "
                   "prochaines opportunités. Bonne continuation !")


def render_template(body: str, applicant_name: str, poste: str, entreprise: str) -> str:
    parts = (applicant_name or "").strip().split()
    prenom = parts[-1] if parts else ""
    return (body.replace("{prenom}", prenom).replace("{nom}", (applicant_name or "").strip())
            .replace("{poste}", poste).replace("{entreprise}", entreprise)
            .replace("{date}", "").replace("{lien}", ""))


def _stage_of(app: dict) -> str:
    st = app.get("stage")
    if st in ("nouveau", "preselection", "entretien", "offre", "embauche", "refuse"):
        return st
    status = app.get("status")
    return {"Entretien": "entretien", "Accepté": "embauche", "Refusé": "refuse"}.get(status, "nouveau")


def run_closure(opp_id: str, trigger: str) -> dict:
    opp_ref = _db.collection("opportunities").document(opp_id)
    opp_snap = opp_ref.get()
    if not opp_snap.exists:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    opp = opp_snap.to_dict()
    cfg = opp.get("closure") or {}
    if cfg.get("status") == "done":
        return cfg.get("stats") or {}

    company_id = opp.get("postedBy", "")
    company = (_db.collection("users").document(company_id).get().to_dict() or {})
    entreprise = company.get("username") or company.get("companyName") or opp.get("companyName") or "Notre entreprise"
    poste = opp.get("title", "")
    body = cfg.get("message") or DEFAULT_REFUSAL
    send_refusal = cfg.get("sendRefusal", True) is not False
    keep_top = cfg.get("keepTop", True) is not False

    tags_by_app = {}
    for n in _db.collection("companyNotes").where("companyId", "==", company_id).stream():
        tags_by_app[n.id] = n.to_dict().get("tags") or []

    hired = pooled = refused = untouched = 0
    for a_doc in _db.collection("applications").where("opportunityId", "==", opp_id).stream():
        a = a_doc.to_dict()
        stage = _stage_of(a)
        if stage == "embauche":
            hired += 1
            continue
        if stage == "refuse":
            continue
        tags = tags_by_app.get(a_doc.id, [])
        if keep_top and ("Top profil" in tags or "Vivier" in tags):
            _db.collection("companyNotes").document(a_doc.id).set(
                {"companyId": company_id, "tags": firestore.ArrayUnion(["Vivier"]), "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)
            pooled += 1
            continue
        if not send_refusal:
            untouched += 1
            continue
        text = render_template(body, a.get("applicantName", ""), poste, entreprise)
        _chat_message(a_doc.reference, company_id, text, "unreadCountCandidate",
                      extra_app={"status": "Refusé", "stage": "refuse", "stageUpdatedAt": firestore.SERVER_TIMESTAMP})
        if _push:
            _push(user_id=a.get("applicantId"), title=f"Message de {entreprise}", body=text[:60] + ("…" if len(text) > 60 else ""),
                  data={"type": "chat", "applicationId": a_doc.id})
        refused += 1

    cancelled = 0
    if cfg.get("cancelInterviews"):
        now = datetime.now(timezone.utc)
        for iv in _db.collection("interviews").where("opportunityId", "==", opp_id).stream():
            d = iv.to_dict()
            start = _as_utc(d.get("startAt"))
            if d.get("status") in ("proposed", "confirmed") and start and start > now:
                iv.reference.update({"status": "cancelled", "updatedAt": firestore.SERVER_TIMESTAMP})
                cancelled += 1

    stats = {"hired": hired, "pooled": pooled, "refused": refused, "untouched": untouched, "cancelledInterviews": cancelled}
    upd = {
        "closure.status": "done",
        "closure.doneAt": firestore.SERVER_TIMESTAMP,
        "closure.trigger": trigger,
        "closure.stats": stats,
    }
    if trigger == "filled":
        upd["isFilled"] = True
    if cfg.get("closeApplications", True) is not False:
        upd["applicationsClosed"] = True
        end = _as_utc(opp.get("dateEnd"))
        if not end or end > datetime.now(timezone.utc):
            upd["dateEnd"] = datetime.now(timezone.utc)
    opp_ref.update(upd)
    print(f"🏁 Offre {opp_id} clôturée : {stats}")
    return stats


@router.post("/opportunities/{opp_id}/close")
def close_opportunity(opp_id: str, authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    snap = _db.collection("opportunities").document(opp_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    if snap.to_dict().get("postedBy") != uid:
        raise HTTPException(status_code=403, detail="Accès refusé")
    return {"status": "success", "stats": run_closure(opp_id, "filled")}


def process_auto_closures() -> int:
    """Clôture les offres réglées sur « 7 jours après la date de clôture »."""
    if _db is None:
        return 0
    now = datetime.now(timezone.utc)
    done = 0
    query = (_db.collection("opportunities")
             .where("closure.trigger", "==", "after_end")
             .where("closure.status", "==", "scheduled"))
    for doc in query.stream():
        end = _as_utc(doc.to_dict().get("dateEnd"))
        if end and end + timedelta(days=7) <= now:
            try:
                run_closure(doc.id, "after_end")
                done += 1
            except Exception as e:
                print(f"❌ Clôture auto {doc.id} : {e}")
    return done


def is_closed_for_applications(opp: dict) -> bool:
    return bool(opp.get("isFilled") or opp.get("applicationsClosed") or (opp.get("closure") or {}).get("status") == "done")


# =============================================================================
#  PHASE C — CVTHÈQUE ANONYME
#  users/{uid}.recruiterVisible (bool), recruiterVisibleSince, hiddenFromCompanies [uid]
#  talentIndex/{code} = { uid }                 (serveur uniquement)
#  talentInvitations/{id}                       (lu par le candidat)
#  users/{entreprise}/sentInvitations/{même id} (lu par l'entreprise, sans uid)
# =============================================================================
TALENT_SALT = os.getenv("TALENT_SALT", "marabo-talent-salt")
TALENT_DAILY_QUOTA = int(os.getenv("TALENT_DAILY_QUOTA", "12"))
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Champs du profil montrés aux recruteurs (jamais : nom, photo, e-mail, téléphone, âge, CV)
TALENT_FIELDS = ["job", "city", "mobility", "level", "domain", "speciality", "skills",
                 "experienceYears", "languages", "availability", "profileType"]


def talent_code(uid: str) -> str:
    digest = hmac.new(TALENT_SALT.encode(), uid.encode(), hashlib.sha256).digest()
    return "".join(_CODE_ALPHABET[b % len(_CODE_ALPHABET)] for b in digest[:6])


def _ensure_index(code: str, uid: str):
    ref = _db.collection("talentIndex").document(code)
    try:
        if not ref.get().exists:
            ref.set({"uid": uid, "createdAt": firestore.SERVER_TIMESTAMP})
    except Exception as e:
        print(f"⚠️ talentIndex {code} : {e}")


def _uid_from_code(code: str) -> Optional[str]:
    snap = _db.collection("talentIndex").document(str(code)).get()
    return (snap.to_dict() or {}).get("uid") if snap.exists else None


def _require_verified_company(uid: str) -> dict:
    d = _db.collection("users").document(uid).get().to_dict() or {}
    if d.get("type") != "entreprise":
        raise HTTPException(status_code=403, detail="Réservé aux entreprises")
    status = d.get("verificationStatus") or ("valide" if d.get("isVerified") else "non_envoye")
    if status != "valide":
        raise HTTPException(status_code=403, detail="Ton compte entreprise doit être vérifié pour accéder à la CVthèque.")
    return d


def _anon_profile(uid: str, data: dict) -> dict:
    p = {k: data.get(k) for k in TALENT_FIELDS if data.get(k) not in (None, "", [])}
    since = _as_utc(data.get("recruiterVisibleSince"))
    p["talentId"] = talent_code(uid)
    p["isNew"] = bool(since and datetime.now(timezone.utc) - since < timedelta(days=7))
    filled = sum(1 for k in ("job", "city", "level", "domain", "skills", "experienceYears", "languages", "availability") if data.get(k) not in (None, "", []))
    p["complete"] = filled >= 7
    return p


def _opp_for_score(opp: dict) -> dict:
    """Score CVthèque : critères de l'offre, sans les questions (pas encore de réponses)."""
    o = dict(opp)
    o.pop("questions", None)
    return o


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _quota_left(company_uid: str) -> int:
    sent = (_db.collection("users").document(company_uid).collection("sentInvitations")
            .where("createdAt", ">=", _today_start()).get())
    return max(0, TALENT_DAILY_QUOTA - len(sent))


def _visible_for(company_uid: str, data: dict) -> bool:
    return (data.get("recruiterVisible") is True
            and data.get("type") != "entreprise"
            and company_uid not in (data.get("hiddenFromCompanies") or []))


@router.post("/talents/search")
def search_talents(payload: dict = Body(default={}), authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    _require_verified_company(uid)

    q_tokens = [t for t in norm(payload.get("q", "")).split() if len(t) > 1]
    city = norm(payload.get("city", ""))
    min_rank = level_rank(payload.get("minLevel")) if payload.get("minLevel") else None
    min_exp = _to_int(payload.get("minExperience"), 0)
    avail = [a for a in (payload.get("availability") or []) if a]
    limit = min(max(_to_int(payload.get("limit"), 30), 1), 50)

    opp, opp_id = None, str(payload.get("opportunity_id") or "")
    invited, applied = set(), set()
    if opp_id:
        snap = _db.collection("opportunities").document(opp_id).get()
        if snap.exists and snap.to_dict().get("postedBy") == uid:
            opp = _opp_for_score(snap.to_dict())
            for d in _db.collection("users").document(uid).collection("sentInvitations").where("opportunityId", "==", opp_id).stream():
                invited.add(d.to_dict().get("talentId"))
            for a in _db.collection("applications").where("opportunityId", "==", opp_id).stream():
                applied.add(a.to_dict().get("applicantId"))

    results = []
    total_visible = 0
    for doc in _db.collection("users").where("recruiterVisible", "==", True).stream():
        data = doc.to_dict() or {}
        if not _visible_for(uid, data):
            continue
        total_visible += 1
        hay = norm(" ".join([str(data.get("job", "")), str(data.get("speciality", "")), str(data.get("domain", "")),
                             " ".join(str(x) for x in (data.get("skills") or []))]))
        hits = sum(1 for t in q_tokens if re.search(r"(^| )" + re.escape(t), hay))
        if q_tokens and hits == 0:
            continue
        if city:
            same = norm(data.get("city")) == city
            if not same and data.get("mobility") is not True:
                continue
        if min_rank is not None:
            r = level_rank(data.get("level"))
            if r is None or r < min_rank:
                continue
        if min_exp and _to_int(data.get("experienceYears"), 0) < min_exp:
            continue
        if avail and data.get("availability") not in avail:
            continue

        p = _anon_profile(doc.id, data)
        if opp:
            m = compute_match(opp, data, [])
            if m:
                p.update({"score": m["score"], "tier": m["tier"], "reasons": m["reasons"][:6], "eliminated": m["eliminated"]})
            p["alreadyInvited"] = p["talentId"] in invited
            p["alreadyApplied"] = doc.id in applied
        p["_relevance"] = hits
        p["_uid"] = doc.id
        results.append(p)

    if opp:
        results.sort(key=lambda r: (r.get("eliminated", False), -(r.get("score") or 0), -r["_relevance"]))
    else:
        results.sort(key=lambda r: (-r["_relevance"], not r["isNew"], not r["complete"]))
    page = results[:limit]

    # Compteur d'apparitions (statistique montrée au candidat) + index des codes
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    batch = _db.batch()
    for r in page:
        batch.set(_db.collection("users").document(r["_uid"]), {"talentViews": {month: firestore.Increment(1)}}, merge=True)
        _ensure_index(r["talentId"], r["_uid"])
    if page:
        batch.commit()
    for r in page:
        r.pop("_uid", None)
        r.pop("_relevance", None)

    return {"status": "success", "total": len(results), "visible": total_visible, "results": page, "quotaLeft": _quota_left(uid)}


@router.get("/talents/quota")
def talents_quota(authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    _require_verified_company(uid)
    return {"quotaLeft": _quota_left(uid), "quota": TALENT_DAILY_QUOTA}


@router.get("/talents/{talent_id}")
def talent_profile(talent_id: str, opportunity_id: str = "", authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    _require_verified_company(uid)
    t_uid = _uid_from_code(talent_id)
    data = (_db.collection("users").document(t_uid).get().to_dict() or {}) if t_uid else {}
    if not t_uid or not _visible_for(uid, data):
        raise HTTPException(status_code=404, detail="Ce profil n'est plus visible")
    p = _anon_profile(t_uid, data)
    if opportunity_id:
        snap = _db.collection("opportunities").document(opportunity_id).get()
        if snap.exists and snap.to_dict().get("postedBy") == uid:
            m = compute_match(_opp_for_score(snap.to_dict()), data, [])
            if m:
                p.update({"score": m["score"], "tier": m["tier"], "breakdown": m["breakdown"], "reasons": m["reasons"], "eliminated": m["eliminated"]})
            p["alreadyInvited"] = len(_db.collection("users").document(uid).collection("sentInvitations")
                                      .where("opportunityId", "==", opportunity_id).where("talentId", "==", talent_id).limit(1).get()) > 0
            p["alreadyApplied"] = len(_db.collection("applications").where("opportunityId", "==", opportunity_id)
                                      .where("applicantId", "==", t_uid).limit(1).get()) > 0
    return {"status": "success", "profile": p, "quotaLeft": _quota_left(uid)}


@router.post("/talents/invite")
def invite_talent(payload: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Invite un profil CVthèque (talent_id) ou un ancien candidat (application_id) à postuler."""
    uid = require_uid(authorization)
    company = _require_verified_company(uid)
    opp_id = str(payload.get("opportunity_id") or "")
    message = str(payload.get("message") or "").strip()[:800]

    opp_snap = _db.collection("opportunities").document(opp_id).get()
    if not opp_snap.exists or opp_snap.to_dict().get("postedBy") != uid:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    opp = opp_snap.to_dict()
    if is_closed_for_applications(opp) or opp.get("isDeleted") or opp.get("isArchived"):
        raise HTTPException(status_code=410, detail="Cette offre est clôturée")
    end = _as_utc(opp.get("dateEnd"))
    if end and end < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Cette offre est expirée")

    talent_id = str(payload.get("talent_id") or "")
    app_id = str(payload.get("application_id") or "")
    applicant_name = ""
    if talent_id:
        t_uid = _uid_from_code(talent_id)
        data = (_db.collection("users").document(t_uid).get().to_dict() or {}) if t_uid else {}
        if not t_uid or not _visible_for(uid, data):
            raise HTTPException(status_code=404, detail="Ce profil n'est plus visible")
    elif app_id:
        a_snap = _db.collection("applications").document(app_id).get()
        if not a_snap.exists or a_snap.to_dict().get("companyId") != uid:
            raise HTTPException(status_code=404, detail="Candidat introuvable")
        a = a_snap.to_dict()
        t_uid = a.get("applicantId")
        applicant_name = a.get("applicantName", "")
        data = _db.collection("users").document(t_uid).get().to_dict() or {}
        if uid in (data.get("hiddenFromCompanies") or []):
            raise HTTPException(status_code=403, detail="Ce candidat ne souhaite plus être contacté")
        talent_id = talent_code(t_uid)
    else:
        raise HTTPException(status_code=400, detail="Profil manquant")

    if len(_db.collection("applications").where("opportunityId", "==", opp_id).where("applicantId", "==", t_uid).limit(1).get()):
        raise HTTPException(status_code=409, detail="Ce profil a déjà postulé à cette offre")
    if len(_db.collection("talentInvitations").where("opportunityId", "==", opp_id).where("applicantId", "==", t_uid).limit(1).get()):
        raise HTTPException(status_code=409, detail="Ce profil a déjà été invité pour cette offre")
    left = _quota_left(uid)
    if left <= 0:
        raise HTTPException(status_code=429, detail=f"Limite de {TALENT_DAILY_QUOTA} invitations par jour atteinte. Reviens demain.")

    m = compute_match(_opp_for_score(opp), data, [])
    company_name = company.get("username") or company.get("companyName") or "Une entreprise"
    inv_ref = _db.collection("talentInvitations").document()
    batch = _db.batch()
    batch.set(inv_ref, {
        "applicantId": t_uid,
        "companyId": uid,
        "companyName": company_name,
        "companyLogo": company.get("profileImageUrl") or "",
        "opportunityId": opp_id,
        "opportunityTitle": opp.get("title", ""),
        "opportunityLocation": opp.get("location", ""),
        "contractType": opp.get("contractType") or (opp.get("recruitment") or {}).get("contract") or "",
        "dateEnd": opp.get("dateEnd"),
        "score": m["score"] if m else None,
        "message": message,
        "status": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    batch.set(_db.collection("users").document(uid).collection("sentInvitations").document(inv_ref.id), {
        "talentId": talent_id,
        "applicationId": app_id or None,
        "applicantName": applicant_name or None,   # seulement pour d'anciens candidats
        "opportunityId": opp_id,
        "opportunityTitle": opp.get("title", ""),
        "score": m["score"] if m else None,
        "status": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    })
    batch.set(_db.collection("users").document(t_uid), {"talentInvitesCount": firestore.Increment(1)}, merge=True)
    batch.commit()

    title = f"{company_name} t’invite à postuler ✨"
    body = f"« {opp.get('title', 'Une offre')} »" + (f" · ton profil correspond à {m['score']} %" if m else "")
    try:
        _db.collection("users").document(t_uid).collection("notifications").add({
            "title": title, "message": body, "body": body, "isRead": False,
            "createdAt": firestore.SERVER_TIMESTAMP, "type": "talent_invite",
            "invitationId": inv_ref.id, "opportunityId": opp_id,
        })
    except Exception as e:
        print(f"⚠️ Notification d'invitation : {e}")
    if _push:
        _push(user_id=t_uid, title=title, body=body, data={"type": "talent_invite", "invitationId": inv_ref.id, "opportunityId": opp_id})
    return {"status": "success", "invitationId": inv_ref.id, "quotaLeft": left - 1}


@router.post("/invitations/{inv_id}/decline")
def decline_invitation(inv_id: str, authorization: Optional[str] = Header(None)):
    uid = require_uid(authorization)
    ref = _db.collection("talentInvitations").document(inv_id)
    snap = ref.get()
    if not snap.exists or snap.to_dict().get("applicantId") != uid:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    inv = snap.to_dict()
    ref.update({"status": "declined", "respondedAt": firestore.SERVER_TIMESTAMP})
    try:
        _db.collection("users").document(inv["companyId"]).collection("sentInvitations").document(inv_id).update(
            {"status": "declined", "respondedAt": firestore.SERVER_TIMESTAMP})
    except Exception:
        pass
    return {"status": "success"}


def mark_invitation_applied(applicant_uid: str, opp_id: str, app_id: str) -> bool:
    """Appelé par /apply : relie la candidature à une invitation en attente."""
    try:
        found = (_db.collection("talentInvitations").where("opportunityId", "==", opp_id)
                 .where("applicantId", "==", applicant_uid).limit(1).get())
        if not found:
            return False
        inv = found[0]
        d = inv.to_dict()
        if d.get("status") == "applied":
            return True
        inv.reference.update({"status": "applied", "applicationId": app_id, "respondedAt": firestore.SERVER_TIMESTAMP})
        _db.collection("users").document(d["companyId"]).collection("sentInvitations").document(inv.id).set(
            {"status": "applied", "applicationId": app_id, "respondedAt": firestore.SERVER_TIMESTAMP}, merge=True)
        return True
    except Exception as e:
        print(f"⚠️ Lien invitation → candidature : {e}")
        return False
