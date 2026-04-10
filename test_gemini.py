import google.generativeai as genai

# ⚠️ REMPLACE PAR TA CLÉ QUI COMMENCE PAR "AIza"
GOOGLE_API_KEY = "AIzaSyCzA4YhIjSkKqmPQdfnCNwbKNFjaNiHAV0"

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    print(f"✅ Clé configurée. Interrogation de Google...")
    
    # On demande la liste des modèles disponibles
    models = genai.list_models()
    found = False
    
    print("\n--- MODÈLES DISPONIBLES POUR TOI ---")
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            print(f"👉 {m.name}")
            found = True
            
    if not found:
        print("❌ Aucun modèle trouvé. Ta clé est peut-être invalide ou mal configurée.")
    else:
        print("\n✅ COPIE UN DES NOMS CI-DESSUS (ex: models/gemini-pro) DANS TON CODE.")

except Exception as e:
    print(f"\n❌ ERREUR CRITIQUE : {e}")
    if "400" in str(e) or "403" in str(e):
        print("💡 INDICE : Ta clé API est probablement invalide ou expirée.")