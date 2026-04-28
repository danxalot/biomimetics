import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models?key={key}')
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        models = json.loads(r.read().decode())['models']
        gemma3 = [m['name'].replace('models/', '') for m in models if 'gemma-3' in m['name']]
        print("Gemma 3 models:", gemma3)
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}")
