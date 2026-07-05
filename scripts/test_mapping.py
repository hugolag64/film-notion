import asyncio
import sys
import os

# Ajout du dossier racine au path pour les imports
sys.path.append(os.getcwd())

from backend.core.notion import NotionService

async def test():
    print("Test du service Notion...")
    try:
        medias = await NotionService.fetch_all_media()
        print(f"Récupéré {len(medias)} médias.")
        
        if medias:
            m = medias[0]
            print("\n--- Premier média ---")
            print(f"Titre: {m.title}")
            print(f"Réalisateur: {m.director}")
            print(f"Date: {m.release_date}")
            print(f"Statut: {m.status}")
            print(f"Note: {m.rating}")
            print(f"TMDB OK: {m.tmdb_ok}")
            print(f"Catégories: {m.categories}")
            print(f"Support: {m.support}")
            print(f"Raw model dump: {m.model_dump()}")
        else:
            print("Aucun média trouvé.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Fix encoding for Windows
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
    asyncio.run(test())
