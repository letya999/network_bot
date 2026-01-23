from google import genai
import inspect

try:
    client = genai.Client(api_key="test")
    print("Files methods:", dir(client.files))
    
    # Check upload signature
    if hasattr(client.files, 'upload'):
        print("\nUpload method signature:")
        print(inspect.signature(client.files.upload))
        
    # Check if there's documentation
    if hasattr(client.files.upload, '__doc__'):
        print("\nUpload method docstring:")
        print(client.files.upload.__doc__)
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
