import asyncio
import sys
import os

sys.path.append(os.getcwd())

from backend.core.notion import NotionService

async def debug_notion():
    print("Starting debug...")
    try:
        await NotionService.fetch_all_media()
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    asyncio.run(debug_notion())
