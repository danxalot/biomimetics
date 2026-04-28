import urllib.request, json, ssl, urllib.error
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with open('/Users/danexall/Documents/VS Code Projects/ARCA/.secrets/google_ai_studio', 'r') as f:
    key = f.read().strip()

prompt="""You are an automated tagger. Analyze the following JSON array of text paragraphs.
For each paragraph, determine which of the following tags apply: [#bios/swarm, #context/legal, #bios/architecture, #bios/security]. If none apply, use an empty array.
You must output ONLY a valid JSON array of arrays containing the tags. Do not output markdown, codeblocks, or any conversational text.

Input:
["The autonomous agent Serena uses CoPaw.", "I bought apples.", "The backend requires Azure Key Vault."]

Output:"""

payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0.1}
}

req = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemma-3-1b-it:generateContent?key={key}', 
    headers={'Content-Type': 'application/json'}, 
    data=json.dumps(payload).encode()
)
try:
    with urllib.request.urlopen(req, context=ctx) as r:
        text = json.loads(r.read().decode())['candidates'][0]['content']['parts'][0]['text']
        print("Raw output:", text)
        print("Parsed JSON:", json.loads(text))
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()}")
