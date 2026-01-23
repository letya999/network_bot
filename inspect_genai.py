
try:
    from google import genai
    print("Import successful")
    print(dir(genai))
    if hasattr(genai, 'Client'):
        client = genai.Client(api_key="test")
        print("Client attributes:", dir(client))
        if hasattr(client, 'aio'):
            print("Client.aio:", dir(client.aio))
        if hasattr(client, 'models'):
            print("Client.models:", dir(client.models))
except Exception as e:
    print(e)
