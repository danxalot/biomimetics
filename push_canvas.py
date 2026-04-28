import urllib.request
import json

data = json.dumps({
    "session_id": "console:default",
    "type": "canvas_update",
    "text": "### BiOS HUD: Test View\n\nThis is a test from the script.",
    "sticky": True
}).encode('utf-8')

req = urllib.request.Request(
    'http://localhost:8090/console/push',
    data=data,
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as f:
        print("Success:", f.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
