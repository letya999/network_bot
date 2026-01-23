#!/usr/bin/env python3
"""
Diagnostic script to check Gemini file upload flow
"""
import sys
import os

# Check if we're in the right environment
print("=== Environment Check ===")
print(f"Python: {sys.version}")
print(f"Working directory: {os.getcwd()}")

# Check if API key is set
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    print(f"✅ GEMINI_API_KEY is set ({len(api_key)} chars)")
else:
    print("❌ GEMINI_API_KEY is not set")
    sys.exit(1)

# Import google.genai
try:
    from google import genai
    print("✅ google.genai imported")
except ImportError as e:
    print(f"❌ Failed to import google.genai: {e}")
    sys.exit(1)

# Check version
if hasattr(genai, '__version__'):
    print(f"   Version: {genai.__version__}")

# Create client
try:
    client = genai.Client(api_key=api_key)
    print("✅ Client created")
except Exception as e:
    print(f"❌ Failed to create client: {e}")
    sys.exit(1)

# Check if files.upload exists and its signature
import inspect
if hasattr(client.files, 'upload'):
    sig = inspect.signature(client.files.upload)
    print(f"✅ client.files.upload exists")
    print(f"   Signature: {sig}")
    
    # Get parameter names
    params = list(sig.parameters.keys())
    print(f"   Parameters: {params}")
    
    # Check if 'file' or 'path' parameter exists
    if 'file' in params:
        print("   ✅ 'file' parameter found")
    elif 'path' in params:
        print("   ⚠️  'path' parameter found (old API?)")
    else:
        print(f"   ❓ Neither 'file' nor 'path' found. Params: {params}")
else:
    print("❌ client.files.upload does not exist")
    print(f"   Available methods: {dir(client.files)}")

print("\n=== All checks passed ===")
