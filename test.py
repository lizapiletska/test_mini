from ollama import Client

client = Client()  # uses OLLAMA_HOST automatically

response = client.chat(
    model="mistral",
    messages=[{"role": "user", "content": "Hello via ngrok!"}]
)

print(response["message"]["content"])
