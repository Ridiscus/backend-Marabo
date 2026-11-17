# =============================================================================
#  MARABO — Suppression de compte (App Store 5.1.1(v), Play Store, RGPD)
#
#  POST /account/delete   (jeton Firebase obligatoire)
#    Corps : { "confirm": "SUPPRIMER" }
#
#  Efface définitivement :
#   - Particulier : profil (users/{uid} et sous-collections), candidatures et
#     leurs messages, entretiens, notes des entreprises sur ses candidatures,
#     invitations CVthèque, code anonyme, abonnements aux entreprises, fichiers
#     (photo, CV, lettre, documents de candidature, pièces jointes du chat).
#   - Entreprise : profil, annonces, candidatures reçues et leurs messages,
#     entretiens, sessions, notes, affiches, crédits de publication, abonnés,
#     fichiers (logo, justificatifs, visuels, affiches, pièces jointes).
#   - Puis le compte Firebase Authentication.
#
#  Conservé (obligations comptables) : transactions, paiements, dons, sans
#  nom ni e-mail (seulement l'identifiant technique, qui n'existe plus).
# =============================================================================
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException
from firebase_admin import auth as fb_auth
from firebase_admin import storage

router = APIRouter()
_db = None


def init_compte(db):
    global _db
    _db = db


def _uid(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return fb_auth.verify_id_token(authorization.split(" ", 1)[1].strip())["uid"]
    except Exception:
        return None


def _delete_doc(ref):
    """Supprime un document et toutes ses sous-collections."""
    try:
        _db.recursive_delete(ref)
    except Exception as e:
        print(f"⚠️ Suppression {ref.path} : {e}")


def _delete_query(query) -> int:
    n = 0
    for doc in query.stream():
        _delete_doc(doc.reference)
        n += 1
    return n


def _delete_blobs(prefix: str) -> int:
    n = 0
    try:
        for blob in storage.bucket().list_blobs(prefix=prefix):
            try:
                blob.delete()
                n += 1
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ Fichiers {prefix} : {e}")
    return n


def _delete_blob(path: Optional[str]):
    if not path:
        return
    try:
        storage.bucket().blob(str(path)).delete()
    except Exception:
        pass


def _delete_application(app_doc):
    """Candidature + messages + pièces jointes + documents + entretiens + notes."""
    d = app_doc.to_dict() or {}
    _delete_blobs(f"chats/{app_doc.id}/")
    _delete_blob(d.get("cvPath"))
    _delete_blob(d.get("lmPath"))
    _delete_query(_db.collection("interviews").where("applicationId", "==", app_doc.id))
    _delete_doc(_db.collection("companyNotes").document(app_doc.id))
    _delete_doc(app_doc.reference)


def delete_account(uid: str) -> dict:
    user_ref = _db.collection("users").document(uid)
    user = user_ref.get().to_dict() or {}
    is_company = str(user.get("type") or "").lower() == "entreprise"
    stats = {"type": "entreprise" if is_company else "particulier"}

    if is_company:
        # Candidatures reçues
        apps = list(_db.collection("applications").where("companyId", "==", uid).stream())
        for a in apps:
            _delete_application(a)
        stats["applications"] = len(apps)
        # Annonces et leurs visuels
        stats["opportunities"] = _delete_query(_db.collection("opportunities").where("postedBy", "==", uid))
        for col, field in (("interviews", "companyId"), ("interviewSessions", "companyId"), ("companyNotes", "companyId"),
                           ("banners", "ownerId"), ("publishCredits", "userId")):
            _delete_query(_db.collection(col).where(field, "==", uid))
        # Les abonnés ne suivent plus cette entreprise
        for f in user_ref.collection("followers").stream():
            _delete_doc(_db.collection("users").document(f.id).collection("following").document(uid))
        for prefix in (f"opportunity_images/{uid}_", f"banners/{uid}_", f"verifications/{uid}_"):
            _delete_blobs(prefix)
    else:
        apps = list(_db.collection("applications").where("applicantId", "==", uid).stream())
        for a in apps:
            _delete_application(a)
        stats["applications"] = len(apps)
        _delete_query(_db.collection("interviews").where("applicantId", "==", uid))
        _delete_query(_db.collection("talentInvitations").where("applicantId", "==", uid))
        _delete_query(_db.collection("talentIndex").where("uid", "==", uid))
        # Les entreprises suivies perdent cet abonné
        for f in user_ref.collection("following").stream():
            _delete_doc(_db.collection("users").document(f.id).collection("followers").document(uid))
        _delete_blobs(f"users_docs/{uid}_")

    # Commun : photo de profil, signalements envoyés, profil complet
    _delete_blob(f"profile_images/{uid}.jpg")
    _delete_query(_db.collection("reports").where("reporterId", "==", uid))
    # Dons : on garde le montant (comptabilité), sans nom ni message
    for d in _db.collection("donations").where("userId", "==", uid).stream():
        try:
            d.reference.update({"userName": "", "message": "", "anonymous": True})
        except Exception:
            pass
    _delete_doc(user_ref)

    # Enfin, le compte de connexion
    try:
        fb_auth.delete_user(uid)
    except fb_auth.UserNotFoundError:
        pass
    print(f"🗑️ Compte {uid} supprimé : {stats}")
    return stats


@router.post("/account/delete")
def account_delete(payload: dict = Body(default={}), authorization: Optional[str] = Header(None)):
    uid = _uid(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Connexion requise")
    if str((payload or {}).get("confirm") or "").strip().upper() != "SUPPRIMER":
        raise HTTPException(status_code=400, detail="Confirmation manquante")
    try:
        stats = delete_account(uid)
    except Exception as e:
        print(f"❌ Suppression du compte {uid} : {e}")
        raise HTTPException(status_code=500, detail="La suppression a échoué. Réessaie ou contacte le support.")
    return {"status": "deleted", **stats}
