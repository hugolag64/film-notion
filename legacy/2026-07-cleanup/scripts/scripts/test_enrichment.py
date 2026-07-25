import asyncio
import sys
import os

# Ajout du dossier racine au path
sys.path.append(os.getcwd())

from backend.core.processor import EnrichmentProcessor

async def test_enrichment():
    print("Test du processeur d'enrichissement...")
    
    # Instance du processeur
    processor = EnrichmentProcessor()
    
    try:
        # Lancement du traitement
        # Attention: cela va VRAIMENT modifier Notion si des items correspondent aux critères
        # C'est ce qu'on veut pour tester "en vrai" avant de livrer
        updated, skipped = await processor.process_all()
        
        print(f"\n--- Résultat ---")
        print(f"Mis à jour : {updated}")
        print(f"Ignorés (Cache/Complet) : {skipped}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Fix encoding for Windows
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
    asyncio.run(test_enrichment())
