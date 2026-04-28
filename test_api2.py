import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

payload = {
    "systemInstruction": {"parts": [{"text": "You are a valid bot"}]},
    "contents": [{"parts": [{"text": "Say hello"}]}],
    "generationConfig": {"temperature": 0.2}
}

req = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={key}', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps(payload).encode()
)
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        print("Success camelCase!")
except urllib.error.HTTPError as e:
    print(f"Error {e.code} with camelCase: {e.read().decode()}")

payload2 = {
    "system_instruction": {"parts": [{"text": "You are a valid bot"}]},
    "contents": [{"parts": [{"text": "Say hello"}]}],
    "generationConfig": {"temperature": 0.2}
}

req2 = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={key}', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps(payload2).encode()
)
try:
    with urllib.request.urlopen(req2, context=ctx) as r:
        print("Success snake_case!")
except urllib.error.HTTPError as e:
    print(f"Error {e.code} with snake_case: {e.read().decode()}")
