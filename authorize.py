#!/usr/bin/env python3
"""
One-time Google Calendar OAuth authorization script.

Run this once for each person who needs write access to their calendar.
It opens a browser, you log in with their Google account, and saves a token.

Usage:
    python3 authorize.py --user Mark
    python3 authorize.py --user Emily
"""

import argparse
import json
import base64
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
CLIENT_SECRET = CREDENTIALS_DIR / "google_oauth.json"


def authorize(user: str):
    token_file = CREDENTIALS_DIR / f"token_{user.lower()}.json"

    print(f"\nAuthorizing Google Calendar for {user}...")
    print("A browser window will open — sign in with their Google account.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token locally
    token_file.write_text(creds.to_json())
    print(f"\n✅ Token saved to {token_file}")

    # Also print as base64 for Railway env var
    token_b64 = base64.b64encode(creds.to_json().encode()).decode()
    env_var = f"GOOGLE_TOKEN_{user.upper()}"
    print(f"\n── Add this to Railway environment variables ──")
    print(f"{env_var}={token_b64}")
    print(f"───────────────────────────────────────────────\n")
    print("Copy that line and add it as a variable in your Railway service.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="Family member name, e.g. Mark or Emily")
    args = parser.parse_args()
    authorize(args.user)
