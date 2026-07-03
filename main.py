import os, requests, uuid, random, hashlib
from fastapi import FastAPI, Request, File, UploadFile, Form
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
from selenium.webdriver.common.by import By  # <--- Assure-toi que c'est décommenté ou ajouté
from firebase_admin import firestore, messaging
from facebook_scraper import get_posts
from webdriver_manager.chrome import ChromeDriverManager


import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
import traceback # 🟢 NOUVEAU : Pour pister l'erreur exacte


from apify_client import ApifyClient
from datetime import datetime
from facebook_scraper import get_posts
from apify_client import ApifyClient
import google.generativeai as genai
from firebase_admin import storage # <--- Ajoute storage
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, BackgroundTasks # N'oublie pas d'importer BackgroundTasks



from playwright.async_api import async_playwright

from typing import Optional # 💡 N'oublie pas cet import tout en haut de ton fichier !
from fastapi import UploadFile, File, Form
from fastapi.responses import JSONResponse
# (Garde tes autres imports : firebase_admin, etc.)


# --- IMPORTS SELENIUM ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


import urllib3
from kaggle.api.kaggle_api_extended import KaggleApi


from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler




# Désactiver les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)








# Charger les variables d'environnement
load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
#GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

#GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"


# Modèle mis à jour vers 2.0-flash (celui qui est dispo sur ta clé)
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

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


# initialize_app(cred)

initialize_app(cred, {
    'storageBucket': 'marabo-80906.firebasestorage.app'
})


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




app = FastAPI()
# On dit à FastAPI : "Tout ce qui est dans le dossier 'static' est accessible via l'URL /static"
app.mount("/static", StaticFiles(directory="static"), name="static")


# Fonction pour générer une image aléatoire
def random_image():
    return f"https://picsum.photos/600/300?random={random.randint(1, 10000)}"


# # Images locales par source
# local_images = {
#     "INFAS": [
#         "https://yop.l-frii.com/wp-content/uploads/2025/06/Cote-dIvoire-CONCOURS-DENTREE-A-LINFAS-SESSION-2025-Nouveau-Report-de-la-date-limite-des-inscriptions.jpeg",
#         "https://kamerpower.com/wp-content/uploads/2019/12/Procedure-Inscription-Concours-INFAS-Cote-divoire.jpg",
#         "https://yop.l-frii.com/wp-content/uploads/2025/06/Cote-dIvoire-CONCOURS-DENTREE-A-LINFAS-SESSION-2025-Nouveau-Report-de-la-date-limite-des-inscriptions.jpeg"
#     ],
#     "GUCACI ENA": [
#         "https://fonctionpublique.gouv.tg/wp-content/uploads/2022/07/ENA-togo.jpg",
#         "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSEoXTDhtsRroemejeY6FqFS9aMTcHh-iytJQ&s",
#         "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ0ngHGHxFjqeqsq-_Q5ntWjbTMC-hk1htF6g&s"
#     ],
#     "EAUX ET FORËT": [
#         "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSO26enIR5fvSeo1p08r9KrS3r_AeW4X0NGUw&s",
#         "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQsyBqrF3io_uq63rLm3JiSlBudCh4kcGUJUg&s",
#         "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ_ExN2f0t-gxep_LBsjoP4bbrAstbQkTjiyQ&s"
#     ],
#     # ✅ AJOUT DE SOCIUMJOB ICI
#     "SociumJob": [
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fsocium1.png?alt=media&token=ebc31bce-055d-400a-a553-f5433df24085",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fsocium2.png?alt=media&token=e96da610-1d34-43ca-8eed-93952707eba5",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fsocium3.png?alt=media&token=c6abf67e-911c-47c8-a801-1affb8641025"
#     ],
#     # ✅ AJOUT DE SOCIUMJOB ICI
#     "NovoJob": [
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fnovojob1.png?alt=media&token=219a2388-447e-4c11-bbad-f058b7369396",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fnovojob2.png?alt=media&token=a2d429ad-88ff-405b-abb3-e64a4cafcf53",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fnovojob3.png?alt=media&token=b78f4c63-19b8-48c2-b1da-e79e22320920"
#     ],
#     # ✅ AJOUT DE PROJOBIVOIR ICI educarriere
#     "ProJob Ivoire": [
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fprojobivoire1.png?alt=media&token=d5ab3658-fdf9-4d5c-9055-787f06f8006f",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fprojobivoire2.png?alt=media&token=934c3f12-f508-463f-bd5c-db0eb29743f0",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fprojobivoire3.png?alt=media&token=7c96a39f-a3f6-465b-8629-ebc4b359c141"
#     ],
#     "Option Carrière": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Foption_carri1.png?alt=media&token=eadc3a53-afe0-46ce-a36c-7d3f1456662b",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Foption_carri2.png?alt=media&token=51182f7d-6110-4f08-bc99-32d69eea5ec6",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Foption_carri3.png?alt=media&token=66b00166-fb15-41c9-8b1d-18e6ef72aabf"
#     ],
#     "Educarriere": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere1.png?alt=media&token=e09243d2-1550-4e5c-af87-e2cf10c99a9d",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere2.png?alt=media&token=b5fd06f5-0df8-4eb4-9a55-aed4f5c404c0",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere3.png?alt=media&token=9b39073d-6662-460d-82a6-17cc8e92fc63"
#     ], 
#     "ENS (Ablanian)": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fens1.png?alt=media&token=6f4c18d5-cfb0-4924-91d1-80f16ecb20e2",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fens2.png?alt=media&token=b512e5e5-867e-44ea-aa94-ec2841f7f35d",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fens3.png?alt=media&token=ac2561ee-7fda-4af4-9bc2-84af540541d1"
#     ],
#     "DAAD": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fdaads1.png?alt=media&token=1265c4b8-5ad3-4d1c-a3cb-fa6a85c90ab5",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fdaads2.png?alt=media&token=26b5de71-701c-4528-b38a-5f998d87fea0",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fdaads3.png?alt=media&token=0a4fde8b-83a2-4906-aa9d-6cbf5fcc59d4"
#     ],
#     "Educarriere Formations": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere1.png?alt=media&token=e09243d2-1550-4e5c-af87-e2cf10c99a9d",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere2.png?alt=media&token=b5fd06f5-0df8-4eb4-9a55-aed4f5c404c0",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Feducarriere3.png?alt=media&token=9b39073d-6662-460d-82a6-17cc8e92fc63"
#     ],
#     "Kaggle": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fkaggle1.png?alt=media&token=55f6092a-356b-465c-a82f-88bc28572c89",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fkaggle2.png?alt=media&token=c0da6d48-0198-4ad7-8dfd-cbbd072e67b4",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Fkaggle3.png?alt=media&token=e71aea7d-0c20-4043-bfe2-2f216873f3d2"
#     ],
#     "Agence Emploi Jeunes": [ 
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Ficon_agenceemploi1.png?alt=media&token=7d666cfc-f3d3-4f45-8ed1-1ecc0ad4e46c",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Ficon_agenceemploi2.png?alt=media&token=49bdbf76-e069-44dc-8167-486b3c0a91e3",
#         "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/images_sources%2Ficon_agenceemploi3.png?alt=media&token=3afccd8e-9d54-4fe2-b3a5-c430267b5ec1"
#     ]
# }




# Un dictionnaire d'images thématiques fixes, réalistes et professionnelles
THEME_IMAGES = {
    # Images par défaut et catégories simples
    "DEFAULT": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fdefault_banner.jpg?alt=media&token=44a66a27-98e8-4b88-aed9-501b2449e8da",
    "Bourses": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fbourses.jpg?alt=media&token=f7a2658b-bfd0-4784-b5a8-9cb06f641e57",
    "Concours": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fconcours.jpg?alt=media&token=cb7dc11a-4470-4041-bd26-6d210d1845e5",
    "Hackathons": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fhackathons.jpg?alt=media&token=339f69b4-ac8a-414b-b970-fe6a92a4fad3",
    "Certificats": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fcertificats.jpg?alt=media&token=b5c909d0-e5c3-49e2-8da3-8575d84c3409",
    "Stages": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fstages.jpg?alt=media&token=92ff90ea-1ce3-4342-8bca-834e2b022cf7",
    "Institutions internationales": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Finternationale.jpg?alt=media&token=640eed63-14f2-42ec-a4d3-edd7f17790e8",
    "Appels à projets": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Fprojet.jpg?alt=media&token=cdb3ef19-fa2d-4dfd-82fb-1188cb357e02",
    "Subventions / Financements": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Ffinance.jpg?alt=media&token=896d296f-3208-40fb-8017-f4d1cb809a32",

    "Emplois": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Femplois.jpg?alt=media&token=e47fa437-d873-4a9d-a5bc-7217a5ca886b", # Image générique de l'emploi si l'IA ne choisit pas de sous-thème
    "Réseautage / Mentorats": "https://mon-storage.com/marabot/categories/reseautage.png",
    "Formations": "https://mon-storage.com/marabot/categories/formations.png",
    "Évènements": "https://mon-storage.com/marabot/categories/evenements.png",
    
    # Sous-thématiques pour "Emplois" ou "Formations" déterminées par l'IA
    "tech": "https://firebasestorage.googleapis.com/v0/b/marabo-80906.firebasestorage.app/o/categories%2Ftech.jpg?alt=media&token=3123917e-bfa9-4b07-9dc8-05537663dae2",        # Développeur, Data Scientist...
    "sante": "https://mon-storage.com/marabot/metiers/sante.png",      # INFAS, Médecin, Infirmier...
    "vente": "https://mon-storage.com/marabot/metiers/vente.png",      # Vendeur, Marketing, Commercial...
    "bureau": "https://mon-storage.com/marabot/metiers/bureau.png",    # RH, Comptabilité, Secrétariat...
    "terrain": "https://mon-storage.com/marabot/metiers/terrain.png",  # Logistique, Chauffeur, BTP...
}





checked_sources_cache = set()

def check_and_notify_new_source(source_name):
    """
    Vérifie si une source est nouvelle. Utilise un cache local pour éviter
    de lire Firestore 50 fois pour la même source.
    """
    if not source_name:
        return

    # Nettoyage du nom
    source_id = source_name.strip().lower().replace(" ", "_")

    # 1. Si on a déjà vérifié cette source pendant ce lancement, on arrête tout de suite
    if source_id in checked_sources_cache:
        return 

    # 2. Sinon, on vérifie dans Firestore
    source_ref = db.collection('known_sources').document(source_id)
    doc = source_ref.get()
    
    if not doc.exists:
        print(f"✨ Nouvelle source détectée : {source_name}")
        
        # Enregistrement dans Firestore
        source_ref.set({
            'name': source_name,
            'first_seen': firestore.SERVER_TIMESTAMP
        })
        
        # ✅ CORRECTION : Envoi de la notif avec les bons arguments
        # Vérifie bien que ta fonction send_notification_to_topic accepte ces arguments (topic, title, body)
        send_notification_to_topic(
            topic="all", # Remplace "all" par le nom de ton topic si c'est différent
            title="🌟 Nouvelle source d'opportunités !",
            body=f"Découvrez dès maintenant les offres de {source_name} sur l'application Marabo."
        )
    
    # 3. On ajoute au cache pour ne plus revérifier cette source ID aujourd'hui
    checked_sources_cache.add(source_id)



# def choose_image(source: str):
#     """
#     Choisit une image dans le dictionnaire en fonction de la source.
#     Utilise .get() pour gérer les clés manquantes sans planter.
#     """
#     # Si la source est dans notre dictionnaire, on prend une image au hasard de sa liste
#     if source in local_images:
#         return random.choice(local_images[source])
    
#     # Sinon, on retourne le fallback aléatoire
#     print(f"⚠️ Aucune image spécifique trouvée pour la source : '{source}'. Utilisation d'une image aléatoire.")
#     return random_image()




def choose_smart_image(category: str, ai_job_theme: str = None) -> str:
    """
    Sélectionne une image fixe professionnelle selon la catégorie ou le sous-thème de l'IA.
    """
    # 1. Si l'IA a détecté un sous-thème spécifique (tech, sante, etc.) et qu'il existe, on le prend
    if ai_job_theme and ai_job_theme in THEME_IMAGES:
        return THEME_IMAGES[ai_job_theme]
        
    # 2. Sinon, on cherche l'image de la catégorie principale
    if category in THEME_IMAGES:
        return THEME_IMAGES[category]
        
    # 3. Fallback absolu : Image par défaut Marabot
    return THEME_IMAGES["DEFAULT"]




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


# def generate_ai_summary_gemini(title, category, source, description=""):
    
    
#     prompt = f"Résumé en français de l'opportunité suivante:\nTitre: {title}\nCatégorie: {category}\nSource: {source}\nDescription: {description}\nRends-le clair et engageant."

#     headers = {
#         "Content-Type": "application/json"
#     }

#     data = {
#         "contents": [
#             {
#                 "parts": [
#                     {"text": prompt}
#                 ]
#             }
#         ]
#     }

#     try:
#         response = requests.post(GEMINI_API_URL, json=data, headers=headers, timeout=15)
#         response.raise_for_status()
#         result = response.json()
#         # Récupération du texte renvoyé par Gemini
#         ai_summary = result["candidates"][0]["content"]["parts"][0]["text"]
#         return ai_summary
#     except Exception as e:
#         print("Erreur Gemini:", e, response.text if 'response' in locals() else "")
#         return f"L’IA n’a pas pu générer de résumé pour '{title}'."


def generate_ai_summary(category, source):
    """
    Génère un résumé IA dynamique basé sur la catégorie et la source.
    """
    return f"L’IA a détecté un {category.lower()} publié par {source}."




# def analyze_opportunity_with_gemini(title, category, source, description=""):
#     # Le prompt magique : on force Gemini à renvoyer du JSON
#     prompt = f"""Analyse l'opportunité suivante et extrais les informations clés.
# Titre: {title}
# Catégorie: {category}
# Source: {source}
# Description: {description}

# Tu dois OBLIGATOIREMENT renvoyer la réponse sous la forme d'un objet JSON valide, avec la structure exacte suivante :
# {{
#     "summary": "Un résumé clair et engageant en 2 ou 3 phrases.",
#     "company_name": "Nom de l'entreprise ou de l'organisation. Si introuvable, mets 'Non spécifié'",
#     "exact_location": "Ville précise (ex: Abidjan, Bouaké, Yamoussoukro, Remote). Si introuvable, mets 'Non spécifié'",
#     "required_skills": ["Compétence 1", "Compétence 2", "Compétence 3"]
# }}"""

#     headers = {
#         "Content-Type": "application/json"
#     }

#     data = {
#         "contents": [
#             {
#                 "parts": [
#                     {"text": prompt}
#                 ]
#             }
#         ]
#     }

#     try:
#         response = requests.post(GEMINI_API_URL, json=data, headers=headers, timeout=15)
#         response.raise_for_status()
#         result = response.json()
        
#         # Récupération du texte brut de l'IA
#         ai_text = result["candidates"][0]["content"]["parts"][0]["text"]
        
#         # Nettoyage : parfois Gemini entoure le JSON avec ```json ... ```
#         ai_text = re.sub(r"^```json\s*", "", ai_text, flags=re.IGNORECASE)
#         ai_text = re.sub(r"\s*```$", "", ai_text).strip()
        
#         # Transformation du texte en vrai dictionnaire Python
#         ai_data = json.loads(ai_text)
#         return ai_data

#     except Exception as e:
#         print("Erreur Gemini (ou parsing JSON):", e)
#         # Fallback de sécurité au cas où l'IA échoue
#         return {
#             "summary": f"L’IA n’a pas pu générer de résumé pour '{title}'.",
#             "company_name": "Non spécifié",
#             "exact_location": "Non spécifié",
#             "required_skills": []
#         }






def analyze_opportunity_with_gemini(title, category, source, description=""):
    # Le prompt magique mis à jour avec la consigne 'job_theme'
    prompt = f"""Analyse l'opportunité suivante et extrais les informations clés.
Titre: {title}
Catégorie: {category}
Source: {source}
Description: {description}

Tu dois OBLIGATOIREMENT renvoyer la réponse sous la forme d'un objet JSON valide, avec la structure exacte suivante :
{{
    "summary": "Un résumé clair et engageant en 2 ou 3 phrases.",
    "company_name": "Nom de l'entreprise ou de l'organisation. Si introuvable, mets 'Non spécifié'",
    "exact_location": "Ville précise (ex: Abidjan, Bouaké, Yamoussoukro, Remote). Si introuvable, mets 'Non spécifié'",
    "required_skills": ["Compétence 1", "Compétence 2", "Compétence 3"],
    "job_theme": "Si la catégorie est 'Emplois' ou 'Formations', choisis STRICTEMENT la valeur la plus proche parmi : 'tech', 'sante', 'vente', 'bureau', 'terrain'. Si la description ne correspond à aucun de ces thèmes ou s'il s'agit d'une autre catégorie (comme Concours, Bourses, etc.), mets null sans guillemets."
}}"""

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
        
        # Récupération du texte brut de l'IA
        ai_text = result["candidates"][0]["content"]["parts"][0]["text"]
        
        # Nettoyage : parfois Gemini entoure le JSON avec
        ai_text = re.sub(r"^json\s*", "", ai_text, flags=re.IGNORECASE)
        ai_text = re.sub(r"\s*`$", "", ai_text).strip()
        
        # Transformation du texte en vrai dictionnaire Python
        ai_data = json.loads(ai_text)
        return ai_data

    except Exception as e:
        print("Erreur Gemini (ou parsing JSON):", e)
        # Fallback de sécurité au cas où l'IA échoue (Ajout du job_theme par défaut à None)
        return {
            "summary": f"L’IA n’a pas pu générer de résumé pour '{title}'.",
            "company_name": "Non spécifié",
            "exact_location": "Non spécifié",
            "required_skills": [],
            "job_theme": None
        }





def extract_opportunity_from_email_with_gemini(email_text):
    """Demande à Gemini d'extraire les infos OU de rejeter si ce n'est pas une opportunité."""
    
    prompt = f"""
    Voici le contenu d'un e-mail :
    
    {email_text}
    
    Mission 1 : Détermine si ce texte est VÉRITABLEMENT une offre d'opportunité. 
    Les SEULES catégories acceptées sont strictement : "Formations", "Emplois", "Stages", "Concours".
    Si l'e-mail est personnel, une discussion, une publicité ou hors de ces catégories, renvoie EXACTEMENT ce JSON et rien d'autre :
    {{"est_opportunite": false}}

    Mission 2 : Si c'est bien une opportunité valide, extrais les informations sous forme d'un objet JSON strict :
    {{
        "est_opportunite": true,
        "titre": "Nom de l'opportunité",
        "description": "Un résumé accrocheur en 2-3 phrases",
        "categorie": "Choisis uniquement parmi: Formations, Emplois, Stages, Concours",
        "source": "Nom de l'organisation",
        "lien_inscription": "Le lien web mentionné, ou vide",
        "date_limite": "Date au format JJ-MM-AAAA, ou vide"
    }}
    
    Renvoie UNIQUEMENT le code JSON, sans markdown ni texte autour.
    """

    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(GEMINI_API_URL, json=data, headers=headers, timeout=20)
        response.raise_for_status()
        result = response.json()
        ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
        
        clean_json = ai_response.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        print("❌ Erreur d'extraction Gemini :", e)
        return None



# J'ai remplacé la valeur par défaut de data par None, puis je l'assigne à un dict vide.
def send_notification(tokens, title, body, data=None):
    if data is None:
        data = {} # Par défaut, on n'envoie pas de data spécifique

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
                "data": data, # 👈 Les data sont insérées ici
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
                    users = db.collection("users").where("fcm_token", "==", token).stream()
                    for user in users:
                        db.collection("users").document(user.id).update({"fcm_token": firestore.DELETE_FIELD})
            except Exception as cleanup_error:
                print("⚠️ Erreur nettoyage token:", cleanup_error)



def send_push_to_user(user_id, title, body, data=None):
    """Récupère le token d'un user et lui envoie une notif"""
    try:
        # 1. Récupérer le profil de l'utilisateur (Entreprise)
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            print(f"⚠️ User {user_id} introuvable.")
            return

        user_data = user_doc.to_dict()
        fcm_token = user_data.get('fcm_token')

        if not fcm_token:
            print(f"⚠️ Pas de token FCM pour l'user {user_id}")
            return

        # 2. Préparer le message via Firebase Admin (plus fiable que requests manuel)
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    click_action="FLUTTER_NOTIFICATION_CLICK",
                    channel_id="high_importance_channel" # Assure-toi d'avoir ce channel côté Flutter
                ),
            ),
        )

        # 3. Envoyer
        response = messaging.send(message)
        print(f"✅ Notif envoyée à {user_id} : {response}")

    except Exception as e:
        print(f"❌ Erreur envoi notif user : {e}")






def notify_users_by_interest(opportunity_id, opportunity_title, category, source="", date_end=None):
    """
    1. Vérifie que l'offre n'est pas expirée.
    2. Cherche les utilisateurs intéressés.
    3. Sauvegarde la notif dans Firestore.
    4. Envoie le Push (FCM) SAUF si la source est Kaggle.
    """
    # On bloque tout si c'est déjà expiré
    if is_opportunity_expired(date_end):
        print(f"⏳ Offre expirée ({opportunity_title}), aucune notification envoyée ou sauvegardée.")
        return

    # 🛑 OPTION : Si tu ne veux MÊME PAS que la notif Kaggle apparaisse 
    # dans l'onglet "Notifications" de ton application, décommente ces lignes :
    # if source.strip().lower() == "kaggle":
    #     print(f"🚫 Notification annulée à 100% car la source est Kaggle.")
    #     return

    print(f"🔍 Recherche d'utilisateurs intéressés par : {category}")
    
    users_ref = db.collection('users').where('interests', 'array_contains', category).stream()
    tokens_to_notify = []
    
    for user in users_ref:
        user_data = user.to_dict()
        user_id = user.id
        
        # 1. Sauvegarder la notif dans Firestore (les users verront la cloche dans l'app)
        notif_data = {
            "title": f"Nouvelle opportunité : {category}",
            "message": opportunity_title,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "isRead": False,
            "type": "opportunity",
            "opportunityId": str(opportunity_id)
        }
        db.collection('users').document(user_id).collection('notifications').add(notif_data)
        
        # 2. Récupérer le token
        if 'fcm_token' in user_data and user_data['fcm_token']:
            tokens_to_notify.append(user_data['fcm_token'])
            
    # 3. Envoyer le Push groupé
    if tokens_to_notify:
        # 🎯 L'EXCEPTION EST ICI : On envoie le push UNIQUEMENT si ce n'est pas Kaggle
        if source.strip().lower() == "kaggle":
            print(f"🤫 Push silencieux : On n'envoie pas de Push FCM pour Kaggle ({opportunity_title}).")
        else:
            send_notification(
                tokens=tokens_to_notify,
                title=f"Nouveau dans vos intérêts : {category} !",
                body=opportunity_title,
                # 👇 LE PAYLOAD ADAPTÉ POUR FLUTTER
                data={
                    "type": "opportunity", 
                    "opportunityId": str(opportunity_id)
                }
            )
            print(f"✅ Notif push envoyée à {len(tokens_to_notify)} utilisateurs.")
    else:
        print("🤷‍♂️ Aucun utilisateur n'a cet intérêt ou aucun token valide trouvé.")




def is_opportunity_expired(date_str) -> bool:
    """Vérifie si une date donnée est antérieure à la date du jour (expirée)."""
    if not date_str:
        return False
        
    now = datetime.utcnow().date()
    
    # Si c'est déjà un objet datetime (ex: Timestamp Firestore)
    if isinstance(date_str, datetime):
        return date_str.date() < now
        
    # Si c'est un string, on tente de le parser
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            clean_date = str(date_str).strip()
            opp_date = datetime.strptime(clean_date, fmt).date()
            return opp_date < now
        except ValueError:
            continue
            
    return False




class ApplicationModel(BaseModel):
    applicant_uid: str   # ID du particulier
    applicant_name: str  # Nom du particulier
    opportunity_id: str  # ID de l'offre
    company_uid: str     # ID de l'entreprise (postedBy)
    message: str = ""    # Lettre de motivation courte





@app.post("/apply")
async def apply_for_job(
    applicant_uid: str = Form(...),
    applicant_name: str = Form(...),
    opportunity_id: str = Form(...),
    company_uid: str = Form(...),
    category: str = Form(...),                  # 💡 NOUVEAU : Récupère la catégorie
    message: Optional[str] = Form(None),        # 💡 NOUVEAU : Message optionnel
    cv_file: Optional[UploadFile] = File(None), # 💡 CHANGÉ : Optionnel
    lm_file: Optional[UploadFile] = File(None)  # 💡 CHANGÉ : Optionnel
):
    try:
        bucket = storage.bucket() # Récupère le bucket configuré plus haut
        
        cv_url = None
        lm_url = None

        # --- 1. Upload du CV (Seulement s'il est fourni) ---
        if cv_file and cv_file.filename:
            blob_cv = bucket.blob(f"candidatures/{opportunity_id}/{applicant_uid}_cv_{cv_file.filename}")
            blob_cv.upload_from_file(cv_file.file, content_type=cv_file.content_type)
            blob_cv.make_public() 
            cv_url = blob_cv.public_url

        # --- 2. Upload de la LM (Seulement si elle est fournie) ---
        if lm_file and lm_file.filename:
            blob_lm = bucket.blob(f"candidatures/{opportunity_id}/{applicant_uid}_lm_{lm_file.filename}")
            blob_lm.upload_from_file(lm_file.file, content_type=lm_file.content_type)
            blob_lm.make_public()
            lm_url = blob_lm.public_url

        # --- 3. Enregistrement Firestore (CANDIDATURE) ---
        app_data = {
            "applicantId": applicant_uid,
            "applicantName": applicant_name,
            "opportunityId": opportunity_id,
            "companyId": company_uid,
            "category": category, # On garde une trace de la catégorie
            "createdAt": firestore.SERVER_TIMESTAMP,
            "status": "pending"
        }
        
        # On n'ajoute ces champs à Firestore que s'ils existent
        if cv_url:
            app_data["cvUrl"] = cv_url
        if lm_url:
            app_data["lmUrl"] = lm_url
        if message:
            app_data["message"] = message

        # On insère dans la base
        update_time, app_ref = db.collection('applications').add(app_data)

        # --- 🧠 LOGIQUE DE NOTIFICATION DYNAMIQUE ---
        is_job_or_project = category in ['Emplois', 'Stages', 'Bourses', 'Subventions / Financements', 'Appels à projets']
        
        notif_title = "Nouvelle Candidature ! 📂" if is_job_or_project else "Nouvelle Inscription ! 🎉"
        notif_body = f"{applicant_name} a envoyé son dossier." if is_job_or_project else f"{applicant_name} vient de s'inscrire."
        
        # S'il y a un message (pour les événements), on l'ajoute à la notification
        if message:
            notif_body += f" Message : {message}"

        # --- 4. Enregistrement Firestore (NOTIFICATION VISUELLE) ---
        notification_data = {
            "recipientId": company_uid,
            "title": notif_title,
            "body": notif_body,
            "isRead": False,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "type": "candidature", # Tu peux garder 'candidature' ou le changer selon tes icônes côté Flutter
            "relatedId": opportunity_id,
            "applicationId": app_ref.id
        }
        
        # ON ÉCRIT DANS LA SOUS-COLLECTION DU USER
        db.collection('users').document(company_uid).collection('notifications').add(notification_data)

        # --- 5. Envoi du PUSH (Le "Bip" sur le téléphone) ---
        # Note : assure-toi que ta fonction send_push_to_user gère bien ces paramètres !
        send_push_to_user(
            user_id=company_uid,
            title=notif_title,
            body=notif_body,
            data={"type": "candidature", "opp_id": opportunity_id}
        )

        success_msg = "Dossier envoyé avec succès." if is_job_or_project else "Inscription confirmée avec succès."
        return {"status": "success", "message": success_msg}

    except Exception as e:
        print(f"Erreur candidature upload: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)






# Ajoute ce modèle Pydantic avec tes autres modèles (ex: ApplicationModel)
class ChatNotificationModel(BaseModel):
    application_id: str
    sender_id: str
    message_text: str

# @app.post("/notify-chat")
# async def trigger_chat_notification(payload: ChatNotificationModel):
#     """
#     Route appelée par Flutter après l'envoi d'un message 
#     pour déclencher la notification Push.
#     """
#     try:
#         # 1. Récupérer les infos de la candidature pour identifier les acteurs
#         app_doc = db.collection('applications').document(payload.application_id).get()
#         if not app_doc.exists:
#             return JSONResponse({"status": "error", "message": "Candidature introuvable"}, status_code=404)
        
#         app_data = app_doc.to_dict()

#         # 2. Déterminer qui est le destinataire et le nom de l'expéditeur
#         receiver_id = ""
#         sender_name = ""

#         # Si l'expéditeur est l'entreprise
#         if payload.sender_id == app_data.get('companyId'):
#             receiver_id = app_data.get('applicantId')
#             sender_name = app_data.get('username', "L'entreprise")
#         # Si l'expéditeur est le candidat
#         else:
#             receiver_id = app_data.get('companyId')
#             sender_name = app_data.get('applicantName', "Un candidat")

#         # 3. Raccourcir le texte pour la notification (esthétique)
#         short_msg = payload.message_text
#         if len(short_msg) > 50:
#             short_msg = short_msg[:47] + "..."

#         # 4. Envoyer le Push en utilisant TA fonction existante ! 🚀
#         send_push_to_user(
#             user_id=receiver_id,
#             title=f"Nouveau message de {sender_name}",
#             body=short_msg,
#             data={
#                 "type": "chat",
#                 "applicationId": payload.application_id
#             }
#         )

#         return {"status": "success", "message": "Notification envoyée"}

#     except Exception as e:
#         print(f"Erreur notification chat: {e}")
#         return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# @app.post("/notify-chat")
# async def trigger_chat_notification(payload: ChatNotificationModel):
#     """
#     Route appelée par Flutter après l'envoi d'un message 
#     pour déclencher la notification Push.
#     """
#     try:
#         # 1. Récupérer les infos de la candidature pour identifier les acteurs
#         app_doc = db.collection('applications').document(payload.application_id).get()
#         if not app_doc.exists:
#             return JSONResponse({"status": "error", "message": "Candidature introuvable"}, status_code=404)
        
#         app_data = app_doc.to_dict()

#         # 2. Déterminer qui est le destinataire et formater le titre de la notification
#         receiver_id = ""
#         notification_title = ""



#         if payload.sender_id == app_data.get('companyId'):
#             receiver_id = app_data.get('applicantId')

#             # 🔥 Aller chercher l'entreprise dans users
#             company_doc = db.collection("users").document(payload.sender_id).get()

#             if company_doc.exists:
#                 company_data = company_doc.to_dict()
#                 company_name = company_data.get('username', "inconnue")
#             else:
#                 company_name = "inconnue"

#             notification_title = f"Nouveau message de l'entreprise {company_name}"
            
#         # Si l'expéditeur est le candidat
#         else:
#             receiver_id = app_data.get('companyId')
#             applicant_name = app_data.get('applicantName', "Un candidat")
#             # 💡 On garde un format classique pour les particuliers
#             notification_title = f"Nouveau message de {applicant_name}"

#         # 3. Raccourcir le texte pour la notification (esthétique)
#         short_msg = payload.message_text
#         if len(short_msg) > 50:
#             short_msg = short_msg[:47] + "..."

#         # 4. Envoyer le Push en utilisant TA fonction existante ! 🚀
#         send_push_to_user(
#             user_id=receiver_id,
#             title=notification_title,
#             body=short_msg,
#             data={
#                 "type": "chat",
#                 "applicationId": payload.application_id
#             }
#         )

#         return {"status": "success", "message": "Notification envoyée"}

#     except Exception as e:
#         print(f"Erreur notification chat: {e}")
#         return JSONResponse({"status": "error", "message": str(e)}, status_code=500)





@app.post("/notify-chat")
async def trigger_chat_notification(payload: ChatNotificationModel):
    """
    Déclenche le Push avec distinction Entreprise / Candidat.
    """
    try:
        # 1. Récupérer les infos de la candidature
        app_doc = db.collection('applications').document(payload.application_id).get()
        if not app_doc.exists:
            return JSONResponse({"status": "error", "message": "Candidature introuvable"}, status_code=404)
        
        app_data = app_doc.to_dict()

        receiver_id = ""
        notification_title = ""

        # --- CAS : L'expéditeur est l'ENTREPRISE ---
        if payload.sender_id == app_data.get('companyId'):
            receiver_id = app_data.get('applicantId')

            # On récupère le nom dans la collection 'users'
            company_doc = db.collection("users").document(payload.sender_id).get()
            
            if company_doc.exists:
                company_data = company_doc.to_dict()
                # On cherche 'username' ou 'companyName'
                name = company_data.get('username') or company_data.get('companyName') or "Marabo"
                notification_title = f"Nouveau message de l'entreprise {name}"
            else:
                notification_title = "Nouveau message de l'entreprise"

        # --- CAS : L'expéditeur est le CANDIDAT ---
        else:
            receiver_id = app_data.get('companyId')
            applicant_name = app_data.get('applicantName', "Un candidat")
            notification_title = f"Nouveau message de {applicant_name}"

        # 2. Préparation du texte (le message_text contient déjà "📷 Photo" si c'est une image)
        short_msg = payload.message_text
        if len(short_msg) > 60:
            short_msg = short_msg[:57] + "..."

        # 3. Envoi du Push
        send_push_to_user(
            user_id=receiver_id,
            title=notification_title,
            body=short_msg,
            data={
                "type": "chat",
                "applicationId": payload.application_id
            }
        )

        return {"status": "success", "message": "Notification envoyée"}

    except Exception as e:
        print(f"Erreur notification chat: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)











@app.post("/notify-new-announcement")
async def notify_new_announcement(
    company_name: str = Body(...),
    title: str = Body(...),
    category: str = Body(...),
    opportunity_id: str = Body(...)
):
    try:
        notif_title = f"Nouvelle opportunité : {category}"
        notif_message = title 
        clean_id = str(opportunity_id).strip() # On nettoie l'ID une seule fois

        # --- 1. SAUVEGARDE DANS FIRESTORE D'ABORD ---
        # Comme ça, quand le push arrive, les données sont déjà prêtes
        users_ref = db.collection('users').where('role', '==', 'particulier').stream()
        batch = db.batch()
        count = 0
        total_saved = 0

        for user in users_ref:
            notif_ref = db.collection('users').document(user.id).collection('notifications').document()
            batch.set(notif_ref, {
                "title": notif_title,
                "message": notif_message,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "isRead": False,
                "type": "opportunity",
                "opportunityId": clean_id
            })
            
            count += 1
            total_saved += 1
            if count >= 500:
                batch.commit()
                batch = db.batch()
                count = 0
        
        if count > 0:
            batch.commit()

        # --- 2. ENVOI DU PUSH (SEULEMENT APRÈS LE COMMIT) ---
        send_push_to_topic(
            topic="particuliers",
            title=notif_title,
            body=f"{company_name} a publié : {notif_message}",
            data={
                "type": "opportunity",
                "opportunityId": clean_id, # Utilisation de l'ID nettoyé
                "screen": "/notifications"
            }
        )

        print(f"✅ Notification sauvegardée pour {total_saved} particuliers et push envoyé.")
        return {"status": "success", "message": "Notification envoyée et enregistrée."}

    except Exception as e:
        print(f"❌ Erreur lors de la notification globale: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)



def send_push_to_topic(topic: str, title: str, body: str, data: dict = None):
    """
    Envoie une notification push à tous les utilisateurs abonnés à un topic.
    """
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            topic=topic,
        )
        response = messaging.send(message)
        print(f"Successfully sent message to topic {topic}: {response}")
    except Exception as e:
        print(f"Error sending topic message: {e}")




#lorsque les entreprises publient une annonce
def send_opportunity_notification_to_all(opportunity_title, company_name, category, opp_id):
    # 1. Préparation du message pour le Topic 'new_sources'
    message = messaging.Message(
        notification=messaging.Notification(
            title=f"Nouvelle opportunité ({category}) 🚀",
            body=f"{company_name} vient de publier : {opportunity_title}"
        ),
        data={
            "type": "nouvelle_opportunite", # Pour que Flutter sache quoi ouvrir
            "opportunityId": str(opp_id)
        },
        topic="new_sources" # Le nom exact du topic dans ton main.dart
    )

    # 2. Envoi via Firebase
    try:
        response = messaging.send(message)
        print(f"✅ Notification de masse envoyée avec succès : {response}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de la notification de masse : {e}")

# Appel de la fonction après la création en base :
# send_opportunity_notification_to_all("Développeur Flutter", "Tech Corp", "Emploi", new_opp_ref.id)





@app.post("/notify-account-validated")
async def notify_account_validated(
    user_id: str = Body(...),
    company_name: str = Body(...)
):
    try:
        clean_user_id = str(user_id).strip()
        clean_company_name = str(company_name).strip() if company_name else "l'équipe"

        notif_title = "🎉 Votre compte entreprise est validé !"
        notif_message = f"Félicitations {clean_company_name}, votre structure a été approuvée. Vous pouvez dès à présent publier vos annonces !"

        # --- 1. SAUVEGARDE DE LA NOTIFICATION DANS LE FIRESTORE DE L'ENTREPRISE ---
        notif_ref = db.collection('users').document(clean_user_id).collection('notifications').document()
        notif_ref.set({
            "title": notif_title,
            "message": notif_message,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "isRead": False,
            "type": "account_activation",
            "opportunityId": "" # Pas d'opportunité liée ici
        })

        # --- 2. ENVOI DU PUSH DIRECT À L'ENTREPRISE (Via son Topic personnel) ---
        # Note : Dans ton main.dart Flutter, assure-toi que l'entreprise s'abonne à "user_SON_UID" à la connexion
        user_topic = f"user_{clean_user_id}"
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=notif_title,
                body=notif_message,
            ),
            data={
                "type": "account_activation",
                "screen": "create_annonce"
            },
            topic=user_topic,
        )
        
        response = messaging.send(message)
        print(f"✅ Notification de validation enregistrée et push envoyé au topic {user_topic}: {response}")
        
        return {"status": "success", "message": "Compte entreprise notifié avec succès."}

    except Exception as e:
        print(f"❌ Erreur lors de la notification de validation: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)



import os
import subprocess
def get_driver():
    chrome_options = Options()
    
    # --- 1. Options de performance et mode headless moderne ---
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # --- 2. Blindage anti-bots (Masquage de Selenium) ---
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Un User-Agent récent de vrai navigateur (Crucial)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    # --- 3. Détection / Installation automatique de Chrome sur Linux ---
    if os.name != 'nt':  # Si ce n'est pas Windows, on est sur Linux (Render/Railway)
        print("🐧 [SERVEUR LINUX] Vérification de la présence de Chrome...")
        
        # Le chemin où Playwright installe Chrome de manière isolée
        chrome_install_dir = os.path.expanduser("~/.cache/ms-playwright")
        
        # Forcer le téléchargement de Chrome par Playwright si absent
        if not os.path.exists(chrome_install_dir):
            print("📥 Chrome introuvable. Installation automatique du binaire Chrome en cours...")
            try:
                subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
                print("✅ Chrome installé avec succès sur le serveur !")
            except Exception as e_install:
                print(f"⚠️ Échec de l'installation automatique de Chrome: {e_install}")

        # Recherche du binaire téléchargé dans les sous-dossiers
        binary_path = None
        for root, dirs, files in os.walk(chrome_install_dir):
            for file in files:
                if file in ["chrome", "chromium"] and "chrome-linux" in root:
                    binary_path = os.path.join(root, file)
                    break
            if binary_path: 
                break

        if binary_path:
            print(f"🚀 Chrome autonome trouvé à : {binary_path}")
            chrome_options.binary_location = binary_path
        else:
            # Fallback sur les chemins classiques Linux
            for path in ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/google-chrome"]:
                if os.path.exists(path):
                    chrome_options.binary_location = path
                    print(f"🚀 Chrome standard trouvé à : {path}")
                    break
    else:
        print("💻 [LOCAL WINDOWS] Utilisation de la configuration par défaut de ton PC...")

    # --- 4. Lancement du driver Selenium avec injection JavaScript de sécurité ---
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # 🧪 SCRIPT MAGIQUE : Efface toute trace de 'navigator.webdriver' à chaque changement de page
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
        return driver
    except Exception as e:
        print(f"❌ Erreur critique Selenium : {e}")
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




# def build_opportunity(opp_id, title, category, source, date_start, date_end, url, badge_color, description="", isFeatured=False, image_url=None):
#     if not date_start:
#         date_start = date_end

#     # 1. On lance l'analyse IA
#     ai_data = analyze_opportunity_with_gemini(title, category, source, description)

#     # 2. Gestion intelligente de la localisation
#     # Si c'est Kaggle, c'est Global. Sinon, on prend la ville trouvée par l'IA. 
#     # Si l'IA n'a rien trouvé, on met "Côte d’Ivoire" par défaut.
#     location = "Global" if source == "Kaggle" else ai_data.get("exact_location", "Non spécifié")
#     if location == "Non spécifié" and source != "Kaggle":
#         location = "Côte d’Ivoire"

#     return {
#         "id": opp_id,
#         "source": source,
#         "title": title,
#         "category": category,
#         "views": 0,
#         "date_start": parse_date_fr(date_start),
#         "date_end": parse_date_fr(date_end),
        
#         # --- NOUVEAUX CHAMPS DATA-DRIVEN ---
#         "location": location, 
#         "company_name": ai_data.get("company_name", "Non spécifié"),
#         "required_skills": ai_data.get("required_skills", []),
#         "aiSummary": ai_data.get("summary", ""),
#         # -----------------------------------
        
#         "summary": f"Inscrivez-vous du {date_start} au {date_end}",
#         "badgeColor": badge_color,
#         "url": url,
#         "isFeatured": isFeatured,
#         "imageUrl": image_url if image_url else choose_image(source)
#     }





def build_opportunity(opp_id, title, category, source, date_start, date_end, url, badge_color, description="", isFeatured=False, image_url=None):
    if not date_start:
        date_start = date_end

    # 1. On lance l'analyse IA
    ai_data = analyze_opportunity_with_gemini(title, category, source, description)

    # 2. Gestion intelligente de la localisation
    location = "Global" if source == "Kaggle" else ai_data.get("exact_location", "Non spécifié")
    if location == "Non spécifié" and source != "Kaggle":
        location = "Côte d’Ivoire"

    # 3. Récupération du sous-thème extrait par Gemini (ex: 'tech', 'sante' ou None)
    ai_job_theme = ai_data.get("job_theme", None)

    return {
        "id": opp_id,
        "source": source,
        "title": title,
        "category": category,
        "views": 0,
        "date_start": parse_date_fr(date_start),
        "date_end": parse_date_fr(date_end),
        
        # --- NOUVEAUX CHAMPS DATA-DRIVEN ---
        "location": location, 
        "company_name": ai_data.get("company_name", "Non spécifié"),
        "required_skills": ai_data.get("required_skills", []),
        "aiSummary": ai_data.get("summary", ""),
        # -----------------------------------
        
        "summary": f"Inscrivez-vous du {date_start} au {date_end}",
        "badgeColor": badge_color,
        "url": url,
        "isFeatured": isFeatured,
        
        # 👇 LOGIQUE D'IMAGE SÉCURISÉE ET PROFESSIONNELLE 👇
        "imageUrl": image_url if image_url else choose_smart_image(category, ai_job_theme)
    }





@app.get("/opportunities")
def list_opportunities():
    docs = db.collection("opportunities").stream()
    opportunities = [doc.to_dict() for doc in docs]
    return {"opportunities": opportunities}








# Récupération des clés
GENIUS_API_KEY = os.getenv("GENIUS_API_KEY")
GENIUS_API_SECRET = os.getenv("GENIUS_API_SECRET")

@app.post("/create-payment")
def create_payment(
    amount: int = Body(...), 
    description: str = Body("Abonnement Marabo"),
    phone: str = Body(None),
    user_id: str = Body(...)
):
    transaction_id = str(uuid.uuid4())
    url = "https://pay.genius.ci/api/v1/merchant/payments"
    
    # Utilisation des variables sécurisées
    headers = {
        "X-API-Key": GENIUS_API_KEY,
        "X-API-Secret": GENIUS_API_SECRET,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "amount": amount,
        "description": description,
        "reference": transaction_id,
        "currency": "XOF",
        "metadata": {
            "user_id": user_id
        }
    }
    
    if phone:
        payload["customer_phone"] = phone

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        if response.status_code in [200, 201]:
            return {
                "status": "success",
                "checkout_url": data['data']['checkout_url'],
                "transaction_id": transaction_id
            }
        else:
            return {"status": "error", "details": data}

    except Exception as e:
        return {"status": "error", "message": str(e)}






@app.post("/webhook/geniuspay")
async def geniuspay_webhook(request: Request):
    try:
        payload = await request.json()
        print("🔔 WEBHOOK REÇU :", payload)
        
        # 1. On vérifie l'événement
        event = payload.get("event")
        
        # 2. On ouvre le "tiroir" data
        data = payload.get("data", {})
        
        status = data.get("status")
        gp_reference = data.get("reference") # Ex: SANDBOX_J2HCXU...
        
        # 3. On récupère le user_id qu'on avait caché dans les metadata
        metadata = data.get("metadata")
        user_id = None
        if isinstance(metadata, dict):
            user_id = metadata.get("user_id")

        # 4. On valide le paiement
        if event == "payment.success" and status == "completed":
            # On récupère le montant envoyé par GeniusPay
            amount = float(data.get("amount", 0))
            print(f"✅ Paiement validé (Ref: {gp_reference}) - Montant: {amount} FCFA")
            
            if user_id:
                print(f"🚀 Mise à jour Firestore pour l'utilisateur : {user_id}")
                
                # On crée la référence vers l'utilisateur
                user_ref = db.collection("users").document(user_id)
                
                # --- ACTION 1 : MISE À JOUR DU SOLDE ---
                # On utilise Increment pour ajouter le montant au solde existant
                user_ref.update({
                    "wallet_balance": firestore.Increment(amount)
                })
                
                # --- ACTION 2 : CRÉATION DE L'HISTORIQUE ---
                # On enregistre la transaction pour que l'entreprise la voie dans son historique
                db.collection("transactions").add({
                    "user_id": user_id,
                    "amount": amount,
                    "type": "top_up",
                    "provider": "geniuspay",
                    "reference": gp_reference,
                    "date": firestore.SERVER_TIMESTAMP # Heure exacte du serveur
                })
                
                print("💎 Portefeuille Marabo Pay rechargé avec succès !")
                return {"status": "success", "message": "Portefeuille mis à jour"}
                
            else:
                print("⚠️ Paiement validé, mais aucun user_id trouvé dans les metadata.")
                return {"status": "error", "message": "user_id manquant"}
            
    except Exception as e:
        print(f"⚠️ Erreur Webhook : {e}")
        return {"status": "error", "message": str(e)}






def delete_notifications_for_opportunity(opportunity_id):
    """
    Cherche et supprime toutes les notifications liées à une opportunité spécifique
    dans les sous-collections 'notifications' de tous les utilisateurs.
    """
    print(f"🧹 Nettoyage des notifications fantômes pour l'offre {opportunity_id}...")
    try:
        # Recherche via collection_group pour parcourir les sous-collections de tous les users
        notifications_ref = db.collection_group('notifications')\
            .where('opportunityId', '==', str(opportunity_id))\
            .stream()
        
        deleted_count = 0
        batch = db.batch()
        
        for notif in notifications_ref:
            batch.delete(notif.reference)
            deleted_count += 1
            
            # Commit par lots de 500 pour respecter les limites de Firestore
            if deleted_count % 500 == 0:
                batch.commit()
                batch = db.batch() 
                
        # Commit du reste
        if deleted_count % 500 != 0:
            batch.commit()
            
        print(f"✅ {deleted_count} notifications supprimées pour {opportunity_id}.")
        
    except Exception as e:
        print(f"❌ Erreur lors du nettoyage des notifications fantômes : {e}")




def check_expired_opportunities_and_notify():
    """
    Vérifie les offres expirées, change leur statut et notifie l'entreprise.
    Ne supprime PAS le document.
    """
    now = datetime.utcnow().date()
    processed_count = 0
    
    # On cherche les offres qui ne sont PAS encore marquées 'expired'
    docs = db.collection("opportunities").where("status", "!=", "expired").stream()

    for doc in docs:
        data = doc.to_dict()
        opp_id = doc.id
        
        # Récupération de la date
        date_str = data.get("date_end") or data.get("date_start")
        if not date_str: continue

        opp_date = None
        try:
             if isinstance(date_str, datetime):
                opp_date = date_str.date()
             else:
                for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                    try:
                        clean_date = str(date_str).strip()
                        opp_date = datetime.strptime(clean_date, fmt).date()
                        break
                    except ValueError: continue
        except: continue

        if opp_date and opp_date < now:
            
            # 1. Vérifier si c'est une offre Entreprise (qui a un postedBy)
            company_uid = data.get('postedBy')
            
            # 2. Mise à jour Firestore : On marque comme expiré
            db.collection("opportunities").document(opp_id).update({
                "status": "expired",
                "expirationNotified": True # Marqueur pour ne pas re-notifier
            })

            # 3. Si c'est une entreprise, on envoie le PUSH
            if company_uid and data.get('expirationNotified') != True:
                send_push_to_user(
                    user_id=company_uid,
                    title="Annonce Expirée ⏳",
                    body=f"Votre annonce '{data.get('title')}' est arrivée à échéance.",
                    # 👇 CORRECTION ICI : On ne garde qu'un seul "data" avec la bonne route Entreprise
                    data={"type": "expiration", "opp_id": opp_id, "screen": "/notifEntreprise"}
                )
                print(f"🔔 Notif expiration envoyée à {company_uid}")
            
            processed_count += 1

    return processed_count
    



def notify_new_opportunities():
    print("🔔 Vérification des opportunités non notifiées...")
    opp_ref = db.collection("opportunities")
    
    query = opp_ref.where("notified", "==", False).stream()
    
    for opp_doc in query:
        opp = opp_doc.to_dict()
        opp_id = opp_doc.id
        
        # 1. Vérifier si l'opportunité est déjà expirée
        date_str = opp.get("date_end") or opp.get("date_start")
        if is_opportunity_expired(date_str):
            print(f"⏳ Ignorée car déjà expirée : {opp.get('title')}")
            # On marque comme notifiée et expirée pour ne plus la traiter, 
            # MAIS on n'envoie pas de push et on ne sauvegarde rien chez l'user.
            opp_ref.document(opp_id).update({
                "notified": True,
                "status": "expired"
            })
            continue

        # 2. Si elle est valide, on notifie les utilisateurs intéressés
        tokens = get_interested_users(opp.get("category", ""))
        if tokens:
            send_notification(
                tokens=tokens,
                title=opp.get("title", "Nouvelle opportunité"),
                body=opp.get("aiSummary", "Découvrez cette nouvelle offre !"),
                # 👇 C'est ici qu'on prépare le terrain pour Flutter au clic
                data={
                    "opportunityId": str(opp_id), 
                    "screen": "/details_opportunite" # Adapte ce nom selon ta route Flutter
                }
            )
        
        # 3. Marquer comme notifié dans la base
        opp_ref.document(opp_id).update({"notified": True})
        print(f"✅ Opportunité notifiée: {opp.get('title')}")


# async def cron_notify_async():
#     while True:
#         try:
#             # check_expired_opportunities_and_notify() remplace delete_expired...
#             check_expired_opportunities_and_notify() 
#             notify_new_opportunities()
#         except Exception as e:
#             print("⚠️ Erreur dans le cron:", e)
#         await asyncio.sleep(60) # Vérifie toutes les minutes



# @app.on_event("startup")
# async def start_async_crons():
#     asyncio.create_task(cron_notify_async())


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
    # On tape directement sur la bonne URL 2026
    target_url = "https://gucaci.ciconcours.com/concours-2026/liste-concours/ENA/1/2"
    used_url = "https://gucaci.ciconcours.com/" # URL par défaut si tout plante
    
    soup = None
    
    # 1. TENTATIVE DE CONNEXION À L'URL 2026
    try:
        resp = requests.get(target_url, timeout=10)
        if resp.status_code == 200:
            temp_soup = BeautifulSoup(resp.text, "html.parser")
            # On vérifie si le tableau est bien là (et non pas une page de maintenance)
            if temp_soup.select("div.my-3 table#table-liste tbody tr"):
                soup = temp_soup
                used_url = target_url
    except requests.exceptions.RequestException:
        pass # Si ça plante, on passe directement au plan de secours plus bas
        
    items = []
    
    # 2. SI LE SITE FONCTIONNE (on a trouvé le tableau)
    if soup:
        rows = soup.select("div.my-3 table#table-liste tbody tr")
        for tr in rows:
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cols) < 4:
                continue
                
            _, title, date_start, date_end = cols[:4]

            # On cherche le lien du communiqué PDF
            link_tag = tr.find("a", string=lambda t: t and "communiqué" in t.lower())
            link = link_tag['href'] if link_tag and link_tag.has_attr('href') else used_url

            opp_id = str(generate_numeric_id(title, date_end))
            source = "GUCACI ENA"
            
            check_and_notify_new_source(source)

            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category="Concours",
                source=source,
                date_start=date_start,
                date_end=date_end,
                url=used_url,  # <-- Correction ici : on utilise le lien du communiqué !
                badge_color="red",
                description=f"Du {date_start} au {date_end}, concours organisé par GUCACI ENA.",
                isFeatured=True
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


            source = "INFAS"

            # ✅ AJOUT ICI
            check_and_notify_new_source(source)
            
            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category="Concours",
                source="INFAS",
                date_start=date_start,
                date_end=date_end,
                url=url,
                badge_color="green",
                description=f"Du {date_start} au {date_end}, concours organisé par  INFAS.",
                isFeatured=True
            ))
    return items



# ---------- SCRAPING CAFOP VIA ABLANIAN ----------
def scrape_cafop():
    url = "https://ablanian.ci/concours_admin/view.php?slug=cafopia"
    items = []

    try:
        # On utilise un User-Agent pour éviter d'être bloqué
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"⚠️ Impossible d'accéder à {url} (Code: {resp.status_code})")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Extraction du TITRE
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            title = "Concours CAFOP 2026 (Instituteurs Adjoints)"

        # 2. Extraction des DATES (Adaptée à la nouvelle structure HTML)
        date_start, date_end = "", ""
        
        page_text = soup.get_text(separator=" ", strip=True)

        # 🎯 NOUVEAU PATTERN : On cherche "Début :" et "Clôture :" séparément
        match_debut = re.search(r"Début\s*:\s*(\d{2}/\d{2}/\d{4})", page_text, re.IGNORECASE)
        match_cloture = re.search(r"Clôture\s*:\s*(\d{2}/\d{2}/\d{4})", page_text, re.IGNORECASE)
        
        if match_debut and match_cloture:
            date_start = match_debut.group(1)
            date_end = match_cloture.group(1)
        else:
            # FALLBACK FORT : Si le design change encore, on force les dates officielles
            date_start = "08/12/2025" 
            date_end = "13/02/2026"

        # 3. Extraction de la DESCRIPTION
        conditions = "Conditions non spécifiées."
        age_match = re.search(r"Âge requis\s*(.*?)(Nationalité|Diplômes|$)", page_text, re.IGNORECASE)
        diploma_match = re.search(r"Diplômes acceptés\s*(.*?)(Condition|Autres|$)", page_text, re.IGNORECASE)
        
        desc_parts = []
        if age_match:
            desc_parts.append(f"Âge : {age_match.group(1).strip()}")
        if diploma_match:
            desc_parts.append(f"Diplôme : {diploma_match.group(1).strip()}")
            
        if desc_parts:
            conditions = " | ".join(desc_parts)
        else:
            conditions = "Concours direct d'entrée dans les CAFOP (Instituteurs Adjoints)."

        description = f"{conditions}. Période : Du {date_start} au {date_end}."

        # 4. Construction de l'objet Opportunité
        year_match = re.search(r"20\d{2}", title)
        year = year_match.group(0) if year_match else "2026"
        
        opp_id = str(generate_numeric_id("CAFOP", year))
        source_name = "CAFOP (Ablanian)"

        check_and_notify_new_source(source_name)

        items.append(build_opportunity(
            opp_id=opp_id,
            title=title,
            category="Concours",
            source=source_name,
            date_start=date_start,
            date_end=date_end,
            url=url, 
            badge_color="orange",
            description=description,
            isFeatured=True
        ))

    except Exception as e:
        print(f"❌ Erreur scraping CAFOP (Ablanian) : {e}")
        # FALLBACK CRITIQUE
        try:
            items.append(build_opportunity(
                opp_id="CAFOP_FALLBACK_2026",
                title="Concours CAFOP 2026 (Info récupérée)",
                category="Concours",
                source="DECO",
                date_start="08/12/2025", 
                date_end="13/02/2026",
                url="https://men-deco.org",
                badge_color="red",
                description="Le site source est temporairement inaccessible. Les inscriptions pour le CAFOP 2026 sont officiellement lancées.",
                isFeatured=True # N'oublie pas le isFeatured ici aussi !
            ))
        except:
            pass

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
                    description=f"Du {date_start} au {date_end}, concours organisé par GUCACI ENA.",
                    isFeatured=True
                ))
    return items



# ---------- SCRAPING NOVOJOBS (Version Selenium Optimisée) ----------
def scrape_novojob():
    urls = [
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/372-production-methode-industrie",
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/351-metiers-banque-et-assurances",
        "https://www.novojob.com/cote-d-ivoire/offres-d-emploi/offres-par-fonction/358-commercial-technico-commercial-service-client"
    ]
    
    items = []
    driver = None 

    mois_map = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
    }

    try:
        # 1. On lance le navigateur virtuel
        driver = get_driver()

        for url in urls:
            try:
                print(f"🔄 Scraping Novojob: {url}")
                driver.get(url)
                
                # 2. PAUSE : On attend que le site charge le contenu
                time.sleep(3) 

                # 3. On récupère le code source
                soup = BeautifulSoup(driver.page_source, "html.parser")
                jobs = soup.select("div.row-fluid.job-details.pointer")
                
                for job in jobs:
                    try:
                        # --- Extraction des données ---
                        a_tag = job.find("a", title=True)
                        title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
                        
                        # Lien complet
                        job_url = urljoin("https://www.novojob.com", a_tag['href']) if a_tag and a_tag.has_attr('href') else url

                        # Entreprise
                        company_tag = job.select_one("div.contact h6")
                        company = company_tag.get_text(strip=True) if company_tag else "Entreprise inconnue"

                        # Localisation
                        location_tag = job.select_one("i.fa-map-marker + span")
                        location = location_tag.get_text(strip=True) if location_tag else "Côte d’Ivoire"

                        # --- Gestion de la Date ---
                        date_start = datetime.today().strftime("%d/%m/%Y") # Valeur par défaut
                        
                        date_span = job.select_one("span.spaced-right i.fa-clock-o")
                        if date_span and date_span.parent:
                            date_tag = date_span.parent
                            # On retire l'icône
                            for i_tag in date_tag.find_all("i"):
                                i_tag.extract()
                            raw_date = date_tag.get_text(strip=True)

                            try:
                                parts = raw_date.split()
                                if len(parts) >= 2:
                                    jour = parts[0]
                                    mois = mois_map.get(parts[1].lower(), "01")
                                    annee = str(datetime.today().year)
                                    date_start = f"{jour.zfill(2)}/{mois}/{annee}"
                            except Exception:
                                pass # On garde la date du jour par défaut en cas d'erreur

                        # Calcul date fin (+30 jours par défaut)
                        try:
                            date_obj = datetime.strptime(date_start, "%d/%m/%Y")
                            date_end = (date_obj + timedelta(days=30)).strftime("%d/%m/%Y")
                        except Exception:
                            date_end = date_start

                        # --- Construction de l'objet ---
                        opp_id = str(generate_numeric_id(title, date_end))
                        source_name = "NovoJob"

                        # ✅ APPEL IMPORTANT : Notification Nouvelle Source
                        check_and_notify_new_source(source_name)
                        
                        items.append(build_opportunity(
                            opp_id=opp_id,
                            title=title,
                            category="Emplois",
                            source=source_name,
                            date_start=date_start,
                            date_end=date_end,
                            url=job_url,
                            badge_color="purple",
                            description=f"{title} chez {company}, situé à {location}."
                        ))

                    except Exception as e_job:
                        print(f"⚠️ Erreur parsing job individuel: {e_job}")
                        continue

            except Exception as e_url:
                print(f"⚠️ Erreur lors du scraping de l'URL Novojob: {e_url}")
                continue 

    except Exception as e_main:
        print(f"❌ Erreur critique Selenium Novojob: {e_main}")

    finally:
        # 4. TRÈS IMPORTANT : Fermeture propre
        if driver:
            driver.quit()
            print("🚪 Navigateur Selenium fermé.")

    return items



# ---------- SCRAPING SOCIUMJOB (Selenium) ----------
def scrape_sociumjob():
    url = "https://sociumjob.com/jobs"
    items = []
    driver = None

    try:
        # 1. On lance le navigateur virtuel
        driver = get_driver()
        print(f"🔄 Scraping SociumJob: {url}")
        driver.get(url)
        
        # 2. PAUSE : On attend que React/Next.js charge les offres d'emploi
        time.sleep(5) 
        
        # 3. Récupération du code source
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # 🎯 NOUVEAU CIBLAGE : On cherche les div qui ont l'attribut "data-jid"
        jobs_cards = soup.find_all("div", attrs={"data-jid": True})
        
        seen_urls = set()

        for job in jobs_cards:
            try:
                # --- Extraction de l'URL via le slug ---
                jid = job.get("data-jid")
                if not jid:
                    continue
                    
                job_url = f"https://sociumjob.com/jobs/{jid}"
                
                # Éviter les doublons
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # --- Extraction du Titre ---
                title_tag = job.find("h3", class_="job-title")
                title = title_tag.get_text(strip=True) if title_tag else None
                
                if not title or len(title) < 3:
                    continue

                # --- Extraction de la Localisation ---
                # Dans ton HTML, la ville est dans un <p> avec la classe "truncate"
                loc_tag = job.select_one("p.truncate")
                location = loc_tag.get_text(strip=True) if loc_tag else "Côte d'Ivoire"

                # --- Extraction de la Date ---
                # Dans ton HTML, la date est dans une balise <time>
                time_tag = job.find("time")
                if time_tag:
                    date_start = time_tag.get_text(strip=True) # Ex: 24/08/2024
                else:
                    date_start = datetime.today().strftime("%d/%m/%Y")

                # Calcul de la date de fin (approximatif : on ajoute 30 jours à la date_start)
                try:
                    date_obj = datetime.strptime(date_start, "%d/%m/%Y")
                    date_end = (date_obj + timedelta(days=30)).strftime("%d/%m/%Y")
                except Exception:
                    date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

                # --- Construction de l'objet ---
                opp_id = str(generate_numeric_id(title, date_end))
                source_name = "SociumJob"

                # ✅ APPEL IMPORTANT : Notification Nouvelle Source
                check_and_notify_new_source(source_name)
                
                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category="Emplois",
                    source=source_name,
                    date_start=date_start,
                    date_end=date_end,
                    url=job_url,
                    badge_color="teal", 
                    description=f"{title} - Poste basé à {location}."
                ))

            except Exception as e_job:
                print(f"⚠️ Erreur parsing job individuel SociumJob: {e_job}")
                continue

    except Exception as e_main:
        print(f"❌ Erreur critique Selenium SociumJob: {e_main}")

    finally:
        if driver:
            driver.quit()
            print("🚪 Navigateur Selenium fermé (SociumJob).")

    return items


# ---------- ROUTE DE TEST INDIVIDUEL ----------
# @app.get("/test-socium")
# def test_scrape_sociumjob_only():
#     print("🚀 Lancement du test unitaire pour SociumJob...")
    
#     try:
#         # 1. On lance uniquement notre nouveau scraper
#         ops = scrape_sociumjob()
        
#         # 2. On renvoie les données récupérées pour inspection visuelle
#         return {
#             "message": "Test SociumJob terminé",
#             "total_trouve": len(ops),
#             "donnees": ops # Tu verras exactement la structure des offres ici
#         }
        
#     except Exception as e:
#         print(f"❌ Erreur lors du test : {e}")
#         return {
#             "message": "Erreur lors du scraping",
#             "erreur": str(e)
#         }






# ---------- ROUTE DE TEST INDIVIDUEL ENA ----------
# @app.get("/test-ena")
# def test_scrape_ena_only():
#     print("🚀 Lancement du test unitaire pour l'ENA 2026...")
    
#     try:
#         # 1. On lance uniquement notre scraper nettoyé
#         ops = scrape_ena_directs()
        
#         # 2. On renvoie les données récupérées pour inspection dans le navigateur
#         return {
#             "message": "Test ENA terminé",
#             "total_trouve": len(ops),
#             "donnees": ops # Tu pourras vérifier les dates 2026 et les liens ici
#         }
        
#     except Exception as e:
#         print(f"❌ Erreur lors du test ENA : {e}")
#         return {
#             "message": "Erreur lors du scraping de l'ENA",
#             "erreur": str(e)
#         }






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


        source = "DAAD"

        # ✅ AJOUT ICI
        check_and_notify_new_source(source)

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

# def scrape_educarriere(max_pages: int = 1):
#     base_url = "https://emploi.educarriere.ci/nos-offres"
#     items = []

#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
#         "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
#     }



#     def normalize_category(cat: str) -> str:
#         cat = cat.lower()
#         if "emploi" in cat:
#             return "Emplois"
#         elif "stage" in cat:
#             return "Stages"
#         elif "formation" in cat:
#             return "Formations"
#         else:
#             return cat.capitalize()



#     for page in range(1, max_pages + 1):
#         url = f"{base_url}?page={page}" if page > 1 else base_url

#         try:
#             resp = requests.get(url, headers=headers, timeout=10, verify=False)
#             resp.raise_for_status()
#         except requests.exceptions.SSLError:
#             print(f"[SSL ERROR] Impossible de se connecter à {url}")
#             continue

#         soup = BeautifulSoup(resp.text, "html.parser")

#         offers = soup.select("div.rt-post.post-md.style-8")
#         for offer in offers:
#             # URL et titre
#             a_tag = offer.select_one("h4.post-title a")
#             title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
#             job_url = a_tag["href"] if a_tag and a_tag.has_attr("href") else url

#             # Catégorie (Emploi, Stage, Emploi (CDD), etc.)
#             category_tag = offer.select_one("a.racing")
#             raw_category = category_tag.get_text(strip=True) if category_tag else "Non spécifié"
#             category = normalize_category(raw_category)

#             # Dates
#             metas = offer.select("span.rt-meta li")
#             date_start, date_end = None, None
#             for li in metas:
#                 text = li.get_text(strip=True)
#                 if "Date d'édition" in text:
#                     try:
#                         raw = li.find("span").get_text(strip=True)
#                         date_start = datetime.strptime(raw, "%d/%m/%Y").strftime("%d/%m/%Y")
#                     except Exception:
#                         date_start = datetime.today().strftime("%d/%m/%Y")
#                 if "Date limite" in text:
#                     try:
#                         raw = li.find("span").get_text(strip=True)
#                         date_end = datetime.strptime(raw, "%d/%m/%Y").strftime("%d/%m/%Y")
#                     except Exception:
#                         date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

#             # fallback si manquant
#             if not date_start:
#                 date_start = datetime.today().strftime("%d/%m/%Y")
#             if not date_end:
#                 date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

#             # ID unique
#             opp_id = str(generate_numeric_id(title, date_end))

#             source = "EMPLOI EDUCARRIERE"

#             # ✅ AJOUT ICI
#             check_and_notify_new_source(source)

#             items.append(build_opportunity(
#                 opp_id=opp_id,
#                 title=title,
#                 category=category,   # dynamique
#                 source="Educarriere",
#                 date_start=date_start,
#                 date_end=date_end,
#                 url=job_url,
#                 badge_color="purple",
#                 description=f"{title} ({category}) - Voir plus sur Educarriere."
#             ))

#     return items




import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def scrape_educarriere(max_pages: int = 28): 
    items = []

    # 🟢 CORRECTION : On remet ton User-Agent ultra-complet pour passer la sécurité
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
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

    print("🔵 Démarrage du scraping Educarriere...")

    for page in range(1, max_pages + 1):
        if page == 1:
            url = "https://emploi.educarriere.ci/nos-offres"
        else:
            url = f"https://emploi.educarriere.ci/emploi/page/emploi/{page}"

        print(f"   📄 Scraping de la page {page} ({url})...")

        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"      [ERREUR] Impossible de se connecter à {url} : {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        offers = soup.select("div.rt-post.post-md.style-8")
        
        # 🟢 VÉRIFICATION ET DÉBOGAGE : Si c'est vide, on regarde sur quelle page on a atterri
        if not offers:
            page_title = soup.title.get_text(strip=True) if soup.title else "Titre inconnu"
            print(f"      ⚠️ Aucune offre trouvée sur la page {page}. Le site a renvoyé la page : '{page_title}'")
            # On s'arrête ici pour ne pas scraper 28 pages dans le vide
            break

        for offer in offers:
            try:
                # URL et titre
                a_tag = offer.select_one("h4.post-title a")
                title = a_tag.get_text(strip=True) if a_tag else "Titre non spécifié"
                job_url = a_tag["href"] if a_tag and a_tag.has_attr("href") else url

                # Catégorie
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

                # Fallback si manquant
                if not date_start:
                    date_start = datetime.today().strftime("%d/%m/%Y")
                if not date_end:
                    date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")
# ID unique
                opp_id = str(generate_numeric_id(title, date_end))
                source = "EMPLOI EDUCARRIERE"

                try:
                    check_and_notify_new_source(source)
                except Exception:
                    pass

                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category=category,
                    source="Educarriere",
                    date_start=date_start,
                    date_end=date_end,
                    url=job_url,
                    badge_color="purple",
                    description=f"{title} ({category}) - Voir plus sur Educarriere."
                ))
            except Exception as e:
                print(f"      ⚠️ Erreur lors du traitement d'une offre Educarriere : {e}")
                continue

    print(f"✅ Educarriere terminé : {len(items)} offres récupérées au total.")
    return items




@app.get("/scrape/educarriere")
def trigger_educarriere_scrape():
    print("🚀 Lancement manuel du scraper Educarriere...")
    try:
        # On lance le scraping (qui est configuré par défaut sur 28 pages)
        data = scrape_educarriere() 
        
        count = 0
        # Sauvegarde dans Firestore
        for item in data:
            # On récupère l'ID unique de l'offre
            item_id = item.get("id") or item.get("opp_id") 
            
            if not item_id:
                continue 
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            # On vérifie si l'offre n'existe pas déjà dans la base de données
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping Educarriere terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success", 
            "added": count, 
            "total_found": len(data),
            "data": data
        }
        
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping Educarriere : {e}")
        return {"status": "error", "message": str(e)}






def scrape_rmo_jobcenter(max_pages: int = 1):
    base_url = "https://www.rmo-jobcenter.com/fr/cote-d-ivoire/offres-emploi.html"
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def normalize_category(sector: str) -> str:
        sector_lower = sector.lower()
        if "stage" in sector_lower:
            return "Stages"
        elif "formation" in sector_lower:
            return "Formations"
        else:
            return "Emplois" # RMO propose majoritairement des CDI/CDD/Intérim

    print("🔵 Démarrage du scraping RMO Job Center...")

    for page in range(1, max_pages + 1):
        # D'après ton HTML, RMO affiche une pagination classique. Si besoin de plusieurs pages,
        # l'URL prend généralement un paramètre ?page=X. Comme le site regroupe souvent tout, on l'anticipe.
        url = base_url if page == 1 else f"{base_url}?page={page}"

        print(f"   📄 Scraping de la page {page} ({url})...")

        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"      [ERREUR] Impossible de se connecter à {url} : {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # On cible toutes les lignes de tableau ayant la classe ligne_offre
        offers = soup.select("tr.ligne_offre")
        
        if not offers:
            page_title = soup.title.get_text(strip=True) if soup.title else "Titre inconnu"
            print(f"      ℹ️ Aucune offre trouvée sur la page {page}. (Page détectée : '{page_title}')")
            break

        for offer in offers:
            try:
                tds = offer.select("td")
                if len(tds) < 4:
                    continue

                # 1. Récupération de l'ID unique fourni par RMO
                opp_id = offer.get("id") or ""
                
                # 2. Titre et URL de l'offre
                a_tag = tds[1].select_one("a.bleu")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                
                # Reconstruction de l'URL absolue
                if href.startswith("http"):
                    job_url = href
                elif href.startswith("/"):
                    job_url = f"https://www.rmo-jobcenter.com{href}"
                else:
                    job_url = f"https://www.rmo-jobcenter.com/{href}"

                # 3. Catégorie et secteur
                sector = tds[2].get_text(strip=True)
                category = normalize_category(sector)

                # 4. Extraction propre des dates par Regex (Format JJ/MM/AAAA)
                raw_date_start = tds[0].get_text(strip=True)
                date_start_match = re.search(r"\d{2}/\d{2}/\d{4}", raw_date_start)
                date_start = date_start_match.group(0) if date_start_match else datetime.today().strftime("%d/%m/%Y")

                raw_date_end = tds[3].get_text(strip=True)
                date_end_match = re.search(r"\d{2}/\d{2}/\d{4}", raw_date_end)
                date_end = date_end_match.group(0) if date_end_match else (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")

                # Sécurité si l'ID HTML était manquant
                if not opp_id:
                    opp_id = str(generate_numeric_id(title, date_end))

                source = "RMO JOB CENTER"
                try:
                    check_and_notify_new_source(source)
                except Exception:
                    pass

                # Construction de l'opportunité standardisée pour Marabo
                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category=category,
                    source="RMO Job Center",
                    date_start=date_start,
                    date_end=date_end,
                    url=job_url,
                    badge_color="blue",
                    description=f"Poste : {title} - Secteur : {sector}. Retrouvez tous les détails et postulez sur RMO Job Center."
                ))
            except Exception as e:
                print(f"      ⚠️ Erreur lors du traitement d'une offre RMO : {e}")
                continue

    print(f"✅ RMO Job Center terminé : {len(items)} offres récupérées au total.")
    return items






@app.get("/scrape/rmo")
def trigger_rmo_scrape():
    print("🚀 Lancement manuel du scraper RMO Job Center...")
    try:
        # On lance le scraping
        data = scrape_rmo_jobcenter() 
        
        count = 0
        # Sauvegarde sécurisée dans Firestore avec vérification des doublons
        for item in data:
            item_id = item.get("id") or item.get("opp_id") 
            
            if not item_id:
                continue 
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping RMO terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success", 
            "added": count, 
            "total_found": len(data),
            "data": data
        }
        
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping RMO : {e}")
        return {"status": "error", "message": str(e)}



import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta

def scrape_agence_emploi_jeunes(max_pages_per_city=3):
    VILLES_URLS = {
        "Bouaké": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=10",
        "Aboisso": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=3",
        "Adjamé": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=4",
        "Koumassi": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=22",
        "Katiola": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=20",
        "San-Pédro": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=27",
        "Guiglo": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=19",
        "Korhogo": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=21",
        "Gagnoa": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=18",
        "Béoumi": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=6",
        "Bongouanou": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=8",
        "Abobo": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=2",
        "Daloa": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=12",
        "Man": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=23",
        "Bondoukou": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=7",
        "Ferkéssédougou": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=17",
        "Yopougon": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=33",
        "Boundiali": "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=11",
        # Ajoute les autres villes ici...
    }

    items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    print("🔵 Démarrage du scraping AEJ avec Corrections Dates et Localité...")

    for ville, base_url in VILLES_URLS.items():
        print(f"   📍 Recherche à {ville}...")
        
        current_page = 1
        last_page = 1 
        
        while current_page <= last_page and current_page <= max_pages_per_city:
            if current_page == 1:
                url = base_url
            else:
                url = f"{base_url}&page={current_page}" if "?" in base_url else f"{base_url}?page={current_page}"
                
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.get(url, headers=headers, timeout=15, verify=False)
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                break 

            soup = BeautifulSoup(resp.text, "html.parser")
            app_div = soup.find("div", id="app")

            if not app_div or not app_div.has_attr("data-page"):
                break
                
            try:
                page_data = json.loads(app_div["data-page"])
                props = page_data.get("props", {})
                
                offres_brutes = []
                if "offres" in props:
                    if isinstance(props["offres"], dict) and "data" in props["offres"]:
                        offres_brutes = props["offres"]["data"]
                        if current_page == 1:
                            last_page = props["offres"].get("last_page", 1)
                    elif isinstance(props["offres"], list):
                        offres_brutes = props["offres"]
                
                if not offres_brutes:
                    break 
                
                for offer in offres_brutes:
                    try:
                        title = str(offer.get("titre") or offer.get("intitule") or "Titre non spécifié")
                        reference = str(offer.get("reference") or offer.get("id") or "")
                        job_url = f"https://agenceemploijeunes.ci/offres-emploi/{reference}" if reference else url
                        
                        company = "Agence Emploi Jeunes"
                        if isinstance(offer.get("entreprise"), dict):
                            company = offer.get("entreprise").get("nom", company)
                        elif offer.get("nom_entreprise"):
                            company = offer.get("nom_entreprise")
                        
                        category = "Emplois"
                        type_contrat = ""
                        tc_obj = offer.get("type_contrat")
                        if isinstance(tc_obj, dict):
                            type_contrat = str(tc_obj.get("libelle", ""))
                        else:
                            type_contrat = str(tc_obj or offer.get("type_contrat", ""))

                        if "stage" in type_contrat.lower():
                            category = "Stages"
                        elif "formation" in type_contrat.lower():
                            category = "Formations"
# --- 🟢 CORRECTION DES DATES (Scanner agressif) ---
                        date_start = datetime.today().strftime("%d/%m/%Y")
                        for k in ["created_at", "createdAt", "date_publication", "date_creation", "published_at"]:
                            val = offer.get(k)
                            if val and isinstance(val, str) and len(val) >= 10:
                                try:
                                    date_start = datetime.strptime(val[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                                    break
                                except: pass

                        date_end = (datetime.today() + timedelta(days=30)).strftime("%d/%m/%Y")
                        for k in ["date_cloture", "dateCloture", "date_limite", "dateLimite", "date_fin", "dateFin", "deadline", "expires_at"]:
                            val = offer.get(k)
                            if val and isinstance(val, str) and len(val) >= 10:
                                try:
                                    date_end = datetime.strptime(val[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                                    break
                                except: pass
                        # --------------------------------------------------

                        full_description = f"Entreprise: {company}\nLieu: {ville}\nType de contrat: {type_contrat}"
                        desc_texte = offer.get("description") or offer.get("profil_recherche")
                        if desc_texte:
                            clean_desc = BeautifulSoup(str(desc_texte), "html.parser").get_text(separator=" ", strip=True)
                            full_description += f"\nDescription: {clean_desc[:200]}..."

                        opp_id = str(generate_numeric_id(title, job_url))
                        source_name = "Agence Emploi Jeunes"

                        try:
                            check_and_notify_new_source(source_name)
                        except Exception:
                            pass

                        # 1. On utilise ta fonction normalement
                        opp = build_opportunity(
                            opp_id=opp_id,
                            title=title,
                            category=category,
                            source=source_name,
                            date_start=date_start,
                            date_end=date_end,
                            url=job_url,
                            badge_color="green",
                            description=full_description
                        )

                        # --- 🟢 CORRECTION DE LA VILLE (Écrase "Côte d'Ivoire") ---
                        if isinstance(opp, dict):
                            opp["location"] = ville
                        # ----------------------------------------------------------

                        items.append(opp)
                    except Exception as e:
                        print(f"      ⚠️ Erreur sur une offre spécifique (ignorée) : {e}")
                        continue
                        
            except Exception as e:
                print(f"      ⚠️ Erreur globale lors du traitement de la page {current_page} : {e}")
            
            current_page += 1

    print(f"✅ AEJ terminé : {len(items)} offres récupérées au total.")
    return items



@app.get("/scrape/aej")
def trigger_aej_scrape():
    print("🚀 Lancement manuel du scraper Agence Emploi Jeunes...")
    try:
        # 👇 MODIFICATION ICI : On a retiré (max_pages=1) car on gère maintenant par villes
        data = scrape_agence_emploi_jeunes()
        
        count = 0
        # Sauvegarde en base de données (Firestore)
        for item in data:
            # Assure-toi que la clé correspond bien à ce que retourne ta fonction build_opportunity ("id" ou "opp_id")
            item_id = item.get("id") or item.get("opp_id") 
            
            if not item_id:
                continue # Sécurité au cas où un id serait vide
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            # On vérifie si l'ID existe déjà pour ne pas créer de doublons
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping AEJ terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success", 
            "added": count, 
            "total_found": len(data),
            "data": data
        }
        
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping AEJ : {e}")
        return {"status": "error", "message": str(e)}



from fastapi.responses import HTMLResponse

@app.get("/debug/aej", response_class=HTMLResponse)
def debug_aej():
    """Cette route va nous montrer ce que le robot Python voit réellement"""
    import requests
    url = "https://agenceemploijeunes.ci/offres-emploi?agence_regionale=10"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        return resp.text # On renvoie directement le code source brut reçu par Python
    except Exception as e:
        return f"Erreur de connexion : {e}"


# désactiver les warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)






def scrape_emploi_ci(max_pages: int = 1):
    base_url = "https://www.emploi.ci/recherche-jobs-cote-ivoire"
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def normalize_category(contract_type: str, title: str) -> str:
        text = f"{contract_type} {title}".lower()
        if "stage" in text or "internship" in text:
            return "Stages"
        elif "formation" in text:
            return "Formations"
        else:
            return "Emplois"

    print("🔵 Démarrage du scraping Emploi.ci...")

    for page in range(1, max_pages + 1):
        # Page 1: url de base | Page 2: ?page=1 | Page 3: ?page=2...
        url = base_url if page == 1 else f"{base_url}?page={page - 1}"
        print(f"   📄 Scraping de la page {page} ({url})...")

        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"      [ERREUR] Impossible de se connecter à {url} : {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.card.card-job")
        
        if not cards:
            print(f"      ℹ️ Aucune offre trouvée sur la page {page}.")
            break

        for card in cards:
            try:
                # 1. Extraction de l'URL de l'offre et de son ID unique
                job_url = card.get("data-href") or ""
                if not job_url:
                    a_title = card.select_one("div.card-job-detail h3 a")
                    if a_title:
                        href = a_title.get("href", "")
                        job_url = f"https://www.emploi.ci{href}" if href.startswith("/") else href
                
                if not job_url:
                    continue

                # On extrait l'identifiant numérique en fin d'URL
                id_match = re.search(r"-(\d+)$", job_url.strip())
                opp_id = id_match.group(1) if id_match else ""

                # 2. Titre et Entreprise
                title_tag = card.select_one("div.card-job-detail h3 a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                company_tag = card.select_one(".card-job-company")
                company = company_tag.get_text(strip=True) if company_tag else "Entreprise confidentielle"

                # 3. Extraction de la description succincte
                desc_tag = card.select_one(".card-job-description p")
                description_text = desc_tag.get_text(strip=True) if desc_tag else ""

                # 4. Parsing des détails du contrat et de la localisation (ul > li)
                contract_type = "Non spécifié"
                region = "Côte d'Ivoire"
                li_elements = card.select("div.card-job-detail ul li")
                
                for li in li_elements:
                    li_text = li.get_text().lower()
                    if "contrat proposé" in li_text:
                        strong = li.select_one("strong")
                        if strong:
                            contract_type = strong.get_text(strip=True)
                    elif "région de" in li_text:
                        strong = li.select_one("strong")
                        if strong:
                            region = strong.get_text(strip=True)

                # 5. Normalisation de la catégorie Marabo
                category = normalize_category(contract_type, title)
# 6. Extraction et formatage de la date de publication (YYYY-MM-DD -> DD/MM/YYYY)
                time_tag = card.select_one("time")
                if time_tag and time_tag.get("datetime"):
                    raw_date = time_tag.get("datetime")
                    try:
                        dt_start = datetime.strptime(raw_date, "%Y-%m-%d")
                        date_start = dt_start.strftime("%d/%m/%Y")
                    except ValueError:
                        date_start = datetime.today().strftime("%d/%m/%Y")
                else:
                    date_start = datetime.today().strftime("%d/%m/%Y")

                # Emploi.ci ne fournit pas de date de fin sur la carte, on ajoute 30 jours par défaut
                dt_start_obj = datetime.strptime(date_start, "%d/%m/%Y")
                date_end = (dt_start_obj + timedelta(days=30)).strftime("%d/%m/%Y")

                if not opp_id:
                    opp_id = str(generate_numeric_id(title, date_end))

                source = "Emploi.ci"
                try:
                    check_and_notify_new_source(source)
                except Exception:
                    pass

                # Choix d'une couleur dynamique pour l'affichage de l'étiquette
                badge_color = "green" if category == "Emplois" else ("orange" if category == "Stages" else "purple")

                # Assemblage de la description formatée
                full_description = (
                    f"Entreprise : {company}\n"
                    f"Type de Contrat : {contract_type}\n"
                    f"Localisation : {region}\n\n"
                    f"Résumé de l'offre :\n{description_text}"
                )

                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category=category,
                    source=source,
                    date_start=date_start,
                    date_end=date_end,
                    url=job_url,
                    badge_color=badge_color,
                    description=full_description
                ))

            except Exception as e:
                print(f"      ⚠️ Erreur lors du traitement d'une offre Emploi.ci : {e}")
                continue

    print(f"✅ Emploi.ci terminé : {len(items)} offres récupérées au total.")
    return items







@app.get("/scrape/emploi-ci")
def trigger_emploi_ci_scrape(pages: int = 1):
    print(f"🚀 Lancement manuel du scraper Emploi.ci ({pages} page(s))...")
    try:
        data = scrape_emploi_ci(max_pages=pages)
        
        count = 0
        for item in data:
            item_id = item.get("id") or item.get("opp_id")
            if not item_id:
                continue
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping Emploi.ci terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success",
            "added": count,
            "total_found": len(data),
            "data": data
        }
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping Emploi.ci : {e}")
        return {"status": "error", "message": str(e)}







def parse_un_date(date_text: str) -> str:
    months_fr = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
    }
    try:
        clean_text = date_text.lower().strip()
        match = re.search(r"(\d+)\s+([a-zéûâ]+)\s+(\d{4})", clean_text)
        if match:
            day = match.group(1).zfill(2)
            month = months_fr.get(match.group(2), "01")
            year = match.group(3)
            return f"{day}/{month}/{year}"
    except Exception:
        pass
    return datetime.today().strftime("%d/%m/%Y")


async def scrape_un_jobs():
    base_portal_url = "https://careers.un.org"
    # Remplace par l'URL exacte de ta recherche (ex: filtrée sur Abidjan)
    search_url = f"{base_portal_url}/lbw/Home.aspx" 
    items = []

    print("🔵 Démarrage du scraping UN Jobs avec Playwright...")

    async with async_playwright() as p:
        # Lancement du navigateur en mode sans interface (headless)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # Navigation vers la page
            await page.goto(search_url, timeout=30000, wait_until="networkidle")
            
            # ATTENTE CRUCIALE : On attend que le premier titre d'offre Angular apparaisse dans le DOM
            print("   ⏳ Attente du chargement des composants Angular...")
            await page.wait_for_selector("h2.jbOpen_title", timeout=15000)
            
            # Une fois chargé, on récupère le contenu HTML complet et généré
            html_content = await page.content()
        except Exception as e:
            print(f"   [ERREUR] Timeout ou aucun élément trouvé : {e}")
            await browser.close()
            return items

        await browser.close()

    # On donne le HTML fully-rendered à BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    cards = soup.select("div.card")
    
    print(f"   📄 {len(cards)} cartes potentielles trouvées dans le DOM généré.")

    for card in cards:
        title_tag = card.select_one("h2.jbOpen_title")
        if not title_tag:
            continue

        try:
            title = title_tag.get_text(strip=True)

            id_tag = card.select_one("span.jbOpen_Id")
            opp_id = ""
            if id_tag:
                id_match = re.search(r"\d+", id_tag.get_text())
                if id_match:
                    opp_id = id_match.group(0)

            link_tag = card.select_one("a[href*='jobSearchDescription']")
            job_url = ""
            if link_tag:
                href = link_tag.get("href", "")
                job_url = f"{base_portal_url}{href}" if href.startswith("/") else href

            if not job_url and opp_id:
                job_url = f"{base_portal_url}/jobSearchDescription/{opp_id}?language=fr"

            card_body = card.select_one(".card-body")
            body_text = card_body.get_text() if card_body else ""

            location = "Non spécifié"
            loc_match = re.search(r"Lieu d'affectation\s*:\s*([^:\n]+)", body_text)
            if loc_match:
                location = loc_match.group(1).replace("Date de publication", "").strip()

            department = "ONU"
            dept_match = re.search(r"Département/Bureau\s*:\s*([^:\n]+)", body_text)
            if dept_match:
                department = dept_match.group(1).replace("Date de publication", "").strip()
            
            family = "Général"
            family_match = re.search(r"Famille d'emplois\s*:\s*([^:\n]+)", body_text)
            if family_match:
                family = family_match.group(1).replace("Catégorie", "").strip()

            date_start = datetime.today().strftime("%d/%m/%Y")
            date_end = datetime.today().strftime("%d/%m/%Y")

            start_match = re.search(r"Date de publication\s*:\s*([^:\n]+)", body_text)
            if start_match:
                date_start = parse_un_date(start_match.group(1).replace("Date limite", ""))

            end_match = re.search(r"Date limite\s*:\s*([^:\n]+)", body_text)
            if end_match:
                date_end = parse_un_date(end_match.group(1))

            category = "Emplois"
            if "stage" in title.lower() or "internship" in title.lower():
                category = "Stages"
            
            badge_color = "blue" if category == "Emplois" else "orange"
            full_description = (
                f"Organisation : {department}\n"
                f"Famille d'emplois : {family}\n"
                f"Lieu d'affectation : {location}\n\n"
                f"Pour consulter les prérequis de ce poste, veuillez cliquer sur le bouton ci-dessous."
            )

            if not opp_id:
                continue

            items.append(build_opportunity(
                opp_id=f"un-{opp_id}",
                title=title,
                category=category,
                source="UN Jobs",
                date_start=date_start,
                date_end=date_end,
                url=job_url,
                badge_color=badge_color,
                description=full_description
            ))

        except Exception as e:
            print(f"      ⚠️ Erreur traitement offre : {e}")
            continue

    print(f"✅ UN Jobs terminé : {len(items)} offres récupérées.")
    return items


@app.get("/scrape/un-jobs")
async def trigger_un_jobs_scrape():
    print("🚀 Lancement manuel du scraper UN Jobs (Mode Asynchrone)...")
    try:
        # Ajout du await ici car la fonction est asynchrone désormais
        data = await scrape_un_jobs()
        
        count = 0
        for item in data:
            item_id = item.get("id") or item.get("opp_id")
            if not item_id:
                continue
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping UN Jobs terminé : {count} nouvelles offres ajoutées.")
        
        return {
            "status": "success",
            "added": count,
            "total_found": len(data),
            "data": data
        }
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping UN Jobs : {e}")
        return {"status": "error", "message": str(e)}



def scrape_orange_jobs(max_pages=3):
    # La vraie URL cachée
    url = "https://orange.jobs/widgets"
    items = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print("🔵 Démarrage du scraping Orange Jobs (via Widgets)...")

    for page in range(1, max_pages + 1):
        offset = (page - 1) * 10
        
        # Le payload standard pour Phenom ATS
        payload = {
            "lang": "fr_global",
            "deviceType": "desktop",
            "country": "global",
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "sortBy": "",
            "subsearch": "",
            "from": offset,
            "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "city", "state", "type"],
            "size": 10,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": "page1-search-results",
            "siteType": "external",
            "keywords": "",
            "global": True,
            "selected_fields": {}
        }
        
        print(f"   📄 Scraping de la page {page} (offres {offset} à {offset+10})...")
        
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.post(url, json=payload, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"      [ERREUR] Impossible d'accéder au widget Orange : {e}")
            break

        try:
            data = resp.json()
        except Exception:
            print("      ⚠️ Le serveur n'a pas renvoyé de JSON valide.")
            break

        # Extraction de la liste des offres dans la structure spécifique du widget
        jobs = []
        try:
            if "refineSearch" in data and "data" in data["refineSearch"]:
                jobs = data["refineSearch"]["data"].get("jobs", [])
            elif "data" in data and "jobs" in data["data"]:
                jobs = data["data"]["jobs"]
        except Exception:
            pass
            
        if not jobs:
            print(f"      ℹ️ Plus aucune offre trouvée. Fin de la recherche.")
            break

        for job in jobs:
            try:
                # 1. Titre, URL et Localisation
                title = str(job.get("title") or "Titre non spécifié")
                req_id = str(job.get("reqId") or job.get("jobSeqNo") or "")
                job_url = f"https://orange.jobs/fr/fr/job/{req_id}" if req_id else "https://orange.jobs/fr/fr/search-results"
                
                # On prend toutes les localisations sans filtrer
                location = str(job.get("location") or job.get("city") or job.get("country") or "Non spécifié")
                    
                # 2. Catégorie
                category = "Emplois"
                type_contrat = str(job.get("type") or job.get("contractType") or "Non spécifié")
                if "stage" in type_contrat.lower() or "intern" in type_contrat.lower():
                    category = "Stages"
                elif "alternance" in type_contrat.lower() or "apprentice" in type_contrat.lower():
                    category = "Formations"

                # 3. Logique de Dates
                # a. Date de début (par défaut : Aujourd'hui)
                date_start_obj = datetime.today()
                date_start = date_start_obj.strftime("%d/%m/%Y")
                
                posted_date = job.get("postedDate") or job.get("dateCreated")
                if posted_date:
                    try:
                        date_start_obj = datetime.strptime(str(posted_date)[:10], "%Y-%m-%d")
                        date_start = date_start_obj.strftime("%d/%m/%Y")
                    except Exception: 
                        pass

                # b. Date de fin (par défaut : Date de début + 30 jours)
                date_end = (date_start_obj + timedelta(days=30)).strftime("%d/%m/%Y")
                
                end_date_str = job.get("endDate")
                if end_date_str:
                    try:
                        date_end = datetime.strptime(str(end_date_str)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                    except Exception:
                        pass

                # 4. Description
                company = "Orange"
                desc_html = job.get("description", "")
                clean_desc = BeautifulSoup(str(desc_html), "html.parser").get_text(separator=" ", strip=True) if desc_html else ""
                
                full_description = f"Entreprise: {company}\nLieu: {location}\nType de contrat: {type_contrat}"
                if clean_desc:
                    full_description += f"\nDescription: {clean_desc[:250]}..."

                # 5. Création
                opp_id = str(generate_numeric_id(title, job_url))
                source_name = "Orange Jobs"

                try:
                    check_and_notify_new_source(source_name)
                except Exception:
                    pass

                opp = build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category=category,
                    source=source_name,
                    date_start=date_start,
                    date_end=date_end,
                    url=job_url,
                    badge_color="orange",
                    description=full_description
                )
                
                items.append(opp)
                
            except Exception as e:
                print(f"      ⚠️ Erreur sur une offre Orange : {e}")
                continue

    print(f"✅ Orange Jobs terminé : {len(items)} offres récupérées au total.")
    return items


@app.get("/scrape/orange")
def trigger_orange_scrape():
    print("🚀 Lancement manuel du scraper Orange Jobs...")
    try:
        # On va scraper les 3 premières pages (30 offres potentielles)
        data = scrape_orange_jobs(max_pages=3) 
        
        count = 0
        # Sauvegarde dans Firestore
        for item in data:
            item_id = item.get("id") or item.get("opp_id") 
            
            if not item_id:
                continue 
                
            doc_ref = db.collection("opportunities").document(str(item_id))
            
            # On vérifie les doublons
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping Orange terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success", 
            "added": count, 
            "total_found": len(data),
            "data": data
        }
        
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping Orange : {e}")
        return {"status": "error", "message": str(e)}












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

            source = "FORMATION EDUCARRIERE"

            # ✅ AJOUT ICI
            check_and_notify_new_source(source)

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


                source = "KAGGLE"

                # ✅ AJOUT ICI
                check_and_notify_new_source(source)

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


            source = "DEVPOST"

            # ✅ AJOUT ICI
            check_and_notify_new_source(source)

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





@app.get("/test-option-carriere")
def test_option_carriere_endpoint():
    """
    Route de test isolée pour Option Carrière.
    Retourne directement la liste des opportunités trouvées sans écrire dans Firebase.
    """
    print("🧪 [TEST] Lancement isolé du scraper Option Carrière...")
    try:
        results = scrape_option_carriere()
        
        return {
            "status": "Succès",
            "total_found": len(results),
            "data": results # Affiche les objets structurés pour vérification visuelle
        }
    except Exception as e:
        return {
            "status": "Erreur",
            "message": f"Le scraper a planté : {str(e)}"
        }






import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ---------- SCRAPING OPTION CARRIERE (Version Requête Directe) ----------
def scrape_option_carriere():
    url = "https://www.optioncarriere.ci/recherche/emplois?l=C%C3%B4te+d%27Ivoire&sort=date"
    items = []

    print("📡 Connexion directe à Option Carrière via HTTP Requests...")
    
    # 🕵️‍♂️ En-têtes complets imitant à 100% un vrai navigateur Firefox sous Windows
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr,fr-FR;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    try:
        # On effectue la requête directe
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Échec de la requête, Code HTTP : {response.status_code}")
            return items

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        # Sélectionne les articles d'offres d'après ton fichier HTML reçu
        jobs = soup.select("article.job")
        print(f"📊 Le scraper HTTP a trouvé {len(jobs)} offres.")

        if len(jobs) == 0:
            if "cloudflare" in html_content.lower():
                print("❌ [ÉCHEC] Bloqué par Cloudflare même en requête directe.")
            else:
                print("📝 Structure reçue (extrait) :", html_content[:400])

        for job in jobs:
            try:
                # 1. Titre et Lien
                title_tag = job.select_one("header h2 a") or job.select_one("header h3 a")
                if not title_tag: 
                    continue

                title = title_tag.get_text(strip=True)
                link = "https://www.optioncarriere.ci" + title_tag['href']

                # 2. Entreprise
                company_tag = job.select_one("p.company")
                company = company_tag.get_text(strip=True) if company_tag else "Entreprise confidentielle"

                # 3. Localisation
                loc_tag = job.select_one("ul.location li")
                location = loc_tag.get_text(strip=True) if loc_tag else "Abidjan"

                # 4. Description
                desc_tag = job.select_one("div.desc")
                description = desc_tag.get_text(strip=True) if desc_tag else f"Poste chez {company}"

                # 5. Date
                date_tag = job.select_one("footer span.badge")
                raw_date = date_tag.get_text(strip=True).lower() if date_tag else ""
                
                date_start_obj = datetime.today()
                
                if "heure" in raw_date:
                    pass 
                elif "hier" in raw_date:
                    date_start_obj = date_start_obj - timedelta(days=1)
                elif "jour" in raw_date:
                    try:
                        days_ago = int(re.search(r'\d+', raw_date).group())
                        date_start_obj = date_start_obj - timedelta(days=days_ago)
                    except: 
                        pass
                
                date_start = date_start_obj.strftime("%d/%m/%Y")
                date_end = (date_start_obj + timedelta(days=45)).strftime("%d/%m/%Y")

                opp_id = str(generate_numeric_id(title, company))
                source = "OPTION CARRIERE"

                check_and_notify_new_source(source)
                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category="Emplois",
                    source="Option Carrière",
                    date_start=date_start,
                    date_end=date_end,
                    url=link,
                    badge_color="orange",
                    description=f"{description}\n\n📍 {location}"
                ))

            except Exception as e_job:
                print(f"⚠️ Erreur parsing job: {e_job}")
                continue

    except Exception as e:
        print(f"❌ Erreur critique lors du scraping HTTP : {e}")

    return items




# ---------- SCRAPING PROJOB IVOIRE (Version Blindée) ----------
def scrape_projob_ivoire():
    base_url = "https://projobivoire.com/jobs/"
    items = []
    driver = None
    
    # Mapping des mois
    mois_map = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
    }

    def convert_date_fr(date_str):
        try:
            parts = date_str.lower().replace("-", "").strip().split()
            if len(parts) >= 3:
                day = parts[0].zfill(2)
                month = mois_map.get(parts[1], "01")
                year = parts[2]
                return f"{day}/{month}/{year}"
            return datetime.today().strftime("%d/%m/%Y")
        except:
            return datetime.today().strftime("%d/%m/%Y")

    try:
        print("🔄 Scraping ProJob Ivoire via Selenium (Mode Scroll)...")
        
        driver = get_driver()
        driver.get(base_url)

        # 1. ATTENTE INITIALE
        time.sleep(5)

        # 2. SCROLL POUR FORCER LE CHARGEMENT (Lazy Loading)
        # On scrolle un peu vers le bas pour activer les scripts d'affichage
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(3) # On attend que ça charge
        driver.execute_script("window.scrollTo(0, 1600);")
        time.sleep(3)

        # 3. DEBUG : On regarde l'URL actuelle (voir si on a été redirigé sur une pub)
        print(f"🔗 URL actuelle : {driver.current_url}")

        # 4. DEBUG : SAUVEGARDE DU HTML
        # C'est crucial : ouvre ce fichier pour voir si tu vois les offres ou une pub !
        with open("projob_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("📁 HTML sauvegardé sous 'projob_debug.html'.")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 5. SÉLECTEUR ÉLARGI
        # Au lieu de 'article.noo_job', on cherche juste la classe '.noo_job'
        # car parfois ils changent la balise HTML.
        articles = soup.select(".noo_job")
        
        print(f"📊 ProJob (Selenium): {len(articles)} offres trouvées.")

        for article in articles:
            try:
                # Titre (On cherche large: h2 ou h3)
                title_tag = article.select_one("h2 a") or article.select_one("h3 a")
                if not title_tag: 
                    # Parfois le lien est direct sur le titre sans h2
                    if article.name == 'a': 
                        title_tag = article
                    else:
                        continue
                
                title = title_tag.get_text(strip=True)
                link = title_tag['href']

                # Entreprise
                company_tag = article.select_one(".job-company")
                company = company_tag.get_text(strip=True) if company_tag else "Entreprise confidentielle"

                # Type
                type_tag = article.select_one(".job-type")
                job_type = type_tag.get_text(strip=True) if type_tag else "Emploi"

                # Localisation
                loc_tag = article.select_one(".job-location")
                location = loc_tag.get_text(strip=True) if loc_tag else "Abidjan"

                # Catégorie
                cat_tag = article.select_one(".job-category")
                category_raw = cat_tag.get_text(strip=True) if cat_tag else "Divers"
                category = "Stages" if "stage" in job_type.lower() else "Emplois"

                # Dates
                posted_tag = article.select_one(".job-date__posted")
                raw_start = posted_tag.get_text(strip=True) if posted_tag else ""
                date_start = convert_date_fr(raw_start)

                closing_tag = article.select_one(".job-date__closing")
                if closing_tag:
                    raw_end = closing_tag.get_text(strip=True)
                    date_end = convert_date_fr(raw_end)
                else:
                    start_dt = datetime.strptime(date_start, "%d/%m/%Y")
                    date_end = (start_dt + timedelta(days=30)).strftime("%d/%m/%Y")

                # Image
                img_tag = article.select_one("img")
                image_url = img_tag['src'] if img_tag else None

                opp_id = str(generate_numeric_id(title, company))


                source = "PROJOBIVOIRE"

                # ✅ AJOUT ICI
                check_and_notify_new_source(source)

                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=title,
                    category=category,
                    source="ProJob Ivoire",
                    date_start=date_start,
                    date_end=date_end,
                    url=link,
                    badge_color="green",
                    description=f"{job_type} - {category_raw}\nChez {company} à {location}",
                    image_url=image_url
                ))

            except Exception as e_art:
                # On met en commentaire pour ne pas polluer si c'est juste un element vide
                # print(f"⚠️ Erreur parsing article: {e_art}")
                continue

    except Exception as e:
        print(f"❌ Erreur Selenium ProJob: {e}")

    finally:
        if driver:
            driver.quit()
            print("✅ Driver ProJob fermé.")

    return items




# --- AJOUTE CECI POUR ÉVITER L'ERREUR ---
def send_notification_to_topic(topic, title, body):
    # Pour l'instant, on affiche juste un message au lieu d'envoyer la notif réelle
    print(f"🔔 [SIMULATION NOTIF] Vers {topic} : {title} - {body}")





def analyze_facebook_post_with_gemini(text, source_name):
    # ⚠️ TA CLÉ API
    GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=GOOGLE_API_KEY)

    prompt = f"""
    Analyse ce post Facebook de "{source_name}".
    Texte: "{text}"

    Tâche :
    1. Est-ce une offre concrète (emploi, stage, concours, formation, bourse, hackathon, financement) ?
    2. Si OUI, extrais les détails en JSON.
    3. Si NON, renvoie "is_valid": false.

    RÈGLE STRICTE : Renvoie UNIQUEMENT le JSON brut. Pas de Markdown (```json), pas de texte avant ni après.

    Format JSON :
    {{
        "is_valid": true,
        "title": "Titre",
        "category": "Stage",
        "date_end": "JJ/MM/AAAA" (ou null),
        "summary": "Résumé"
    }}
    """

    try:
        # On utilise le modèle 2.0 Flash qui est rapide et gratuit
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        if not response.parts:
            return {"is_valid": False}
        
        raw_text = response.text
        
        # --- NETTOYAGE CHIRURGICAL ---
        # 1. On cherche le premier '{' et le dernier '}'
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        
        if match:
            json_str = match.group() # On garde juste la partie JSON
            return json.loads(json_str)
        else:
            # Si on ne trouve pas de JSON, c'est que la réponse n'était pas valide
            return {"is_valid": False}

    except Exception as e:
        # Pour le debug, on affiche ce qui a planté si besoin
        print(f"⚠️ Erreur parsing Gemini : {e}")
        return {"is_valid": False}





# --- FONCTION D'ANALYSE GEMINI (Réseaux Sociaux : Facebook & LinkedIn) ---
def analyze_social_post_with_gemini(text_content, source_name, platform="Réseau/Plateforme"):
    # On force une petite pause AVANT de lancer la requête
    import time
    time.sleep(2)

    """
    Analyse un texte brut (Post Facebook ou Offre LinkedIn) pour en extraire 
    les infos qualifiées pour le Dashboard B2B.
    """
    
    # 1. Construction du Prompt "Hybride" + Data-Driven
    prompt = f"""
    Tu es un expert en recrutement. Analyse le texte suivant provenant de '{source_name}' sur la plateforme '{platform}'.
    Il peut s'agir d'un post informel ou d'une offre structurée.
    
    Texte à analyser : 
    "{text_content[:1500]}"

    Tâche :
    1. Détermine si c'est une RÉELLE opportunité (Offre d'emploi, Stage, Formation, Concours, Hackathon).
    2. Filtrage strict : Si c'est une publicité, des vœux, de la politique, un témoignage ou une info sans lien/moyen de postuler, REJETTE-LE.
    3. Si c'est valide, extrais les informations clés de manière concise.

    Format de réponse attendu (JSON STRICT uniquement, avec les clés exactes ci-dessous) :
    {{
        "is_valid": true,
        "title": "Titre court et clair du poste ou du concours",
        "category": "Emploi" | "Stage" | "Formation" | "Concours" | "Bourse",
        "date_end": "JJ/MM/AAAA" (ou null si non précisé),
        "summary": "Résumé en une phrase de l'opportunité.",
        "company_name": "Nom de l'entreprise. Si introuvable, mets 'Non spécifié'",
        "exact_location": "Ville précise (ex: Abidjan, Remote). Si introuvable, mets 'Non spécifié'",
        "required_skills": ["Compétence 1", "Compétence 2", "Compétence 3"] 
    }}

    Si l'opportunité est invalide, expirée ou qu'il s'agit d'un simple post de communication : 
    {{ "is_valid": false }}
    """

    # 2. Préparation de la requête
    headers = { "Content-Type": "application/json" }
    data = { "contents": [{ "parts": [{ "text": prompt }] }] }

    try:
        response = requests.post(GEMINI_API_URL, json=data, headers=headers, timeout=15)
        response.raise_for_status() 
        
        result = response.json()
        
        # Vérification si Gemini a renvoyé quelque chose
        if "candidates" not in result or not result["candidates"]:
            return {"is_valid": False}

        text_resp = result["candidates"][0]["content"]["parts"][0]["text"]
        
        # 3. Nettoyage "Chirurgical" du JSON
        match = re.search(r'\{.*\}', text_resp, re.DOTALL)
        if match:
            # On force le parsing JSON
            parsed_data = json.loads(match.group())
            
            # Sécurité : Si l'IA a oublié les nouveaux champs, on les ajoute par défaut
            if parsed_data.get("is_valid") == True:
                parsed_data.setdefault("company_name", "Non spécifié")
                parsed_data.setdefault("exact_location", "Non spécifié")
                parsed_data.setdefault("required_skills", [])
                
            return parsed_data
        else:
            return {"is_valid": False}

    except Exception as e:
        print(f"⚠️ Erreur analyse Gemini pour {platform} ({source_name}): {e}")
        return {"is_valid": False}


# --- 2. FONCTION DE SCRAPING FACEBOOK (inchangée, juste nettoyée) ---
def scrape_facebook_pages():
    # ⚠️ Ton Token Apify (Garde le tien)
    api_token = os.getenv("APIFY_API_TOKEN")
    
    start_urls = [
        {"url": "https://www.facebook.com/AgenceEmploiJeunes"},     
        {"url": "https://www.facebook.com/RMOJobCenter"},
        {"url": "https://www.facebook.com/EmpowerTalentsAndCareers"},
        {"url": "https://www.facebook.com/educarriere.ci"},
        {"url": "https://www.facebook.com/defense.ci"},
        {"url": "https://www.facebook.com/fonctionpublique.ci"},
    ]

    print("🔵 Démarrage du scraping Facebook via APIFY...")
    items = []
    
    try:
        client = ApifyClient(api_token)
        run_input = { "startUrls": start_urls, "resultsLimit": 3, "viewPortWidth": 1200 }

        # Lancement (peut prendre quelques secondes)
        run = client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
        
        dataset = client.dataset(run["defaultDatasetId"])
        items_list = list(dataset.iterate_items())
        print(f"   📦 {len(items_list)} posts FB récupérés.")

        for item in items_list:
            text_content = item.get("text") or item.get("postText") or item.get("content") or ""
            
            if not text_content or len(text_content) < 30: continue

            # Filtrage rapide avant d'appeler l'IA (économie de temps)
            keywords = ["recrutement", "concours", "appel", "candidature", "hackathon", "formation", "stage", "bourse", "avis"]
            if not any(k in text_content.lower() for k in keywords): continue 

            author_name = item.get("user", {}).get("name") or item.get("pageName", "Page Facebook")
            
            # Analyse IA
            analysis = analyze_social_post_with_gemini(text_content, author_name, "Facebook")

            if analysis.get("is_valid"):
                # ... Logique de création de l'opportunité (ton code existant) ...
                opp_id = str(generate_numeric_id(analysis["title"], analysis.get("date_end", "2025-12-31")))
                source_label = f"Facebook - {author_name}"
                
                # Image
                image_url = item.get("imageUrl")
                if not image_url and item.get("images"): image_url = item["images"][0]
                if not image_url: image_url = "https://upload.wikimedia.org/wikipedia/commons/5/51/Facebook_f_logo_%282019%29.svg"

                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=analysis["title"],
                    category=analysis["category"],
                    source=source_label,
                    date_start=datetime.now().strftime("%d/%m/%Y"),
                    date_end=analysis.get("date_end"),
                    url=item.get("url", item.get("postUrl", "")),
                    badge_color="blue",
                    description=analysis.get("summary", text_content[:100]),
                    isFeatured=True,
                    image_url=image_url
                ))
                print(f"      🎉 FB OCCASION: {analysis['title']}")
    
    except Exception as e:
        print(f"❌ Erreur Scraper Facebook : {e}")
    
    return items





# --- 3. FONCTION DE SCRAPING LINKEDIN JOBS ---
def scrape_linkedin_jobs():
    # ⚠️ Ton Token Apify (Garde le tien)
    api_token = os.getenv("APIFY_API_TOKEN")
    
    # 💡 L'ID de l'Actor Apify pour LinkedIn Jobs.
    ACTOR_ID = "curious_coder/linkedin-jobs-scraper" 

    print("🔵 Démarrage du scraping LinkedIn Jobs via APIFY...")
    items = []
    
    try:
        client = ApifyClient(api_token)
        
        # Le format exact exigé par curious_coder
        run_input = {
            "urls": [
                "https://www.linkedin.com/jobs/search/?keywords=recrutement%20OR%20concours%20OR%20stage&location=Cote%20d%27Ivoire"
            ],
            "count": 20,          
            "scrapeCompany": True 
        }

        # Lancement de l'Actor
        run = client.actor(ACTOR_ID).call(run_input=run_input)
        
        dataset = client.dataset(run["defaultDatasetId"])
        items_list = list(dataset.iterate_items())
        print(f"   📦 {len(items_list)} jobs LinkedIn récupérés.")

        for item in items_list:
            # 1. Récupération ultra-sécurisée des données brutes
            job_title = str(item.get("title") or "Poste sans titre")
            company = str(item.get("companyName") or "Entreprise Inconnue")
            location = str(item.get("location") or "Côte d'Ivoire")
            job_url = str(item.get("link") or "")
            
            raw_desc = item.get("descriptionText") or item.get("descriptionHtml") or ""
            description = str(raw_desc)
            
            if len(description) < 30: 
                continue

            # (J'ai retiré le filtre rapide par mots-clés, il est inutile ici : 
            # sur LinkedIn Jobs, ce sont déjà 100% des offres d'emploi)

            # 2. Analyse IA
            prompt_text = f"Titre: {job_title}\nEntreprise: {company}\nLieu: {location}\nDescription: {description}"
            analysis = analyze_social_post_with_gemini(prompt_text, company, "LinkedIn")

            # 👇 AJOUTE CETTE PAUSE ICI (Juste après l'appel à Gemini)
            import time
            time.sleep(4) # Attend 4 secondes pour respecter le quota Free Tier
            # --------------------------------------------------------
        
            if analysis and analysis.get("is_valid"):
                # 3. Construction de l'ID unique
                opp_id = str(generate_numeric_id(f"LI_{job_title}_{company}", "2026"))
                source_label = f"LinkedIn - {company}"
                
                # 4. Récupération du logo
                image_url = item.get("companyLogo")
                if not image_url: 
                    image_url = "https://upload.wikimedia.org/wikipedia/commons/c/ca/LinkedIn_logo_initials.png"

                # # 5. Création de l'opportunité (🟢 NOUVEAU : Sécurisation absolue des retours IA avec "or")
                # items.append(build_opportunity(
                #     opp_id=opp_id,
                #     title=analysis.get("title") or f"{job_title} chez {company}",
                #     category=analysis.get("category") or "Emplois / Stages",
                #     source=source_label,
                #     date_start=datetime.now().strftime("%d/%m/%Y"),
                #     date_end=analysis.get("date_end") or "À déterminer",
                #     url=job_url,
                #     badge_color="blue", 
                #     description=analysis.get("summary") or (description[:120] + "..."),
                #     image_url=image_url
                # ))
                # print(f"      🎉 LI OCCASION: {job_title} chez {company}")


                # 5. Gestion intelligente de la date de fin
                raw_date_end = analysis.get("date_end")
                
                # Si l'IA n'a rien trouvé de concret
                if not raw_date_end or raw_date_end in ["À déterminer", "null", "None", "Non spécifié"]:
                    # Calcul : Aujourd'hui + 30 jours
                    future_date = datetime.now() + timedelta(days=30)
                    final_date_end = future_date.strftime("%d/%m/%Y")
                else:
                    final_date_end = raw_date_end

                # 6. Création de l'opportunité
                items.append(build_opportunity(
                    opp_id=opp_id,
                    title=analysis.get("title") or f"{job_title} chez {company}",
                    category=analysis.get("category") or "Emplois / Stages",
                    source=source_label,
                    date_start=datetime.now().strftime("%d/%m/%Y"),
                    # On utilise notre date calculée ici 👇
                    date_end=final_date_end, 
                    url=job_url,
                    badge_color="blue", 
                    description=analysis.get("summary") or (description[:120] + "..."),
                    image_url=image_url
                ))
                print(f"       🎉 LI OCCASION: {job_title} chez {company} (Fin prévue: {final_date_end})")


    except Exception as e:
        print(f"❌ Erreur Scraper LinkedIn : {e}")
        traceback.print_exc() # 🟢 NOUVEAU : Va imprimer le chemin exact de l'erreur dans la console
    
    return items





@app.get("/clean-linkedin")
def force_clean_linkedin():
    """
    Route temporaire pour forcer la suppression des jobs LinkedIn de la base de données.
    À visiter depuis le navigateur : https://ton-url-render.com/clean-linkedin
    """
    print("🧹 Appel manuel du nettoyage LinkedIn...")
    deleted_count = 0
    try:
        # On récupère toutes les opportunités
        docs = db.collection("opportunities").stream()
        
        for doc in docs:
            data = doc.to_dict()
            source = data.get("source", "")
            
            # Si la source contient "LinkedIn", on supprime !
            if "LinkedIn" in str(source):
                doc.reference.delete()
                deleted_count += 1
                
        print(f"✅ Succès : {deleted_count} supprimés.")
        return {
            "status": "success", 
            "message": f"Nettoyage terminé ! {deleted_count} jobs LinkedIn ont été supprimés de la base de données."
        }
    except Exception as e:
        print(f"❌ Erreur lors du nettoyage : {e}")
        return {"status": "error", "message": f"Une erreur est survenue : {str(e)}"}


@app.get("/scrape/linkedin")
def trigger_linkedin_scrape():
    print("🚀 Lancement manuel du scraper LinkedIn...")
    try:
        # Appel de la fonction de scraping LinkedIn
        data = scrape_linkedin_jobs()
        
        count = 0
        # Sauvegarde en base de données (Firestore)
        for item in data:
            doc_ref = db.collection("opportunities").document(item["id"])
            
            # On vérifie si l'ID existe déjà pour ne pas créer de doublons
            if not doc_ref.get().exists:
                doc_ref.set(item)
                count += 1
                
        print(f"✅ Scraping LinkedIn terminé : {count} nouvelles opportunités ajoutées sur {len(data)} trouvées.")
        
        return {
            "status": "success", 
            "added": count, 
            "total_found": len(data),
            "data": data
        }
        
    except Exception as e:
        print(f"❌ Erreur lors du déclenchement du scraping LinkedIn : {e}")
        return {"status": "error", "message": str(e)}




# @app.get("/scrape/facebook")
# def trigger_facebook_scrape():
#     try:
#         data = scrape_facebook_pages()
#         # Sauvegarde en base de données
#         count = 0
#         for item in data:
#             doc_ref = db.collection("opportunities").document(item["id"])
#             if not doc_ref.get().exists:
#                 doc_ref.set(item)
#                 count += 1
#         return {"status": "success", "added": count, "data": data}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}







# @app.get("/scrape/cafop")
# def trigger_cafop_scrape():
#     try:
#         # 1. On lance le scraping spécifique au CAFOP
#         data = scrape_cafop()
        
#         # 2. Sauvegarde en base de données (Firebase Firestore)
#         count = 0
#         for item in data:
#             # On utilise l'ID unique généré dans scrape_cafop (ex: CAFOP_2026)
#             doc_ref = db.collection("opportunities").document(item["id"])
            
#             # Vérification anti-doublon : on n'écrit que si ça n'existe pas déjà
#             if not doc_ref.get().exists:
#                 doc_ref.set(item)
#                 count += 1
        
#         # 3. Retour du résultat à l'API
#         return {
#             "status": "success", 
#             "source": "CAFOP", 
#             "added": count, 
#             "total_found": len(data),
#             "data": data
#         }

#     except Exception as e:
#         # Gestion d'erreur globale
#         print(f"Erreur endpoint CAFOP : {e}")
#         return {"status": "error", "message": str(e)}




# ---------- SCRAPING ENS (ABLANIAN) ----------
def scrape_ens():
    # 💡 AJOUTE ICI TOUTES LES URLS DES CATÉGORIES ENS QUE TU VEUX SCRAPER
    urls_ens = [
        "https://ablanian.ci/concours_admin/view.php?slug=ens1",     # Exemple : Éducateurs
        "https://ablanian.ci/concours_admin/view.php?slug=ensplpc",   # Exemple : Prof de Lycée Physique-Chimie
        "https://ablanian.ci/concours_admin/view.php?slug=ensplsvt&src=footer",
        "https://ablanian.ci/concours_admin/view.php?slug=enspcsvt&src=footer",
        "https://ablanian.ci/concours_admin/view.php?slug=ensplpc&src=footer"
        # Ajoute les autres spécialités/slugs ici au besoin...
    ]
    
    items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://google.com"
    }

    for url in urls_ens:
        try:
            print(f"🔄 Connexion à {url}...")
            resp = requests.get(url, headers=headers, timeout=20, verify=False)
            
            if resp.status_code != 200:
                print(f"⚠️ Erreur HTTP sur {url} : {resp.status_code}")
                continue # 💡 On passe à l'URL suivante au lieu de planter tout le script

            soup = BeautifulSoup(resp.text, "html.parser")

            # 1. TITRE
            title_tag = soup.find("h1")
            title = title_tag.get_text(strip=True) if title_tag else "Concours ENS 2026"

            # 2. DATES (Regex ultra-blindée pour parer à toute éventualité HTML)
            page_text = soup.get_text(separator=" ", strip=True)
            date_start = "À venir"
            date_end = "À venir"
            status_description = "Lancement prochainement"
            badge_color = "gray"

            start_match = re.search(r"D[eé]but.{0,15}?(\d{2}[/-]\d{2}[/-]\d{4})", page_text, re.IGNORECASE)
            end_match = re.search(r"(?:Fin|Cl[ôo]ture).{0,15}?(\d{2}[/-]\d{2}[/-]\d{4})", page_text, re.IGNORECASE)
            
            if start_match and end_match:
                date_start = start_match.group(1).replace('-', '/')
                date_end = end_match.group(1).replace('-', '/')
                status_description = f"Inscriptions du {date_start} au {date_end}"
                badge_color = "green"
            elif start_match:
                date_start = start_match.group(1).replace('-', '/')
                status_description = f"Inscriptions ouvertes depuis le {date_start}"
                badge_color = "green"
            else:
                if "En cours" in page_text:
                    status_description = "Actuellement en cours (Dates à confirmer)"
                    badge_color = "orange"
                else:
                    status_description = "En attente de lancement officiel"

            # 3. DESCRIPTION DYNAMIQUE
            description = ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"].strip()
            
            if not description or len(description) < 20:
                categorie_match = re.search(r"Catégorie du concours\s*[:\.]?\s*(.*?)(?:Lancement|MAJ|👁|$)", page_text, re.IGNORECASE)
                condition_match = re.search(r"Condition[s]?\s*[:\.]?\s*(.*?)(?:\.|N\.B|Pour le diplôme|Date|$)", page_text, re.IGNORECASE)
                
                desc_parts = []
                if categorie_match:
                    desc_parts.append(f"Catégorie: {categorie_match.group(1).strip()}")
                if condition_match:
                    desc_parts.append(f"Conditions: {condition_match.group(1).strip()}")
                
                if desc_parts:
                    description = f"{title}. " + " | ".join(desc_parts) + f". {status_description}."
                else:
                    description = f"{title}. {status_description}. Retrouvez les conditions d'éligibilité sur la page."

            description = re.sub(r'\s+', ' ', description).strip()

            # 4. ID UNIQUE & SOURCE (On utilise le 'slug' de l'URL pour générer un ID différent par spécialité ENS)
            slug_match = re.search(r'slug=([^&]+)', url)
            slug = slug_match.group(1) if slug_match else "unknown"
            
            opp_id = str(generate_numeric_id(f"ENS_{slug}", "2026"))
            source_name = "ENS (Ablanian)"
            check_and_notify_new_source(source_name)

            # 5. CONSTRUCTION
            items.append(build_opportunity(
                opp_id=opp_id,
                title=title,
                category="Concours",
                source=source_name,
                date_start=date_start,
                date_end=date_end,
                url=url,
                badge_color=badge_color,
                description=description
            ))
            
            print(f"✅ Scraping réussi pour : {title}")
            
            # Petite pause pour ne pas surcharger le serveur Ablanian entre chaque page
            time.sleep(1)

        except Exception as e:
            print(f"❌ ERREUR SCRAPING ENS sur {url} : {e}")
            # On ne fait pas de fallback général ici, sinon ça fausserait les données s'il y a 10 URLs

    return items



@app.get("/scrape/ens")
def trigger_ens_scrape():
      try:
          # 1. On lance le scraping ENS
          data = scrape_ens()
        
          # 2. Sauvegarde en base de données
          count = 0
          for item in data:
              doc_ref = db.collection("opportunities").document(item["id"])
            
              # Vérification : on n'écrase pas si ça existe déjà (sauf si tu veux faire des mises à jour)
              # Pour l'ENS qui n'a pas de date, tu voudras peut-être enlever le "if not exists" plus tard
              # pour mettre à jour quand les dates sortiront.
              if not doc_ref.get().exists:
                  doc_ref.set(item)
                  count += 1
              else:
                  # Optionnel : Mise à jour si l'item existe déjà (utile quand les dates apparaissent)
                  doc_ref.update(item) 
        
          return {
              "status": "success", 
              "source": "ENS", 
              "added_or_updated": count, 
              "total_found": len(data),
              "data": data
          }

      except Exception as e:
          print(f"Erreur endpoint ENS : {e}")
          return {"status": "error", "message": str(e)}






# ---------- SCRAPING FACI (Recrutement Militaire) ----------
def scrape_faci():
    url = "https://ablanian.ci/concours_admin/view.php?slug=facirecrutement&src=footer"
    items = []

    try:
        # Headers pour simuler un navigateur
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://google.com"
        }
        
        print(f"🔄 Connexion à {url}...")
        resp = requests.get(url, headers=headers, timeout=20, verify=False)
        
        if resp.status_code != 200:
            print(f"⚠️ Erreur HTTP : {resp.status_code}")
            return [] # On retourne vide plutôt que de planter

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Extraction du TITRE
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else "Recrutement FACI 2026"

        # 2. Extraction des DATES (Regex ultra-blindée)
        page_text = soup.get_text(separator=" ", strip=True)
        date_start = "À venir"
        date_end = "À venir"
        badge_color = "gray"

        # 💡 EXPLICATION : 
        # D[eé]but -> Accepte "Début" ou "Debut"
        # .{0,15}? -> Accepte jusqu'à 15 caractères entre le mot et la date (gère les icônes 🟢, les espaces, les " : ")
        # (\d{2}[/-]\d{2}[/-]\d{4}) -> Capture la date avec des slashs ou des tirets
        start_match = re.search(r"D[eé]but.{0,15}?(\d{2}[/-]\d{2}[/-]\d{4})", page_text, re.IGNORECASE)
        end_match = re.search(r"(?:Fin|Cl[ôo]ture).{0,15}?(\d{2}[/-]\d{2}[/-]\d{4})", page_text, re.IGNORECASE)
        
        if start_match and end_match:
            date_start = start_match.group(1).replace('-', '/')
            date_end = end_match.group(1).replace('-', '/')
            badge_color = "green"
        elif start_match:
            date_start = start_match.group(1).replace('-', '/')
            badge_color = "green"
        else:
            # Fallback : format "Du 09 Février au..."
            pattern_du_au = re.search(r"Du\s+(\d{1,2}\s+[a-zA-Zéû]+\s+\d{4})\s+au\s+(\d{1,2}\s+[a-zA-Zéû]+\s+\d{4})", page_text, re.IGNORECASE)
            if pattern_du_au:
                date_start = pattern_du_au.group(1)
                date_end = pattern_du_au.group(2)
                badge_color = "green"

        # 3. Extraction de la DESCRIPTION (Conditions CLÉS : Armée)
        conditions_list = []
        
        # Âge
        age_match = re.search(r"Âge requis\s*[:\.]?\s*(.*?)(Nationalité|Diplôme|Condition|$)", page_text, re.IGNORECASE)
        if age_match:
            conditions_list.append(f"Âge: {age_match.group(1).strip()}")
            
        # Diplôme
        diploma_match = re.search(r"Diplôme[s]?.*?\s*[:\.]?\s*(.*?)(Condition|Autres|Taille|$)", page_text, re.IGNORECASE)
        if diploma_match:
            conditions_list.append(f"Diplôme: {diploma_match.group(1).strip()}")
        
        # Taille
        height_match = re.search(r"Taille minimale\s*[:\.]?\s*(\d+[,.]\d+\s*m?)", page_text, re.IGNORECASE)
        if height_match:
            conditions_list.append(f"Taille min: {height_match.group(1).strip()}")

        # Construction dynamique de la description
        if conditions_list:
            desc_text = " | ".join(conditions_list)
            if len(desc_text) > 150: 
                desc_text = desc_text[:147] + "..."
            description = f"{desc_text}. Inscriptions du {date_start} au {date_end}."
        else:
            description = f"Recrutement Militaire FACI. Inscriptions du {date_start} au {date_end}. Vérifiez la taille et l'âge requis sur le site officiel."

        description = re.sub(r'\s+', ' ', description).strip() # Nettoyage des espaces en trop

        # 4. ID & SOURCE
        opp_id = str(generate_numeric_id("FACI", "2026"))
        source_name = "FACI (Ablanian)"
        check_and_notify_new_source(source_name)

        # 5. CONSTRUCTION DE L'ITEM
        items.append(build_opportunity(
            opp_id=opp_id,
            title=title,
            category="Concours",
            source=source_name,
            date_start=date_start,
            date_end=date_end,
            url=url,
            badge_color=badge_color,
            description=description,
            isFeatured=True
        ))
        
        print(f"✅ Scraping FACI réussi ({date_start} - {date_end}).")

    except Exception as e:
        print(f"❌ ERREUR SCRAPING FACI : {e}")
        # FALLBACK de sécurité
        items.append(build_opportunity(
            opp_id="FACI_FALLBACK_2026",
            title="Recrutement FACI 2026",
            category="Concours",
            source="Ministère Défense",
            date_start="À venir", 
            date_end="À venir",
            url="https://defense.gouv.ci", 
            badge_color="red",
            description="Recrutement Militaire FACI 2026. Veuillez consulter le site du Ministère de la Défense pour les détails."
        ))

    return items




# @app.get("/scrape/faci")
# def trigger_faci_scrape():
#     try:
#         # 1. Scraping
#         data = scrape_faci()
        
#         # 2. Sauvegarde DB
#         count = 0
#         for item in data:
#             doc_ref = db.collection("opportunities").document(item["id"])
#             if not doc_ref.get().exists:
#                 doc_ref.set(item)
#                 count += 1
#             else:
#                 # Mise à jour si déjà existant (pour actualiser les dates si elles changent)
#                 doc_ref.update(item)
                
#         return {
#             "status": "success", 
#             "source": "FACI", 
#             "added_or_updated": count, 
#             "total_found": len(data), 
#             "data": data
#         }
#     except Exception as e:
#         return {"status": "error", 
# "message": str(e)}






# @app.get("/scrape-emails")
# async def scrape_unread_emails():
#     try:
#         # 🎯 LISTE BLANCHE : Mets ici les adresses e-mails ou les domaines de confiance
#         EXPEDITEURS_AUTORISES = [
#             "contact@giz.ci", 
#             "newsletter@educarriere.ci",
#             "info@emplois.ci",
#             "tutorat.tuteur@uvci.edu.ci",
#             "scolarite@uvci.edu.ci",
#             "stage.emploi@uvci.edu.ci",
#             "incubateur@uvci.edu.ci", 
#             "@giz.de" # Tu peux aussi n'autoriser qu'un domaine spécifique
#         ]

#         IMAP_SERVER = "imap.gmail.com"
#         mail = imaplib.IMAP4_SSL(IMAP_SERVER)
#         mail.login(EMAIL_USER, EMAIL_PASS)
        
#         mail.select("inbox")
        
#         status, messages = mail.search(None, '(UNSEEN)')
#         email_ids = messages[0].split()

#         if not email_ids:
#             return {"status": "ok", "message": "Aucun nouvel e-mail à traiter."}

#         opportunites_ajoutees = []
#         emails_ignores = 0

#         for e_id in email_ids:
#             res, msg_data = mail.fetch(e_id, '(RFC822)')
#             for response_part in msg_data:
#                 if isinstance(response_part, tuple):
#                     msg = email.message_from_bytes(response_part[1])
                    
#                     # 🛡️ FILTRE 1 : Vérification de l'expéditeur
#                     expediteur_brut = msg.get("From", "")
#                     nom_expediteur, email_expediteur = parseaddr(expediteur_brut)
#                     email_expediteur = email_expediteur.lower()

#                     # On vérifie si l'e-mail ou le domaine est dans notre liste blanche
#                     est_autorise = any(exp in email_expediteur for exp in EXPEDITEURS_AUTORISES)

#                     if not est_autorise:
#                         print(f"🚫 E-mail ignoré (Expéditeur non autorisé) : {email_expediteur}")
#                         emails_ignores += 1
#                         continue # On passe au mail suivant sans le lire !

#                     # Si autorisé, on lit le corps du mail
#                     body = ""
#                     if msg.is_multipart():
#                         for part in msg.walk():
#                             if part.get_content_type() == "text/plain":
#                                 body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
#                                 break
#                     else:
#                         body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

#                     if body:
#                         print(f"📩 Traitement de l'e-mail de {email_expediteur}...")
#                         donnees_extraites = extract_opportunity_from_email_with_gemini(body)
                        
#                         # 🛡️ FILTRE 2 : Validation par Gemini
#                         if donnees_extraites and donnees_extraites.get("est_opportunite") == True:
                            
#                             nouvelle_opp = {
#                                 "title": donnees_extraites.get("titre"),
#                                 "description": donnees_extraites.get("description"),
#                                 "category": donnees_extraites.get("categorie"),
#                                 "source": donnees_extraites.get("source"),
#                                 "link": donnees_extraites.get("lien_inscription"),
#                                 "date_end": donnees_extraites.get("date_limite"),
#                                 "createdAt": firestore.SERVER_TIMESTAMP,
#                                 "type": "scraped_email",
#                                 "imageUrl": choose_image(donnees_extraites.get("source"))
#                             }
                            
#                             update_time, opp_ref = db.collection("opportunities").add(nouvelle_opp)
#                             opportunites_ajoutees.append(donnees_extraites.get("titre"))
                            
#                             check_and_notify_new_source(nouvelle_opp["source"])
#                             send_opportunity_notification_to_all(
#                                 nouvelle_opp["title"], 
#                                 nouvelle_opp["source"], 
#                                 nouvelle_opp["category"], 
#                                 opp_ref.id
#                             )
#                         else:
#                             print("🤖 Gemini a rejeté ce mail (Ce n'est pas une opportunité valide).")

#         mail.close()
#         mail.logout()

#         return {
#             "status": "success", 
#             "ajouts": len(opportunites_ajoutees),
#             "opportunites_ajoutees": opportunites_ajoutees,
#             "emails_ignores_securite": emails_ignores
#         }

#     except Exception as e:
#         print(f"❌ Erreur lors du scraping des emails: {e}")
#         return JSONResponse({"status": "error", "message": str(e)}, status_code=500)






# 👈 AJOUTE CETTE LIGNE : Elle va chercher la clé secrète dans Render
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ChatMessage(BaseModel):
    message: str

@app.post("/chat")
async def chat_with_marabot(chat_req: ChatMessage):
    try:
        # 1. On récupère les opportunités depuis Firestore
        docs = db.collection('opportunities').get()
        opportunities = [doc.to_dict() for doc in docs]
        
        # 2. On prépare le contexte
        context = "Voici les opportunités actuelles dans la base de données :\n"
        for opp in opportunities:
            titre = opp.get('title', 'Sans titre')
            categorie = opp.get('category', 'Non classé')
            lien = opp.get('url', 'Pas de lien')
            context += f"- Titre: {titre} | Catégorie: {categorie} | Lien: {lien}\n"

        # 3. On initialise le modèle (plus besoin de remettre la clé ici)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 4. Le prompt...
        prompt = f"""Tu es Marabo, un assistant virtuel chaleureux et expert.
        ⚠️ ATTENTION : Ton nom s'écrit EXACTEMENT "Marabo". Tu n'es en aucun cas un "marabout". Ne te présente jamais comme un marabout. 
        Ton but est d'aider l'utilisateur à trouver l'opportunité idéale parmi celles disponibles.
        
        {context}
        
        Message de l'utilisateur : "{chat_req.message}"
        
        Instructions :
        - Réponds de manière naturelle, amicale et concise.
        - Si la demande de l'utilisateur correspond à des opportunités dans la liste ci-dessus, propose-les lui avec leurs liens.
        - S'il n'y a pas d'offre correspondante, dis-lui gentiment et suggère-lui de chercher autre chose.
        - Utilise des emojis pour rendre le texte agréable.
        """
        
        # 5. On génère la réponse
        response = model.generate_content(prompt)
        
        return {"reply": response.text}

    except Exception as e:
        return {"reply": f"Oups, j'ai eu un petit bug dans mon circuit IA : {str(e)}"}






# ---------- ROUTE SCRAP ----------
def run_all_scrapers():
    """Cette fonction va tourner en arrière-plan sans bloquer le serveur."""
    print("🚀 Début du scraping en arrière-plan...")
    
    scrapers = [
        scrape_agence_emploi_jeunes,
        scrape_rmo_jobcenter,
        scrape_emploi_ci,
        #scrape_linkedin_jobs,
        scrape_orange_jobs,
        scrape_faci,
        scrape_ens,
        scrape_cafop,
        scrape_facebook_pages,
        scrape_ena_directs,
        scrape_infas,
        scrape_minef_concours,
        #scrape_devpost_hackathons,
        scrape_novojob,
        scrape_daad_scholarship,
        scrape_educarriere,
        scrape_educarriere_formations,
        #scrape_kaggle_competitions,
        scrape_option_carriere,
        scrape_projob_ivoire,
        scrape_sociumjob,
    ]

    ops = []
    for scraper in scrapers:
        try:
            # On exécute le scraper et on ajoute les résultats à la liste globale
            result = scraper()
            if result:
                ops += result


                # 👇 AJOUTE UNE PAUSE ICI
            print(f"✅ Scraper terminé, pause de sécurité avant le suivant...")
            import time
            time.sleep(10) # 10 secondes de repos entre deux sites


        except Exception as e:
            # Si un scraper plante, on log l'erreur mais on continue avec les autres
            print(f"❌ Erreur dans {scraper.__name__ if hasattr(scraper, '__name__') else 'un scraper'}: {e}")
            continue

    added, updated = 0, 0
    for opp in ops:
        try:
            # On vérifie que le scraper a bien renvoyé un ID
            if not opp.get("id"):
                print(f"⚠️ Opportunité ignorée car pas d'ID : {opp.get('title', 'Sans titre')}")
                continue

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

                # 👇 C'EST EXACTEMENT ICI QU'ON MET À JOUR L'APPEL 👇
                try:
                    notify_users_by_interest(
                        opportunity_id=str(opp["id"]), 
                        opportunity_title=opp.get("title", "Nouvelle opportunité"), 
                        category=opp.get("category", "Général"),
                        source=opp.get("source", ""),       # 👈 AJOUT DE LA SOURCE POUR L'EXCEPTION KAGGLE
                        date_end=opp.get("date_end", None)  # 👈 AJOUT DE LA DATE DE FIN POUR LE FILTRE D'EXPIRATION
                    )
                except Exception as notif_error:
                    print(f"⚠️ Erreur lors de l'envoi des notifs ciblées pour {opp['id']}: {notif_error}")
                # 👆 FIN DE L'AJOUT 👆

        except Exception as e:
            print(f"⚠️ Firestore error for opp {opp.get('id', 'inconnu')}: {e}")
            continue

    # 🧹 --- NETTOYAGE DES OPPORTUNITÉS EXPIRÉES --- 🧹
    deleted_count = 0
    try:
        print("🧹 Lancement du nettoyage des opportunités expirées...")
        deleted_count = delete_expired_opportunities()
        print(f"✅ Nettoyage terminé : {deleted_count} opportunités supprimées.")
    except Exception as e:
        print(f"❌ Erreur lors de la suppression des opportunités expirées : {e}")

    print(f"🎉 Bilan final du scraping : {added} ajoutés, {updated} mis à jour, {deleted_count} supprimés sur {len(ops)} trouvés.")


# --- CONFIGURATION DU CRON (PLANIFICATEUR) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Démarrage du serveur et du planificateur de tâches...")

     # 👇 AJOUT TEMPORAIRE : On lance le nettoyage au démarrage
    #delete_all_linkedin_jobs_from_db()
    # 👆 Tu pourras retirer cette ligne lors de ton prochain déploiement
    
    scheduler = BackgroundScheduler()
    
    # 🔥 L'ASTUCE EST ICI : On planifie toutes les 12 heures, 
    # MAIS on utilise next_run_time pour lui dire "Fais le premier tour MAINTENANT, en arrière-plan"
    scheduler.add_job(
        run_all_scrapers, 
        'interval', 
        hours=12, 
        next_run_time=datetime.now()
    )
    
    scheduler.start()
    
    # On a SUPPRIMÉ l'appel direct à run_all_scrapers() ici !
    
    yield # FastAPI s'allume instantanément (Render est content et valide le déploiement !)
    
    # À l'arrêt du serveur
    print("Arrêt du planificateur...")
    scheduler.shutdown()






# --- FONCTION DE NETTOYAGE PHYSIQUE (VERSION FINALE) ---
def delete_expired_opportunities():
    print("🧹 Début du nettoyage des opportunités expirées...")
    now = datetime.utcnow().date()
    deleted = 0
    all_docs = db.collection("opportunities").stream()

    for doc in all_docs:
        data = doc.to_dict()
        try:
            # Priorité à date_end, sinon date_start
            date_str = data.get("date_end") or data.get("date_start")
            if not date_str:
                continue

            # Gestion du format de la date (Timestamp Firestore ou String)
            if isinstance(date_str, datetime):
                opp_date = date_str.date()
            else:
                formats_possibles = [
                    "%Y-%m-%d", "%d-%m-%Y", 
                    "%d/%m/%Y", "%Y/%m/%d"
                ]
                
                opp_date = None
                for fmt in formats_possibles:
                    try:
                        clean_date = str(date_str).strip()
                        opp_date = datetime.strptime(clean_date, fmt).date()
                        break
                    except ValueError:
                        continue
                
                if opp_date is None:
                    continue

            # Vérification et Suppression
            if opp_date < now:
                # 1. On supprime l'offre principale de Firestore
                doc.reference.delete()
                
                # 2. On supprime les notifications fantômes chez les utilisateurs
                try:
                    delete_notifications_for_opportunity(doc.id)
                except Exception as e:
                    print(f"⚠️ Erreur lors de la suppression des notifs pour {doc.id}: {e}")

                deleted += 1
                print(f"🗑️ Supprimé (Expiré): {data.get('title')} ({opp_date})")

        except Exception as e:
            print(f"❌ Erreur sur le document {doc.id}: {e}")
            continue

    # Bilan final dans les logs Render
    if deleted > 0:
        print(f"✨ Nettoyage terminé : {deleted} opportunités (et leurs notifications) supprimées.")
    else:
        print("✨ Nettoyage terminé : Rien à supprimer, la base est propre.")
        
    return deleted


def delete_devpost_and_kaggle_from_db():
    print("🧹 [PURGE] Recherche et suppression des opportunités Devpost et Kaggle...")
    deleted_count = 0
    
    try:
        # Récupération de tous les documents de la collection
        all_docs = db.collection("opportunities").stream()
        
        for doc in all_docs:
            data = doc.to_dict()
            # On passe tout en minuscules pour éviter les pièges d'orthographe
            source_field = str(data.get("source", "")).strip().lower()
            
            # Cible large : capture "Kaggle", "KAGGLE", "Devpost", "devpost", etc.
            if "kaggle" in source_field or "devpost" in source_field:
                print(f"🗑️ [PURGE] Suppression détectée : {data.get('title', 'Sans titre')} (Source en BD: {data.get('source')})")
                
                # 1. Suppression du document principal
                doc.reference.delete()
                
                # 2. Nettoyage des notifications fantômes liées à cet ID
                try:
                    delete_notifications_for_opportunity(doc.id)
                except Exception as e_notif:
                    print(f"⚠️ Erreur nettoyage notif pour {doc.id}: {e_notif}")
                    
                deleted_count += 1
                
        print(f"✨ [PURGE] Opération terminée. {deleted_count} documents supprimés au total.")
    except Exception as e:
        print(f"❌ Erreur critique lors de la purge : {e}")
        
    return deleted_count



# --- CONFIGURATION DU LIFESPAN FINAL ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Démarrage du serveur et du planificateur...")
    
    # On s'assure d'utiliser le bon format de date pour le scheduler
    now = datetime.now()
    
    scheduler = BackgroundScheduler()
    
    # 1. SCRAPING : Toutes les 12 heures
    scheduler.add_job(
        run_all_scrapers, 
        'interval', 
        hours=12, 
        next_run_time=now
    )
    
    # 2. NOTIFICATIONS : Toutes les 2 minutes
    scheduler.add_job(
        notify_new_opportunities, 
        'interval', 
        minutes=2,
        next_run_time=now
    )
    
    # 3. NETTOYAGE : Toutes les 24 heures
    scheduler.add_job(
        delete_expired_opportunities, 
        'interval', 
        hours=24,
        next_run_time=now
    )

    scheduler.start()
    
    yield # Le serveur est "UP" pour Render
    
    print("🛑 Arrêt du planificateur...")
    scheduler.shutdown()




# @app.get("/purge-sources")
# def purge_sources_endpoint(background_tasks: BackgroundTasks):
#     """
#     Route de secours pour nettoyer Devpost et Kaggle en arrière-plan instantanément
#     sans toucher aux scrapers.
#     """
#     # Exécute la purge de façon isolée dans les tâches de fond de FastAPI
#     background_tasks.add_task(delete_devpost_and_kaggle_from_db)
    
#     return {
#         "status": "Succès",
#         "message": "La purge de Devpost et Kaggle a été lancée de manière isolée en arrière-plan !",
#         "action": "Veuillez surveiller les logs Render pour confirmer le nombre d'éléments supprimés."
#     }



@app.get("/scrape")
def scrape_opportunities_endpoint(background_tasks: BackgroundTasks):
    """
    Cette route répond immédiatement au client et lance le travail lourd en tâche de fond.
    """
    # Ajoute la fonction de scraping à la file d'attente
    background_tasks.add_task(run_all_scrapers)
    
    # Répond tout de suite sans faire attendre
    return {
        "message": "Le scraping a été lancé avec succès en arrière-plan !",
        "info": "Consultez les logs du serveur pour voir l'avancement et le bilan final."
    }




@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"status": "Marabot est réveillé et en pleine forme !"}
