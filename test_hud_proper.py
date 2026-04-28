from playwright.sync_api import sync_playwright
import time
import urllib.request
import json
import threading

def push_event():
    print("Waiting 2s before pushing event...")
    time.sleep(2)
    data = json.dumps({
        "session_id": "console:default",
        "type": "canvas_update",
        "text": "### BiOS HUD: Test View\n\nThis is a test from the script.",
        "sticky": True
    }).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:8088/console/push',
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as f:
            print("Push Success:", f.read().decode('utf-8'))
    except Exception as e:
        print("Push Error:", e)

def handle_console(msg):
    print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}")

with sync_playwright() as p:
    print("Launching playwright...")
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", handle_console)
    print("Navigating to HUD...")
    try:
        page.goto("http://localhost:8088/")
        t = threading.Thread(target=push_event)
        t.start()
        print("Waiting for 10 seconds to collect logs...")
        time.sleep(10)
    except Exception as e:
        print(f"Error navigating: {e}")
    browser.close()
    print("Done collecting logs.")
