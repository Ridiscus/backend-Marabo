import os, requests, uuid, random, hashlib
from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
from firebase_admin import credentials, firestore, initialize_app
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
import re
from fastapi import Body
from pydantic import BaseModel
import json
import threading
from google.oauth2 import service_account
import google.auth.transport.requests
import asyncio, time
from fastapi.responses import JSONResponse
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urljoin

from webdriver_manager.chrome import ChromeDriverManager


#from selenium import webdriver
#from selenium.webdriver.common.by import By
#from selenium.webdriver.chrome.options import Options
#from selenium.webdriver.chrome.service import Service
#from selenium.webdriver.common.by import By
#from selenium.webdriver.common.keys import Keys
#from selenium.webdriver.support.ui import WebDriverWait
#from selenium.webdriver.support import expected_conditions as EC


# --- IMPORTS SELENIUM ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
# (Tu peux retirer 'undetected_chromedriver' si tu ne l'utilises pas spécifiquement, 
# car il est très instable sur les serveurs Docker type Railway)


import urllib3
from kaggle.api.kaggle_api_extended import KaggleApi









# Charger les variables d'environnement
load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")



# Initialiser Firebase
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('FIREBASE_CLIENT_EMAIL')}"
})
initialize_app(cred)
db = firestore.client()



# Charger le fichier JSON téléchargé
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
SERVICE_ACCOUNT_FILE = "service-account.json"

fcm_credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
request = google.auth.transport.requests.Request()

def get_fcm_access_token():
    fcm_credentials.refresh(request)
    return fcm_credentials.token  # ✅ au lieu de credentials.token

# Initialise un token immédiatement
access_token = get_fcm_access_token()
print("Access Token:", access_token)



app = FastAPI()



# Fonction pour générer une image aléatoire
def random_image():
    return f"https://picsum.photos/600/300?random={random.randint(1, 10000)}"


# Images locales par source
local_images = {
    "INFAS": [
        "https://yop.l-frii.com/wp-content/uploads/2025/06/Cote-dIvoire-CONCOURS-DENTREE-A-LINFAS-SESSION-2025-Nouveau-Report-de-la-date-limite-des-inscriptions.jpeg",
        "https://kamerpower.com/wp-content/uploads/2019/12/Procedure-Inscription-Concours-INFAS-Cote-divoire.jpg",
        "https://yop.l-frii.com/wp-content/uploads/2025/06/Cote-dIvoire-CONCOURS-DENTREE-A-LINFAS-SESSION-2025-Nouveau-Report-de-la-date-limite-des-inscriptions.jpeg"
    ],
    "GUCACI ENA": [
        "https://fonctionpublique.gouv.tg/wp-content/uploads/2022/07/ENA-togo.jpg",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSEoXTDhtsRroemejeY6FqFS9aMTcHh-iytJQ&s",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ0ngHGHxFjqeqsq-_Q5ntWjbTMC-hk1htF6g&s"
    ],
    "EAUX ET FORËT": [
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSO26enIR5fvSeo1p08r9KrS3r_AeW4X0NGUw&s",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQsyBqrF3io_uq63rLm3JiSlBudCh4kcGUJUg&s",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ_ExN2f0t-gxep_LBsjoP4bbrAstbQkTjiyQ&s"
    ]
}


def choose_image(source: str):
    if source in local_images:
        return random.choice(local_images[source])
    return random_image()  # fallback aléatoire



def parse_date_fr(date_str):
    mois = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    parts = date_str.lower().split()
    if len(parts) >= 3:
        jour = int(parts[0])
        mois_num = mois.get(parts[1], 1)
        annee = int(parts[2])
        return datetime(annee, mois_num, jour).date()  # <- ici .date() enlève l'heure
    return date_str

def generate_numeric_id(title: str, date_end: str) -> int:
    hash_object = hashlib.md5(f"{title}-{date_end}".encode())
    return int(hash_object.hexdigest()[:12], 16)


def generate_ai_summary_gemini(title, category, source, description=""):
    
    
    prompt = f"Résumé en français de l'opportunité suivante:\nTitre: {title}\nCatégorie: {category}\nSource: {source}\nDescription: {description}\nRends-le clair et engageant."

    headers = {
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(GEMINI_API_URL, json=data, headers=headers, timeout=15)
        response.raise_for_status()
        result = response.json()
        # Récupération du texte renvoyé par Gemini
        ai_summary = result["candidates"][0]["content"]["parts"][0]["text"]
        return ai_summary
    except Exception as e:
        print("Erreur Gemini:", e, response.text if 'response' in locals() else "")
        return f"L’IA n’a pas pu générer de résumé pour '{title}'."


def generate_ai_summary(category, source):
    """
    Génère un résumé IA dynamique basé sur la catégorie et la source.
    """
    return f"L’IA a détecté un {category.lower()} publié par {source}."



def send_notification(tokens, title, body, data={"screen": "/alerts"}):
    url = "https://fcm.googleapis.com/v1/projects/marabo-80906/messages:send"
    headers = {
        "Authorization": f"Bearer {get_fcm_access_token()}",
        "Content-Type": "application/json; UTF-8",
    }

    for token in tokens:
        payload = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body
                },
                "data": data or {},
                "android": {
                    "notification": {
                        "click_action": "FLUTTER_NOTIFICATION_CLICK"
                    }
                },
                "apns": {
                    "payload": {
                        "aps": {
                            "category": "FLUTTER_NOTIFICATION_CLICK"
                        }
                    }
                }
            }
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print(f"Envoyé à {token}: {response.status_code} {response.text}")

        # ⚡️ Vérifie si le token est invalide (UNREGISTERED)
        if response.status_code == 404:
            try:
                res_json = response.json()
                error_code = res_json.get("error", {}).get("details", [{}])[0].get("errorCode")
                if error_code == "UNREGISTERED":
                    print(f"⚠️ Token invalide détecté → suppression du Firestore : {token}")
                    # Recherche dans Firestore et supprime le token
                    users = db.collection("users").where("fcm_token", "==", token).stream()
                    for user in users:
                        db.collection("users").document(user.id).update({"fcm_token": firestore.DELETE_FIELD})
            except Exception as cleanup_error:
                print("⚠️ Erreur nettoyage token:", cleanup_error)






# ---------- CONFIGURATION SELENIUM (CORRIGÉE) ----------
def get_driver():
    chrome_options = Options()
    
    # --- 1. Options CRITIQUES pour le serveur (Docker/Railway) ---
    chrome_options.add_argument("--headless=new")       # Indispensable : Pas d'interface graphique
    chrome_options.add_argument("--no-sandbox")         # Indispensable pour Docker
    chrome_options.add_argument("--disable-dev-shm-usage") # Évite les crashs de mémoire partagée
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    
    # User Agent (pour ne pas être bloqué par les sites)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- 2. Astuce pour trouver Chrome sur Linux (Railway/Render) ---
    # Sur ton PC Windows, ça sera ignoré. Sur le serveur, ça trouvera le bon chemin.
    possible_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/opt/google/chrome/google-chrome"
    ]
    
    binary_path = None
    for path in possible_paths:
        if os.path.exists(path):
            binary_path = path
            break
            
    if binary_path:
        print(f"🚀 Chrome détecté sur le serveur à : {binary_path}")
        chrome_options.binary_location = binary_path
    else:
        print("💻 Chrome non trouvé dans les chemins Linux, utilisation du chemin système par défaut (Windows/Mac)")

    # --- 3. Lancement du driver ---
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ Erreur critique lors du lancement de Selenium : {e}")
        raise e





def get_interested_users(category):
    users_ref = db.collection("users")
    # Correction ici
    query = users_ref.where("interests", "array_contains", category).stream()
    
    tokens = []
    for user in query:
        data = user.to_dict()
        if "fcm_token" in data and data["fcm_token"]:  # Vérifie aussi que le token n'est pas vide
            tokens.append(data["fcm_token"])
    return tokens



@app.post("/payment-pending")
async def payment_pending(request: Request):
    try:
        data = await request.json()

        uid = data.get("uid")
        email = data.get("email")
        plan = data.get("plan")
        number = data.get("paymentNumber")
        amount = data.get("paymentAmount")
        service = data.get("paymentService")
        timestamp = data.get("timestamp")

        # --- Enregistrer le paiement en "pending" dans Firestore ---
        db.collection("payments").add({
            "uid": uid,
            "email": email,
            "plan": plan,
            "paymentNumber": number,
            "paymentAmount": amount,
            "paymentService": service,
            "timestamp": timestamp,
            "status": "pending"
        })

        # --- Préparer le message email ---
        subject = f"Nouveau paiement en attente - {plan}"
        body = f"""
Un utilisateur a déclaré un paiement manuel 🚨

UID: {uid}
Email: {email}
Plan: {plan}
Numéro: {number}
Montant: {amount} FCFA
Service: {service}
Date: {timestamp}

Vérifie ton compte Mobile Money ou Wave pour confirmer 👍
"""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_USER  # ou ton autre destinataire

        # --- Envoyer le mail ---
        try:
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_USER, EMAIL_USER, msg.as_string())
            print("✅ Mail envoyé avec succès")
        except Exception as smtp_error:
            print("❌ Erreur SMTP :", smtp_error)
            return JSONResponse({"status": "error", "message": f"Erreur SMTP : {smtp_error}"}, status_code=500)

        return JSONResponse({"status": "ok", "message": "Paiement reçu, mail envoyé et en attente de confirmation"})

    except Exception as e:
        print("❌ Erreur générale :", e)
        return JSONResponse({"status": "error", "message": f"Erreur générale : {e}"}, status_code=500)


@app.post("/confirm-payment")
async def confirm_payment(request: Request):
    try:
        data = await request.json()
        payment_id = data.get("payment_id")  # ID du document Firestore
        email_user = data.get("email")       # Email de l'utilisateur

        # Vérifier si le document existe
        doc_ref = db.collection("payments").document(payment_id)
        doc = doc_ref.get()
        if not doc.exists:
            return JSONResponse({"status": "error", "message": "Paiement introuvable"}, status_code=404)

        # Mettre à jour le statut
        doc_ref.update({"status": "confirmed"})

        # Préparer le mail
        subject = "Votre paiement a été confirmé ✅"
        body = "Nous avons bien reçu et confirmé votre paiement. Merci !"
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = email_user

        # Envoyer le mail
        try:
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_USER, email_user, msg.as_string())
            print(f"✅ Mail de confirmation envoyé à {email_user}")
        except Exception as smtp_error:
            print("❌ Erreur SMTP :", smtp_error)
            # Pas de return ici, le paiement est déjà confirmé

        return JSONResponse({"status": "ok", "message": f"Paiement {payment_id} confirmé"})

    except Exception as e:
        print("❌ Erreur générale :", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)



def build_opportunity(opp_id, title, category, source, date_start, date_end, url, badge_color, description="", image_url=None):
    if not date_start:
        date_start = date_end

    return {
        "id": opp_id,
        "source": source,
        "title": title,
        "category": category,
        "views": 0,
        "date_start": parse_date_fr(date_start),
        "date_end": parse_date_fr(date_end),
        "location": "Global" if source == "Kaggle" else "Côte d’Ivoire",
        "summary": f"Inscrivez-vous du {date_start} au {date_end}",
        "aiSummary": generate_ai_summary_gemini(title, category, source, description),
        "badgeColor": badge_color,
        "url": url,
         "imageUrl": image_url if image_url else choose_image(source)
    }


@app.get("/opportunities")
def list_opportunities():
    docs = db.collection("opportunities").stream()
    opportunities = [doc.to_dict() for doc in docs]
    return {"opportunities": opportunities}



def delete_expired_opportunities():
        now = datetime.utcnow().date()  # on compare seulement les dates
        deleted = 0
        all_docs = db.collection("opportunities").stream()

        for doc in all_docs:
            data = doc.to_dict()
            try:
                # Priorité à date_end, sinon date_start
                date_str = data.get("date_end") or data.get("date_start")
                if not date_str:
                    continue

                # Si c'est déjà un datetime (Firestore Timestamp)
                if isinstance(date_str, datetime):
                    opp_date = date_str.date()
                else:
                    # Normaliser les formats possibles
                    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                        try:
                            opp_date = datetime.strptime(str(date_str), fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        print(f"⚠️ Impossible de parser la date {date_str} pour {data.get('title')}")
                        continue

                # Suppression si date de fin dépassée
                if opp_date < now:
                    db.collection("opportunities").document(doc.id).delete()
                    deleted += 1
                    print(f"Supprimé: {data.get('title')} ({opp_date})")
            except Exception as e:
                print(f"Erreur suppression doc {doc.id}: {e}")
                continue

        return deleted

    

def notify_new_opportunities():
    print("🔔 Vérification des opportunités non notifiées...")
    opp_ref = db.collection("opportunities")
    
    # Correction ici : enlever 'filter='
    query = opp_ref.where("notified", "==", False).stream()
    
    for opp_doc in query:
        opp = opp_doc.to_dict()
        
        tokens = get_interested_users(opp["category"])
        if tokens:
            send_notification(
                tokens,
                opp["title"],
                opp.get("aiSummary", ""),
                data={"opportunityId": opp["id"]}
            )
        
        # Marquer comme notifié
        opp_ref.document(opp_doc.id).update({"notified": True})
        print(f"✅ Opportunité notifiée: {opp['title']}")



async def cron_notify_async():
    while True:
        try:
            delete_expired_opportunities()
            notify_new_opportunities()
        except Exception as e:
            print("⚠️ Erreur dans le cron:", e)
        await asyncio.sleep(60)





@app.on_event("startup")
async def start_async_crons():
    asyncio.create_task(cron_notify_async())


class MarkSeenBody(BaseModel):
    user_id: str

@app.post("/mark_seen/{opp_id}")
def mark_seen(opp_id: str, body: MarkSeenBody):
    user_id = body.user_id
    doc_ref = db.collection("opportunities").document(opp_id)
    doc_ref.update({"seenBy": firestore.ArrayUnion([user_id])})
    return {"message": f"Utilisateur {user_id} ajouté à seenBy pour {opp_id}"}









# ---------- SCRAPING ENA ----------
def scrape_ena_directs():
    url = "https://gucaci.ciconcours.com/concours-2025/liste-concours/ENA/1/2"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("div.my-3 table#table-liste tbody tr")
    items = []
    for tr in rows:
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 4:
            continue
        _, title, date_start, date_end = cols[:4]

        link_tag = tr.find("a", string=lambda t: t and "communiqué" in t.lower())
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else url

        opp_id = str(generate_numeric_id(title, date_end))
        items.append(build_opportunity(
            opp_id=opp_id,
            title=title,
            category="Concours",
            source="GUCACI ENA",
            date_start=date_start,
            date_end=date_end,
            url=url,
            badge_color="red",
            description=f"Du {date_start} au {date_end}, concours organisé par GUCACI ENA."
        ))
    return items



# ---------- SCRAPING INFAS ----------
def scrape_infas():
    urls = [
        "https://infas.ciconcours.com/details/1",  # Auxiliaires
        "https://infas.ciconcours.com/details/2"   # IDE / SFM / TSS
    ]
    items = []

    for url in urls:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table#table-concours tbody tr")
        for tr in rows:
            cols = tr.find_all("td")
            if len(cols) < 2:
                continue

            title = cols[0].get_text(strip=True)

            # Extraire les dates
            date_block = cols[1].get_text(" ", strip=True)
            date_start, date_end = "", ""

            if "Du" in date_block and "Au" in date_block:
                # Regex pour capturer entre Du et Au
                match = re.search(r'Du\s*(.*?)\s*Au\s*(.*)', date_block, re.IGNORECASE)
                if match:
                    date_start = match.group(1).strip()
                    date_end = match.group(2).strip()
                else:
                    # fallback si regex échoue
                    parts = date_block.split("Au")
                    date_start = parts[0].replace("Du", "").strip()
                    date_end = parts[1].strip() if len(parts) > 1 else date_start
            else:
                # Si pas de "Du" et "Au", on copie tout pareil
                date_start = date_end = date_block.strip()

            opp_id = str(generate_numeric_id(title, date_end))
            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category="Concours",
                source="INFAS",
                date_start=date_start,
                date_end=date_end,
                url=url,
                badge_color="green",
                description=f"Du {date_start} au {date_end}, concours organisé par  INFAS."
            ))
    return items


# ---------- SCRAPING EAUX ET FORETS ----------
def scrape_minef_concours():
    urls = [
        "https://minef.ciconcours.com/details/1",  # Niveau BEPC
        "https://minef.ciconcours.com/details/2"   # Niveau BAC
    ]
    items = []
    for url in urls:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("h5", class_="border-bottom pb-2 mb-0")
        if title_tag:
            title = title_tag.get_text(strip=True).replace("CONCOURS ", "").strip()
            date_range = soup.find("td", class_="text-center")
            if date_range:
                dates = date_range.get_text(strip=True).split("Au")
                date_start = dates[0].replace("Du", "").strip()
                date_end = dates[1].strip() if len(dates) > 1 else date_start
                opp_id = str(generate_numeric_id(title, date_end))
                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category="Concours",
                    source="EAUX ET FORËT",
                    date_start=date_start,
                    date_end=date_end,
                    url=url,
                    badge_color="blue",
                    description=f"Du {date_start} au {date_end}, concours organisé par GUCACI ENA."
                ))
    return items






# ---------- SCRAPING NOVOJOBS (Version Selenium) ----------
def scrape_novojob():
    urls = [
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/372-production-methode-industrie",
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/351-metiers-banque-et-assurances",
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/358-commercial-technico-commercial-service-client"
    ]
    
    items = []
    driver = None # On initialise la variable

    mois_map = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
    }

    try:
        # 1. On lance le navigateur virtuel (Fonction get_driver définie plus bas)
        driver = get_driver()

        for url in urls:
            try:
                print(f"🔄 Scraping Novojob: {url}")
                driver.get(url)
                
                # 2. PAUSE OBLIGATOIRE : On attend 3 secondes que le site charge le contenu
                time.sleep(3) 

                # 3. On récupère le code source de la page chargée
                soup = BeautifulSoup(driver.page_source, "html.parser")

                # --- Début de ton code de parsing original ---
                jobs = soup.select("div.row-fluid.job-details.pointer")
                
                for job in jobs:
                    a_tag = job.find("a", title=True)
                    title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
                    
                    # On utilise urljoin pour être sûr d'avoir le lien complet
                    # Note: Assure-toi d'avoir importé urljoin: from urllib.parse import urljoin
                    job_url = urljoin("https://www.novojob.com", a_tag['href']) if a_tag and a_tag.has_attr('href') else url

                    # Entreprise
                    company_tag = job.select_one("div.contact h6")
                    company = company_tag.get_text(strip=True) if company_tag else "Entreprise inconnue"

                    # Localisation
                    location_tag = job.select_one("i.fa-map-marker + span")
                    location = location_tag.get_text(strip=True) if location_tag else "Côte d’Ivoire"

                    # Date (Algorithme complexe conservé)
                    date_span = job.select_one("span.spaced-right i.fa-clock-o")
                    if date_span and date_span.parent:
                        date_tag = date_span.parent
                        # On retire l'icône pour ne garder que le texte
                        for i_tag in date_tag.find_all("i"):
                            i_tag.extract()
                        raw_date = date_tag.get_text(strip=True)

                        try:
                            # Exemple attendu : "23 Juillet"
                            parts = raw_date.split()
                            if len(parts) >= 2:
                                jour = parts[0]
                                mois = mois_map.get(parts[1].lower(), "01")
                                annee = str(datetime.today().year)
                                date_start = f"{jour.zfill(2)}/{mois}/{annee}"
                            else:
                                date_start = datetime.today().strftime("%d/%m/%Y")
                        except Exception:
                            date_start = datetime.today().strftime("%d/%m/%Y")
                    else:
                        date_start = datetime.today().strftime("%d/%m/%Y")

                    # Calcul date fin (+30 jours)
                    try:
                        date_obj = datetime.strptime(date_start, "%d/%m/%Y")
                        date_end = (date_obj + timedelta(days=30)).strftime("%d/%m/%Y")
                    except Exception:
                        date_end = date_start

# ID unique
                    opp_id = str(generate_numeric_id(title, date_end))
                    
                    items.append(build_opportunity(
                        opp_id=opp_id,
                        title=title,
                        category="Emplois",
                        source="NovoJob",
                        date_start=date_start,
                        date_end=date_end,
                        url=job_url,
                        badge_color="blue",
                        description=f"{title} chez {company}, situé à {location}."
                    ))
                # --- Fin du parsing ---

            except Exception as e_url:
                print(f"⚠️ Erreur lors du scraping de l'URL Novojob: {e_url}")
                continue # On passe à l'URL suivante même si celle-ci plante

    except Exception as e_main:
        print(f"❌ Erreur critique Selenium Novojob: {e_main}")

    finally:
        # 4. TRÈS IMPORTANT : On ferme le navigateur pour libérer la mémoire du serveur
        if driver:
            driver.quit()
            print("✅ Driver Selenium fermé.")

    return items



# ---------- SCRAPING DAADS ----------
def scrape_daad_scholarship():
    urls = [
        "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200"
    ]

    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for url in urls:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Titre de la bourse
        title_tag = soup.select_one("h2.title")
        title = title_tag.get_text(strip=True) if title_tag else "Titre non spécifié"

        # Objectif / Description
        objective_tag = soup.select_one("#ueberblick h3:contains('Objective') + p")
        description = objective_tag.get_text(strip=True) if objective_tag else "Description non spécifiée"

        # Conditions d'éligibilité
        eligibility_tag = soup.select_one("#ueberblick h3:contains('Who can apply?') + p")
        eligibility = eligibility_tag.get_text(strip=True) if eligibility_tag else "Conditions non spécifiées"

        # Durée
        duration_tag = soup.select_one("#ueberblick h3:contains('Duration of the funding') + p")
        duration = duration_tag.get_text(strip=True) if duration_tag else "Durée non spécifiée"

        # Valeur / montant
        value_tag = soup.select_one("#ueberblick h3:contains('Value') + ul")
        value = value_tag.get_text(strip=True) if value_tag else "Valeur non spécifiée"

        # Date de début et fin par défaut
        date_start = datetime.today().strftime("%d/%m/%Y")
        date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

        # Création d'un dictionnaire similaire à build_opportunity
        opp_id = str(generate_numeric_id(title, date_end))
        items.append(build_opportunity(
            opp_id=opp_id,
            title= title,
            category= "Bourses",
            source= "DAAD",
            date_start= date_start,
            date_end= date_end,
            url= url,
            badge_color= "green",
            description= f"{title}\n\nObjectif: {description}\nConditions: {eligibility}\nDurée: {duration}\nValeur: {value}"
        ))

    return items






# ---------- SCRAPING EDUCARRIERE ----------
# Désactiver les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scrape_educarriere(max_pages: int = 1):
    base_url = "https://emploi.educarriere.ci/nos-offres"
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }




    def normalize_category(cat: str) -> str:
        cat = cat.lower()
        if "emploi" in cat:
            return "Emplois"
        elif "stage" in cat:
            return "Stages"
        elif "formation" in cat:
            return "Formations"
        else:
            return cat.capitalize()



    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}" if page > 1 else base_url

        try:
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
            resp.raise_for_status()
        except requests.exceptions.SSLError:
            print(f"[SSL ERROR] Impossible de se connecter à {url}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        offers = soup.select("div.rt-post.post-md.style-8")
        for offer in offers:
            # URL et titre
            a_tag = offer.select_one("h4.post-title a")
            title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
            job_url = a_tag["href"] if a_tag and a_tag.has_attr("href") else url

            # Catégorie (Emploi, Stage, Emploi (CDD), etc.)
            category_tag = offer.select_one("a.racing")
            raw_category = category_tag.get_text(strip=True) if category_tag else "Non spécifié"
            category = normalize_category(raw_category)

            # Dates
            metas = offer.select("span.rt-meta li")
            date_start, date_end = None, None
            for li in metas:
                text = li.get_text(strip=True)
                if "Date d'édition" in text:
                    try:
                        raw = li.find("span").get_text(strip=True)
                        date_start = datetime.strptime(raw, "%d/%m/%Y").strftime("%d/%m/%Y")
                    except Exception:
                        date_start = datetime.today().strftime("%d/%m/%Y")
                if "Date limite" in text:
                    try:
                        raw = li.find("span").get_text(strip=True)
                        date_end = datetime.strptime(raw, "%d/%m/%Y").strftime("%d/%m/%Y")
                    except Exception:
                        date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

            # fallback si manquant
            if not date_start:
                date_start = datetime.today().strftime("%d/%m/%Y")
            if not date_end:
                date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

            # ID unique
            opp_id = str(generate_numeric_id(title, date_end))

            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category=category,   # dynamique
                source="Educarriere",
                date_start=date_start,
                date_end=date_end,
                url=job_url,
                badge_color="purple",
                description=f"{title} ({category}) - Voir plus sur Educarriere."
            ))

    return items





# désactiver les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scrape_educarriere_formations(max_pages: int = 1):
    base_url = "https://formation.educarriere.ci/"
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}" if page > 1 else base_url
        resp = requests.get(url, headers=headers, timeout=10, verify=False)  # <-- contournement SSL
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        offers = soup.select("div.rt-post.post-md.style-2.grid-meta")
        for offer in offers:
            # URL et titre
            a_tag = offer.select_one("h3.post-title a")
            title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
            job_url = "https://formation.educarriere.ci" + a_tag["href"] if a_tag and a_tag.has_attr("href") else url

            # Catégorie (ex: GESTION)
            category_tag = offer.select_one("a.cycling")
            category = category_tag.get_text(strip=True) if category_tag else "Formations"

            # Formateur
            trainer_tag = offer.select_one("div.post-meta .name")
            trainer = trainer_tag.get_text(strip=True) if trainer_tag else "Non spécifié"

            # Dates
            metas = offer.select("div.post-meta span.rt-meta")
            date_start, date_end = None, None
            if len(metas) >= 2:
                try:
                    date_start = datetime.strptime(metas[0].get_text(strip=True), "%d/%m/%Y").strftime("%d/%m/%Y")
                except:
                    date_start = datetime.today().strftime("%d/%m/%Y")
                try:
                    date_end = datetime.strptime(metas[1].get_text(strip=True), "%d/%m/%Y").strftime("%d/%m/%Y")
                except:
                    date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

            # fallback si manquant
            if not date_start:
                date_start = datetime.today().strftime("%d/%m/%Y")
            if not date_end:
                date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

            # Description courte
            desc_tag = offer.select_one("div.post-content p")
            description = desc_tag.get_text(strip=True) if desc_tag else f"Formation : {title}"

            # ID unique
            opp_id = str(generate_numeric_id(title, date_end))

            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category="Formations",   # normalisé pour Flutter
                source="Educarriere Formations",
                date_start=date_start,
                date_end=date_end,
                url=job_url,
                badge_color="blue",
                description=f"{title} par {trainer} ({category}) - {description}"
            ))

    return items







# --- Scraper Kaggle (CORRIGÉ) ---
def scrape_kaggle_competitions(max_items: int = 30):
    try:
        api = KaggleApi()
        api.authenticate()
    except Exception as e:
        print(f"⚠️ Erreur Auth Kaggle: {e}")
        return []

    items = []
    page = 1

    while len(items) < max_items:
        try:
            # Récupération de la réponse brute
            response = api.competitions_list(page=page)

            # --- CORRECTION CRUCIALE ICI ---
            # On vérifie si la réponse contient une liste dans l'attribut '.competitions'
            # ou si c'est déjà une liste (pour compatibilité)
            if hasattr(response, 'competitions'):
                competitions = response.competitions
            else:
                competitions = response 
            
            # Si après ça, ce n'est toujours pas une liste valide ou vide
            if not competitions:
                break
                
        except Exception as e:
            print(f"⚠️ Erreur Kaggle page {page}: {e}")
            break

        # Boucle sur les compétitions
        for comp in competitions:
            if len(items) >= max_items:
                break

            try:
                # Extraction sécurisée des données
                title = getattr(comp, 'title', "Titre inconnu")
                description = getattr(comp, 'description', "") or "Pas de description"
                
                # Gestion des dates
                date_start = getattr(comp, "enabledDate", None)
                deadline = getattr(comp, "deadline", None)

                # Formatage Date Début
                try:
                    if date_start:
                        d_start = str(date_start).replace('Z', '') # Nettoyage si format ISO
                        date_start_fmt = datetime.strptime(d_start[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                    else:
                        date_start_fmt = datetime.today().strftime("%d/%m/%Y")
                except:
                    date_start_fmt = datetime.today().strftime("%d/%m/%Y")

                # Formatage Date Fin
                try:
                    if deadline:
                        d_end = str(deadline).replace('Z', '')
                        date_end_fmt = datetime.strptime(d_end[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                    else:
                        date_end_fmt = "31/12/2030"
                except:
                    date_end_fmt = "31/12/2030"

                # URL & Image
                comp_url = getattr(comp, 'url', "https://www.kaggle.com/competitions")
                image_url = getattr(comp, "organizationAvatarUrl", None)

                # ID unique
                opp_id = str(generate_numeric_id(title, date_end_fmt))

                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category="Concours",
                    source="Kaggle",
                    date_start=date_start_fmt,
                    date_end=date_end_fmt,
                    url=comp_url,
                    badge_color="purple",
                    description=f"{title} - {description}",
                    image_url=image_url
                ))

            except Exception as e_comp:
                print(f"⚠️ Erreur sur une compétition Kaggle: {e_comp}")
                continue

        page += 1
        time.sleep(2)  # Pause respectueuse

    return items






# ---------- SCRAPING DEVPOST HACKATHONS ----------
def parse_submission_period(period_str: str):
    """
    Parse des champs comme :
    - "Jul 31 - Oct 01, 2025"
    - "Aug 14 - 30, 2025"
    - "Sep 5, 2025"
    - "Nov 2025"
    - "TBD"
    
    Retourne (date_start, date_end) au format YYYY-MM-DD
    """
    if not period_str:
        today = datetime.now().strftime("%Y-%m-%d")
        return today, today

    period_str = period_str.strip()
    print("🔍 Texte brut reçu pour parsing:", repr(period_str))

    try:
        # --- Cas 1 : "Jul 31 - Oct 01, 2025"
        if "-" in period_str:
            left, right = period_str.split("-")
            left = left.strip()
            right = right.strip()

            # Cas 1.1 : "Aug 14 - 30, 2025" (right commence par chiffre)
            if right[0].isdigit():
                month = left.split()[0]
                year = right.split(",")[-1].strip()
                start_str = f"{left} {year}"        # "Aug 14 2025"
                end_str = f"{month} {right}"        # "Aug 30, 2025"
                date_start = datetime.strptime(start_str, "%b %d %Y").strftime("%Y-%m-%d")
                date_end = datetime.strptime(end_str, "%b %d, %Y").strftime("%Y-%m-%d")

            # Cas 1.2 : "Jul 31 - Oct 01, 2025"
            else:
                year = right.split(",")[-1].strip()
                start_str = f"{left} {year}"        # "Jul 31 2025"
                end_str = right                     # "Oct 01, 2025"
                date_start = datetime.strptime(start_str, "%b %d %Y").strftime("%Y-%m-%d")
                date_end = datetime.strptime(end_str, "%b %d, %Y").strftime("%Y-%m-%d")

            print(f"✅ Dates finales: {date_start} → {date_end}")
            return date_start, date_end

        # --- Cas 2 : "Sep 5, 2025" → start=end
        if "," in period_str and any(m in period_str for m in 
                                     ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]):
            dt = datetime.strptime(period_str, "%b %d, %Y")
            date = dt.strftime("%Y-%m-%d")
            print(f"✅ Cas date unique: {date}")
            return date, date

        # --- Cas 3 : "Nov 2025" (pas de jour → on prend 1er jour du mois)
        if any(m in period_str for m in 
               ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]) and "," not in period_str:
            dt = datetime.strptime(period_str, "%b %Y")
            start = dt.strftime("%Y-%m-01")
            # on prend fin de mois en ajoutant un mois puis en retirant un jour
            next_month = dt.replace(day=28) + timedelta(days=4)  # passe au mois suivant
            end = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")
            print(f"✅ Cas mois seul: {start} → {end}")
            return start, end

        # --- Cas 4 : "TBD"
        if "TBD" in period_str.upper():
            today = datetime.now().strftime("%Y-%m-%d")
            print(f"⚠️ Cas TBD → fallback {today}")
            return today, today

    except Exception as e:
        print("⚠️ Erreur parsing dates:", repr(period_str), "Erreur:", e)

    # fallback général
    today = datetime.now().strftime("%Y-%m-%d")
    return today, today


def scrape_devpost_hackathons():
    base_url = "https://devpost.com/api/hackathons"
    max_pages = 3  # nombre de pages à scrapper
    page = 1
    items = []
    now = datetime.utcnow()  # date et heure actuelles en UTC

    while page <= max_pages:
        resp = requests.get(f"{base_url}?page={page}", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        hackathons = data.get("hackathons", [])
        if not hackathons:
            break  # Plus de hackathons, on sort

        for hack in hackathons:
            title = hack.get("title")
            hack_slug = hack.get("url")
            hack_url = hack_slug if hack_slug else "https://devpost.com/hackathons"
            
            # Debug
            print(f"[DEBUG] hack_slug brut = {hack_slug}")
            print(f"[DEBUG] hack_url final = {hack_url}")

            # Image
            image_url = hack.get("thumbnail_url")
            if not isinstance(image_url, str) or not image_url.strip():
                image_url = random_image()
            elif image_url.startswith("//"):
                image_url = "https:" + image_url

            # Location
            loc = hack.get("location")
            if isinstance(loc, dict):
                location = loc.get("display_name") or loc.get("location") or "En ligne"
            elif isinstance(loc, str):
                location = loc
            else:
                location = "En ligne"

            # Dates → directement depuis submission_period_dates
            submission_period = hack.get("submission_period_dates")
            date_start, date_end = parse_submission_period(submission_period)

            # ⚡️ Filtrage : hackathons déjà terminés
            if date_end:
                # Convertir la string en datetime
                date_end_dt = datetime.strptime(date_end, "%Y-%m-%d")
                if date_end_dt < now:
                    continue

            # Génération d'un ID unique
            opp_id = str(generate_numeric_id(title, location))

            items.append({
                "id": opp_id,
                "source": "Devpost",
                "title": title,
                "category": "Hackathons",
                "views": 0,
                "location": location,
                "summary": "",
                "aiSummary": f"L'IA a détecté un hackathon intitulé '{title}' {location}.",
                "badgeColor": "purple",
                "url": hack_url,
                "imageUrl": image_url,
                "dateStart": date_start,
                "dateEnd": date_end,
                "rawDates": submission_period
            })

        page += 1  # Passe à la page suivante

    return items







# ---------- ROUTE SCRAP ----------
@app.get("/scrape")
def scrape_opportunities():
    scrapers = [
        scrape_ena_directs,
        scrape_infas,
        scrape_minef_concours,
        scrape_devpost_hackathons,
        scrape_novojob,
        scrape_daad_scholarship,
        scrape_educarriere,
        scrape_educarriere_formations,
        scrape_kaggle_competitions,
    ]

    ops = []
    for scraper in scrapers:
        try:
            ops += scraper()
        except Exception as e:
            print(f"❌ Erreur dans {scraper.__name__}: {e}")
            continue

    added, updated = 0, 0
    for opp in ops:
        try:
            doc_ref = db.collection("opportunities").document(str(opp["id"]))
            doc = doc_ref.get()

            opp_to_write = dict(opp)
            opp_to_write["createdAt"] = firestore.SERVER_TIMESTAMP

            if "seenBy" not in opp_to_write:
                opp_to_write["seenBy"] = []

            if doc.exists:
                doc_ref.set(opp_to_write, merge=True)
                updated += 1
            else:
                opp_to_write["isNew"] = True
                opp_to_write["notified"] = False
                doc_ref.set(opp_to_write)
                added += 1
        except Exception as e:
            print(f"⚠️ Firestore error for opp {opp.get('id')}: {e}")
            continue

    return {
        "message": "Scraping terminé",
        "ajoutés": added,
        "mis_à_jour": updated,
        "total": len(ops)
    }

    







@app.get("/")
def root():
    return {"message": "Opportunities backend is running!"}