import urllib.request, json, ssl, urllib.error, re
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

prompt = """You are a precise Zettelkasten tagging and linking agent.
Follow the Zettelkasten Rule: Aggressively identify and wrap core concepts, projects, and entities in double brackets [[ ]].
Return ONLY the paragraph with [[links]] and #tags applied. 

Input:
The autonomous agent Serena uses CoPaw to manage Notion tasks in our BiOS infrastructure.

Output:
"""

payload = {
    "model": "gemma-3-1b-it",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.1
}

req = urllib.request.Request(
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
    data=json.dumps(payload).encode()
)
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        text = json.loads(r.read().decode())['choices'][0]['message']['content'].strip()
        print("Success:", text)
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}")
