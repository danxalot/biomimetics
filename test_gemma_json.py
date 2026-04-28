import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

system="""You are a strict JSON tagging API. Given an array of paragraphs, return a JSON array where each element is an array of relevant tags from this list: [#bios/swarm, #context/legal, #bios/architecture]. If none apply, use an empty array. Do not output anything else except JSON."""

payload = {
    "systemInstruction": {"parts": [{"text": system}]},
    "contents": [{"parts": [{"text": '["The autonomous agent Serena uses CoPaw to manage Notion tasks.", "I bought some apples today.", "The backend pipeline requires Azure Key Vault credentials."]'}]}],
    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
}

req = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemma-3-1b-it:generateContent?key={key}', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps(payload).encode()
)
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        print("Success:", json.loads(r.read().decode())['candidates'][0]['content']['parts'][0]['text'])
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}")
