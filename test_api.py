import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

payload = {"contents": [{"parts": [{"text": "Say hello"}]}]}

req = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={key}', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps(payload).encode()
)
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        print("Success:", json.loads(r.read().decode()))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
    print("Response body:", e.read().decode())
except Exception as e:
    print(f"Other Error: {e}")
