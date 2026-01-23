import asyncio
import os
from google import genai
from google.genai import types

# Test file upload with new API
async def test_upload():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        return
    
    client = genai.Client(api_key=api_key)
    
    # Create a small test audio file
    test_file = "test_audio.ogg"
    with open(test_file, "wb") as f:
        # Write OGG header 'OggS'
        f.write(b'OggS')
        f.write(b'\x00' * 100)  # padding
    
    print(f"Created test file: {test_file}")
    
    try:
        # Test 1: Upload with file parameter
        print("\n=== Test 1: Upload file ===")
        uploaded_file = client.files.upload(file=test_file)
        print(f"✅ Upload successful!")
        print(f"   File name: {uploaded_file.name}")
        print(f"   File URI: {uploaded_file.uri if hasattr(uploaded_file, 'uri') else 'N/A'}")
        print(f"   File object: {uploaded_file}")
        
        # Test 2: Generate content with uploaded file
        print("\n=== Test 2: Generate content with audio ===")
        response = await client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=["Transcribe this audio", uploaded_file]
        )
        print(f"✅ API call successful!")
        print(f"   Response: {response.text[:200]}...")
        
        # Clean up
        print("\n=== Cleanup ===")
        client.files.delete(name=uploaded_file.name)
        print("✅ File deleted from Gemini")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Remove local test file
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"✅ Local test file removed")

if __name__ == "__main__":
    asyncio.run(test_upload())
