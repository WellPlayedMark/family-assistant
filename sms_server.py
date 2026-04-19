#!/usr/bin/env python3
"""
Family Assistant — SMS bot + Web UI via Flask.

Handles inbound SMS via Twilio webhook and serves a browser chat interface.

Environment variables (or .env file):
    ANTHROPIC_API_KEY   — Anthropic key
    TWILIO_ACCOUNT_SID  — from Twilio Console
    TWILIO_AUTH_TOKEN   — from Twilio Console
    VALIDATE_TWILIO     — set to "false" to skip signature validation (local dev only)
    PORT                — port to listen on (default: 5000)
"""

import os
import time
import threading
import logging
from functools import wraps
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from flask import Flask, request, Response, render_template, jsonify, session, redirect, url_for
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient
import anthropic

from assistant_core import load_config, build_system_prompt, run_agentic_loop, refresh_all_tokens
from conversation_store import save_message, load_recent_messages

# ── Setup ──────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
client = anthropic.Anthropic()
config = load_config()

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

INACTIVITY_TIMEOUT = 30 * 60  # 30 min inactivity resets in-memory session
MAX_SMS_CHARS = 1500

# ── Conversation store (in-memory + SQLite) ────────────────────────────────────
# In-memory store for within-session speed; SQLite for cross-session persistence.

_store: dict = {}
_store_lock = threading.Lock()


def _normalize_phone(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def lookup_member(phone: str) -> Optional[dict]:
    normalized = _normalize_phone(phone)
    for member in config.get("members", []):
        if _normalize_phone(member.get("phone", "")) == normalized:
            return member
    return None


def get_session(session_id: str) -> dict:
    """Return session dict, seeding from SQLite if it's a new/stale session."""
    with _store_lock:
        now = time.time()
        session = _store.get(session_id)
        if session and (now - session["last_active"]) > INACTIVITY_TIMEOUT:
            session = None
        if not session:
            # Seed from persistent memory
            prior = load_recent_messages(session_id, limit=10)
            _store[session_id] = {"messages": prior, "last_active": now}
        else:
            _store[session_id]["last_active"] = now
        return _store[session_id]


def truncate(text: str) -> str:
    if len(text) <= MAX_SMS_CHARS:
        return text
    cutoff = text.rfind(" ", 0, MAX_SMS_CHARS - 60)
    return text[:cutoff] + "\n\n(Reply 'more' for the rest.)"


def send_sms(to: str, body: str):
    """Send an outbound SMS via Twilio REST API."""
    from_number = config.get("twilio_number", "")
    if not from_number or not to:
        return
    try:
        twilio_client.messages.create(body=body, from_=from_number, to=to)
    except Exception as e:
        log.error("Failed to send SMS to %s: %s", to, e)


# ── Twilio request validation ──────────────────────────────────────────────────

def validate_twilio(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get("VALIDATE_TWILIO", "true").lower() == "false":
            return f(*args, **kwargs)
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(request.url, request.form, signature):
            log.warning("Failed Twilio signature validation from %s", request.remote_addr)
            return Response("Forbidden", status=403)
        return f(*args, **kwargs)
    return decorated


# ── SMS webhook ────────────────────────────────────────────────────────────────

@app.route("/sms", methods=["POST"])
@validate_twilio
def sms_webhook():
    from_number = request.form.get("From", "")
    body = request.form.get("Body", "").strip()

    log.info("SMS from %s: %r", from_number, body[:80])

    resp = MessagingResponse()

    member = lookup_member(from_number)
    if not member:
        log.warning("Unknown number: %s", from_number)
        resp.message("Hi! I don't recognize this number. Ask a family admin to add you to family_config.json.")
        return Response(str(resp), mimetype="text/xml")

    session = get_session(from_number)
    messages = session["messages"]
    system_prompt = build_system_prompt(config, member["name"], sms_mode=True)
    messages.append({"role": "user", "content": body})

    try:
        reply, messages = run_agentic_loop(client, config, messages, system_prompt)
        session["messages"] = messages
        session["last_active"] = time.time()

        # Persist to SQLite (text only — no tool-use blocks)
        save_message(from_number, "user", body)
        if reply:
            save_message(from_number, "assistant", reply)

        log.info("Reply to %s (%s): %r", member["name"], from_number, reply[:80])
    except Exception as e:
        log.exception("Agentic loop failed for %s: %s", from_number, e)
        reply = "Sorry, something went wrong. Please try again."

    resp.message(truncate(reply) if reply else "Sorry, I couldn't generate a response.")
    return Response(str(resp), mimetype="text/xml")


# ── Auth ───────────────────────────────────────────────────────────────────────

def require_pin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = ""
    if request.method == "POST":
        pin = request.form.get("pin", "").strip().lower()
        correct = config.get("web_pin", "").strip().lower()
        if pin == correct:
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("chat_page"))
        error = "Wrong PIN — try again."
    family_name = config.get("family_name", "The Family")
    return render_template("login.html", family_name=family_name, error=error)


# ── Web chat routes ────────────────────────────────────────────────────────────

@app.route("/consent")
def consent_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ROSIE — SMS Consent &amp; Privacy</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 680px; margin: 60px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.6; }
    h1 { color: #2c3e50; }
    h2 { color: #2c3e50; margin-top: 2em; font-size: 1.1em; }
    .badge { background: #2c3e50; color: white; padding: 4px 12px; border-radius: 20px; font-size: 13px; }
  </style>
</head>
<body>
  <h1>🤖 ROSIE — Family Scheduling Assistant</h1>
  <p><span class="badge">Private Family Tool</span></p>

  <h2>What is ROSIE?</h2>
  <p>ROSIE is a private AI scheduling assistant built for the Allenbach family. It helps coordinate calendars, sends daily schedule briefings, and alerts family members to scheduling conflicts.</p>

  <h2>Who receives SMS messages?</h2>
  <p>ROSIE sends text messages to exactly two recipients: <strong>Mark Allenbach</strong> and <strong>Emily Allenbach</strong>. Both individuals personally built and configured this system and have explicitly consented to receive messages from it. No other recipients exist. This is not a marketing service.</p>

  <h2>Message types</h2>
  <ul>
    <li>Daily schedule briefings (sent each morning)</li>
    <li>Scheduling conflict alerts</li>
    <li>Replies to inbound scheduling questions</li>
    <li>System status notifications</li>
  </ul>

  <h2>Consent</h2>
  <p>Both recipients are the owners and operators of this system. Consent was given verbally and confirmed by personally configuring the service, providing their own phone numbers, and setting up the messaging integration.</p>

  <h2>Opt-out</h2>
  <p>Recipients can reply <strong>STOP</strong> at any time to stop receiving messages.</p>

  <h2>Contact</h2>
  <p>For questions: <a href="mailto:mark@wellplayedllc.com">mark@wellplayedllc.com</a></p>
</body>
</html>"""


@app.route("/chat")
@require_pin
def chat_page():
    members = [m["name"] for m in config.get("members", [])]
    return render_template(
        "chat.html",
        members=members,
        family_name=config.get("family_name", "Family Assistant"),
    )


@app.route("/chat/send", methods=["POST"])
@require_pin
def chat_send():
    data = request.json or {}
    user_name = data.get("user", "").strip()
    message = data.get("message", "").strip()

    if not message or not user_name:
        return jsonify({"error": "Missing user or message"}), 400

    session_id = f"web:{user_name}"
    session = get_session(session_id)
    messages = session["messages"]
    system_prompt = build_system_prompt(config, user_name, sms_mode=False)
    messages.append({"role": "user", "content": message})

    try:
        reply, messages = run_agentic_loop(client, config, messages, system_prompt)
        session["messages"] = messages
        session["last_active"] = time.time()

        save_message(session_id, "user", message)
        if reply:
            save_message(session_id, "assistant", reply)
    except anthropic.OverloadedError:
        log.warning("Anthropic API overloaded for %s", user_name)
        return jsonify({"error": "ROSIE is a little overwhelmed right now — try again in a moment! 🤖"}), 503
    except anthropic.AuthenticationError:
        log.error("Anthropic API key invalid")
        return jsonify({"error": "ROSIE can't connect — API key issue. Ask Mark to check the settings."}), 500
    except Exception as e:
        log.exception("Web chat error for %s: %s", user_name, e)
        return jsonify({"error": "ROSIE hit a snag — please try again."}), 500

    return jsonify({"reply": reply or "Sorry, no response generated."})


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "family": config.get("family_name")})


# ── Background: clean up expired in-memory sessions ───────────────────────────

def _cleanup_loop():
    while True:
        time.sleep(300)
        now = time.time()
        with _store_lock:
            expired = [k for k, s in _store.items() if (now - s["last_active"]) > INACTIVITY_TIMEOUT]
            for k in expired:
                del _store[k]
        if expired:
            log.info("Cleaned up %d expired session(s)", len(expired))

threading.Thread(target=_cleanup_loop, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    # Refresh Google OAuth tokens at startup
    token_status = refresh_all_tokens(config)
    log.info("Token refresh: %s", token_status)
    for name in token_status.get("failed", []):
        log.warning("Token refresh FAILED for %s — calendar writes may not work", name)

    # Import and start scheduled jobs
    from scheduled_jobs import start_scheduler
    start_scheduler(config, client, send_sms)

    # Send startup health text to Mark
    mark = next((m for m in config.get("members", []) if m["name"] == "Mark"), None)
    if mark and mark.get("phone"):
        send_sms(mark["phone"], "ROSIE is back online ✅")

    log.info("Starting server on port %d — %s", port, config.get("family_name"))
    app.run(host="0.0.0.0", port=port, debug=False)
