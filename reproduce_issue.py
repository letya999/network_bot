#!/usr/bin/env python3
"""
Minimal reproducer for the exact issue in gemini_service.py
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.gemini_service import GeminiService
import asyncio
import tempfile
import uuid

async def test():
    print("=== Testing GeminiService ===\n")
    
    # Create test audio file
    temp_dir = tempfile.mkdtemp(prefix="voice_")
    random_filename = f"{uuid.uuid4()}.ogg"
    file_path = os.path.join(temp_dir, random_filename)
    
    # Write minimal OGG file
    with open(file_path, 'wb') as f:
        f.write(b'OggS')  # OGG header
        f.write(b'\x00' * 1000)  # Some padding
    
    print(f"✅ Created test file: {file_path}")
    print(f"   Size: {os.path.getsize(file_path)} bytes\n")
    
    # Test with GeminiService
    gemini = GeminiService()
    
    if not gemini.client:
        print("❌ GEMINI_API_KEY not set")
        return
    
    print("Calling extract_contact_data with audio file...")
    print("(Check logs for detailed information)\n")
    
    try:
        result = await gemini.extract_contact_data(audio_path=file_path)
        
        print("=== Result ===")
        print(f"Name: {result.get('name')}")
        print(f"Notes: {result.get('notes')}")
        print(f"Full result: {result}")
        
        if result.get('name') == 'Неизвестно':
            print("\n❌ Got 'Неизвестно' - check the logs above for the error!")
        else:
            print("\n✅ Success!")
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        print("\n✅ Cleaned up test files")

if __name__ == "__main__":
    asyncio.run(test())
