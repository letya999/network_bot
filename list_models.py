import asyncio
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

async def list_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)
    
    print("Listing available models...")
    try:
        # Pager object, iterate to get models
        pager = client.models.list() 
        
        print(f"{'Name':<40} | {'Display Name':<30}")
        print("-" * 75)
        
        count = 0
        for model in pager:
            print(f"{model.name:<40} | {getattr(model, 'display_name', 'N/A'):<30}")
            count += 1
                
        print(f"\nTotal models: {count}")
        
    except Exception as e:
        print(f"❌ Error listing models: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(list_models())
