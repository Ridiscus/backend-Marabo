# 1. On passe à Python 3.11-slim pour corriger l'alerte de version obsolète
FROM python:3.11-slim

# 2. On empêche Python de créer des fichiers .pyc et on force l'affichage des prints en temps réel
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. On crée le dossier de l'application
WORKDIR /app

# 4. CRUCIAL : On copie et on installe les packages Python D'ABORD.
# De cette façon, la commande 'playwright' devient disponible pour l'étape suivante.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. LA NOUVELLE PARTIE MAGIQUE : 
# On met à jour l'OS, puis Playwright installe Chromium ET toutes ses dépendances Linux (.so)
RUN apt-get update && \
    playwright install --with-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 6. On copie tout le reste de ton code dans le conteneur
COPY . .

# 7. Sur Render, le port par défaut pour les Web Services est le 10000
EXPOSE 10000

# 8. Commande finale pour démarrer Uvicorn sur le port 10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]