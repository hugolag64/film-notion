import requests
import os
import json

# Hardcoded for debug/test or load from env
# We will read from .env manually to be sure
def load_env_vars():
    env_vars = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    except Exception:
        pass
    return env_vars

env = load_env_vars()
TOKEN = env.get("NOTION_TOKEN")
DB_ID = env.get("DATABASE_ID")

def test_notion_raw():
    print(f"Testing Notion API with raw requests...")
    print(f"Database ID: {DB_ID}")
    # print(f"Token: {TOKEN[:4]}...{TOKEN[-4:]}")

    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json={"page_size": 5})
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            print(f"Success! Found {len(results)} items.")
            # print(json.dumps(data, indent=2))
        else:
            print("Error response:")
            print(response.text)
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_notion_raw()
