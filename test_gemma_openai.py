import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {key}"
}
payload = {
    "model": "gemma-3-1b-it",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 10
}

req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode())
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        print("Success:", json.loads(r.read().decode()))
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}")
