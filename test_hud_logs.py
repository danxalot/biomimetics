from playwright.sync_api import sync_playwright
import time

def handle_console(msg):
    print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", handle_console)
    print("Navigating to HUD...")
    try:
        page.goto("http://localhost:8090/console")
        print("Waiting for 10 seconds to collect logs...")
        time.sleep(10)
    except Exception as e:
        print(f"Error navigating: {e}")
    browser.close()
