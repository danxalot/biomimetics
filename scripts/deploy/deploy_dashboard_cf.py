#!/usr/bin/env python3
"""
Deploy the generated BiOS dashboard to Cloudflare (free tier) as a Worker.

Fetches the Cloudflare token at runtime via the shared creds client — no tokens
in code, self-discovers from the ~6 `cloudflare*` secrets. Serves the current
dashboard.html from a tiny Worker at <name>.<subdomain>.workers.dev.

Live-unverified until first run: it depends on the account having a workers.dev
subdomain enabled and a token with Workers Scripts:Edit. On failure it prints the
Cloudflare error so it can be corrected — it never breaks the pipeline (guarded
with || in the runner).
"""
import os
import sys
import json
import ssl
import urllib.request
import urllib.error
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = "/Users/danexall/Google Drive/My Drive/Obsidian-life/_generated/dashboard.html"
WORKER_NAME = "bios-dashboard"
CF_API = "https://api.cloudflare.com/client/v4"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


creds = _load("creds", "../lib/creds.py")


def _ssl_ctx():
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def _cf_get(path, token):
    req = urllib.request.Request(f"{CF_API}{path}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as resp:
        return json.loads(resp.read().decode())


def account_id(token):
    data = _cf_get("/accounts", token)
    results = data.get("result") or []
    return results[0]["id"] if results else None


def deploy():
    if not os.path.exists(DASHBOARD):
        print(f"❌ Dashboard not found at {DASHBOARD} — run generate_dashboard.py first")
        return 1

    token = creds.get_first("cloudflare", prefer=("worker", "edit", "api", "global"))
    if not token:
        print("❌ No cloudflare token found in the credentials server")
        return 1

    acct = account_id(token)
    if not acct:
        print("❌ Could not resolve a Cloudflare account for this token")
        return 1

    html = open(DASHBOARD, encoding="utf-8").read()
    worker_js = (
        "const HTML = " + json.dumps(html) + ";\n"
        "addEventListener('fetch', event => event.respondWith("
        "new Response(HTML, {headers: {'content-type': 'text/html;charset=utf-8'}})));\n"
    )

    url = f"{CF_API}/accounts/{acct}/workers/scripts/{WORKER_NAME}"
    req = urllib.request.Request(
        url, data=worker_js.encode("utf-8"), method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/javascript"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx()) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"❌ Cloudflare API error {e.code}: {e.read().decode()[:400]}")
        return 1

    if body.get("success"):
        print(f"✅ Dashboard deployed: https://{WORKER_NAME}.<your-subdomain>.workers.dev")
        return 0
    print(f"❌ Deploy failed: {json.dumps(body.get('errors', body))[:400]}")
    return 1


if __name__ == "__main__":
    sys.exit(deploy())
