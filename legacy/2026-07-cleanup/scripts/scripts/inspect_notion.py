import os
import asyncio
from dotenv import load_dotenv
from notion_client import AsyncClient

# Charger les variables d'environnement
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

if not NOTION_TOKEN or not DATABASE_ID:
    print("Erreur : NOTION_TOKEN ou DATABASE_ID manquant dans le fichier .env")
    exit(1)

async def inspect_database():
    notion = AsyncClient(auth=NOTION_TOKEN)
    
    print(f"Connexion à Notion avec la base ID : {DATABASE_ID}...")
    
    try:
        # Récupérer les informations de la base de données
        db_info = await notion.databases.retrieve(database_id=DATABASE_ID)
        print(f"\nNom de la base : {db_info.get('title', [{'plain_text': 'Sans titre'}])[0].get('plain_text', 'Sans titre')}")
        
        print("\n--- Propriétés (Colonnes) ---")
        properties = db_info.get("properties", {})
        for name, prop in properties.items():
            print(f"- {name} ({prop['type']})")
            
        # Récupérer une page exemple pour voir les données
        print("\n--- Exemple de données (1ère page) ---")
        query = await notion.databases.query(database_id=DATABASE_ID, page_size=1)
        results = query.get("results", [])
        
        if results:
            page = results[0]
            props = page.get("properties", {})
            for name, prop_data in props.items():
                prop_type = prop_data["type"]
                content = prop_data.get(prop_type)
                # Simplification de l'affichage pour certains types
                if prop_type == "title":
                    content = content[0]["plain_text"] if content else ""
                elif prop_type == "rich_text":
                    content = content[0]["plain_text"] if content else ""
                elif prop_type == "select":
                    content = content["name"] if content else None
                elif prop_type == "multi_select":
                    content = [item["name"] for item in content]
                
                # Force safe printing
                safe_name = name.encode('utf-8', errors='replace').decode('utf-8')
                safe_content = str(content).encode('utf-8', errors='replace').decode('utf-8')
                print(f"  {safe_name}: {safe_content}")
                
                # Debug specific types if needed
                if prop_type not in ['title', 'rich_text', 'select', 'multi_select', 'date', 'checkbox', 'created_time', 'url', 'number']:
                     print(f"  [DEBUG] Type unknown '{prop_type}' data: {prop_data}")

        else:
            print("Aucune page trouvée dans la base.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        await notion.aclose()

if __name__ == "__main__":
    # Fix for Windows console encoding
    import sys
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
    asyncio.run(inspect_database())
