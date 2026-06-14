#!/usr/bin/env python3
"""One-time GDrive OAuth re-authorization.

Why this exists
---------------
A service account cannot create files on a personal @gmail.com Drive
("Service Accounts do not have storage quota"), so writes MUST go through the
user's own OAuth identity. The previously-stored refresh_token is revoked
(invalid_grant) — Google revokes refresh tokens issued by a *Testing*-mode
OAuth consent screen roughly weekly. There is no code-only way to revive a
revoked refresh_token: you must re-consent.

PREREQUISITE (do this first, or the new token rots in 7 days too):
  Publish the OAuth consent screen to *Production*:
  https://console.cloud.google.com/auth/audience?project=757330161781
  ("Publish app" → confirm). Then run this script.

What it does
------------
1. Pulls the OAuth *client* id/secret from the Credentials Server (reusing the
   same desktop client already on the old token — no new GCP client needed).
2. Runs the standard InstalledAppFlow: opens a browser, you approve once.
3. Writes the resulting token JSON (incl. the fresh refresh_token) back to
   Azure Key Vault as `gdrive-oauth-token` via `az`, then rotates the
   Credentials Server cache so the new token is live immediately.

Run from the copaw venv:
  config_copaw/venv/bin/python3 scripts/copaw/reauth_gdrive_oauth.py
"""
import json
import subprocess
import sys
import urllib.request

CREDENTIALS_SERVER_URL = "http://localhost:8089"
CREDENTIALS_API_KEY_PATH = "/Users/danexall/biomimetics/secrets/credentials_api_key"
VAULT_NAME = "arca-mcp-kv-dae"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def _api_key() -> str:
    with open(CREDENTIALS_API_KEY_PATH) as f:
        return f.read().strip()


def _fetch_secret(name: str) -> str:
    req = urllib.request.Request(f"{CREDENTIALS_SERVER_URL}/secrets/{name}")
    req.add_header("X-API-Key", _api_key())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["value"]


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Reuse the existing desktop OAuth client from the (now-dead) token.
    old = json.loads(_fetch_secret("gdrive-oauth-token"))
    client_id = old.get("client_id")
    client_secret = old.get("client_secret")
    if not (client_id and client_secret):
        print("✖ No client_id/client_secret on existing gdrive-oauth-token; "
              "cannot reuse the desktop client.", file=sys.stderr)
        return 2

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("→ Opening browser for Google consent (approve the Drive scope)...")
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # access_type=offline + prompt=consent forces a *refresh_token* to be returned.
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent",
        authorization_prompt_message="Visit this URL to authorize BiOS GDrive access:\n{url}",
        success_message="✓ BiOS GDrive authorized. You can close this tab.",
    )

    if not creds.refresh_token:
        print("✖ No refresh_token returned. Make sure the consent screen is "
              "PUBLISHED and you fully re-consented (prompt=consent).", file=sys.stderr)
        return 3

    token_json = creds.to_json()

    print("→ Writing fresh token to Key Vault...")
    proc = subprocess.run(
        ["az", "keyvault", "secret", "set",
         "--vault-name", VAULT_NAME,
         "--name", "gdrive-oauth-token",
         "--value", token_json],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        print(f"✖ az keyvault set failed: {proc.stderr.strip()[:300]}", file=sys.stderr)
        return 4

    # Evict the cached (dead) token so the new one is served immediately.
    try:
        req = urllib.request.Request(
            f"{CREDENTIALS_SERVER_URL}/cache/rotate?name=gdrive-oauth-token",
            method="POST", headers={"X-API-Key": _api_key()})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  (warning) cache rotate failed: {e}", file=sys.stderr)

    print("✓ Done. gdrive-oauth-token refreshed in Key Vault with a fresh "
          "refresh_token. GDrive read+write now run through your user identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
