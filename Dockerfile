# 1. On part d'un système Linux léger avec Python 3.10
FROM python:3.10-slim

# 2. On empêche Python de créer des fichiers .pyc inutiles et on force l'affichage des prints
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. C'EST LA PARTIE MAGIQUE : On installe Google Chrome et ses dépendances
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. On crée un dossier /app dans le serveur et on s'y place
WORKDIR /app

# 5. On copie le fichier des librairies et on les installe
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. On copie tout le reste de ton code dans le serveur
COPY . .

# 7. On expose le port 8000 pour que l'API soit accessible
EXPOSE 8000

# 8. La commande finale pour démarrer FastAPI (assure-toi que ton fichier s'appelle bien main.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]