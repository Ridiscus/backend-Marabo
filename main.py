import os
import json
import requests
from fastapi import FastAPI
from bs4 import BeautifulSoup
from firebase_admin import credentials, firestore, initialize_app
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

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

app = FastAPI()

# Exemple simple de scraping Google Jobs
def scrape_google_jobs():
    url = "https://www.google.com/search?q=jobs+in+abidjan&hl=en"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    jobs = []
    for div in soup.find_all("div", class_="BjJfJf"):
        title = div.get_text(strip=True)
        if title:
            jobs.append({"title": title})
    return jobs

@app.get("/scrape")
def scrape_opportunities():
    jobs = [
        {"title": "Développeur Python"},
        {"title": "Data Analyst"},
        {"title": "UX Designer"}
    ]
    
    for job in jobs:
        db.collection("opportunities").add(job)
    
    return {"message": f"{len(jobs)} opportunities added."}

@app.get("/")
def root():
    return {"message": "Opportunities backend is running!"}