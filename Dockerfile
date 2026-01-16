# 1. On part d'une version légère de Python 3.11
FROM python:3.11-slim

# 2. Variables d'environnement pour que Python ne garde pas les logs en mémoire
ENV PYTHONUNBUFFERED=1

# 3. Installation des dépendances système et de Google Chrome
# Cette étape est CRUCIALE : elle télécharge Chrome et les outils nécessaires
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    ca-certificates \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. On définit le dossier de travail
WORKDIR /app

# 5. On copie le fichier requirements et on installe les librairies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. On copie tout ton code dans le conteneur
COPY . .

# 7. Commande de démarrage
# On écoute sur le port défini par l'hébergeur ($PORT) ou 8000 par défaut
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}