#!/usr/bin/env python3
"""
Family Assistant — SMS bot via Twilio.

Twilio sends a POST to /sms when a family member texts the number.
The bot identifies the sender by phone number, runs the assistant,
and replies via TwiML.

Usage:
    python sms_server.py

Setup:
    See SETUP.md section 6 for Twilio account setup and ngrok instructions.

Environment variables (or .env file):
    ANTHROPIC_API_KEY   — your Anthropic key
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

from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient
import anthropic

from assistant_core import load_config, build_system_prompt, run_agentic_loop

# ── Setup ──────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
client = anthropic.Anthropic()
twilio_client = TwilioClient(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))
config = load_config()

INACTIVITY_TIMEOUT = 30 * 60  # 30 minutes — after this, conversation resets
MAX_SMS_CHARS = 1500           # Twilio handles multi-segment SMS fine up to this

# ── Conversation store ─────────────────────────────────────────────────────────
# { "+15551234567": {"messages": [...], "last_active": float} }

_store: dict = {}
_store_lock = threading.Lock()


def _normalize_phone(phone: str) -> str:
    """Strip everything except digits for comparison."""
    return "".join(c for c in phone if c.isdigit())


def lookup_member(phone: str) -> Optional[dict]:
    """Find the family member whose phone number matches."""
    normalized = _normalize_phone(phone)
    for member in config.get("members", []):
        if _normalize_phone(member.get("phone", "")) == normalized:
            return member
    return None


def get_session(phone: str) -> dict:
    """Return (or create) a conversation session, resetting if stale."""
    with _store_lock:
        now = time.time()
        session = _store.get(phone)
        if session and (now - session["last_active"]) > INACTIVITY_TIMEOUT:
            session = None
        if not session:
            _store[phone] = {"messages": [], "last_active": now}
        else:
            _store[phone]["last_active"] = now
        return _store[phone]


def get_cc_members(sender: dict) -> list:
    """Return other members with phones who should be CC'd."""
    sender_phone = _normalize_phone(sender.get("phone", ""))
    return [
        m for m in config.get("members", [])
        if m.get("phone") and _normalize_phone(m["phone"]) != sender_phone
    ]


def send_cc(sender_name: str, question: str, reply: str, cc_members: list):
    """Send a CC copy of the exchange to other family members."""
    from_number = config.get("twilio_number", os.environ.get("TWILIO_PHONE_NUMBER", ""))
    if not from_number:
        log.warning("No Twilio phone number configured for CC messages")
        return

    cc_text = f"📋 {sender_name} asked: \"{question}\"\n\n{reply}"
    cc_text = truncate(cc_text)

    for member in cc_members:
        try:
            twilio_client.messages.create(
                body=cc_text,
                from_=from_number,
                to=member["phone"],
            )
            log.info("CC sent to %s", member["name"])
        except Exception as e:
            log.error("Failed to CC %s: %s", member["name"], e)


def truncate(text: str) -> str:
    """Trim very long responses with a note to ask for more."""
    if len(text) <= MAX_SMS_CHARS:
        return text
    cutoff = text.rfind(" ", 0, MAX_SMS_CHARS - 60)
    return text[:cutoff] + "\n\n(Reply 'continue' for more.)"


# ── Twilio request validation ──────────────────────────────────────────────────

def validate_twilio(f):
    """Decorator: verify the request actually came from Twilio."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get("VALIDATE_TWILIO", "true").lower() == "false":
            return f(*args, **kwargs)
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        validator = RequestValidator(auth_token)
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

    # Identify sender
    member = lookup_member(from_number)
    if not member:
        log.warning("Unknown number: %s", from_number)
        resp.message(
            "Hi! I don't recognize this number. "
            "Ask a family admin to add your number to family_config.json."
        )
        return Response(str(resp), mimetype="text/xml")

    # Get conversation session
    session = get_session(from_number)
    messages = session["messages"]

    # Build system prompt for this user
    system_prompt = build_system_prompt(config, member["name"], sms_mode=True)

    # Add the user's message
    messages.append({"role": "user", "content": body})

    # Run the assistant
    try:
        reply, messages = run_agentic_loop(
            client,
            config,
            messages,
            system_prompt,
        )
        session["messages"] = messages
        session["last_active"] = time.time()
        log.info("Reply to %s (%s): %r", member["name"], from_number, reply[:80])
    except Exception as e:
        log.exception("Agentic loop failed for %s: %s", from_number, e)
        reply = "Sorry, something went wrong on my end. Please try again."

    final_reply = truncate(reply) if reply else "Sorry, I couldn't generate a response."
    resp.message(final_reply)

    # CC other members with phones
    cc_members = get_cc_members(member)
    if cc_members and reply:
        threading.Thread(
            target=send_cc,
            args=(member["name"], body, final_reply, cc_members),
            daemon=True,
        ).start()

    return Response(str(resp), mimetype="text/xml")


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return {"status": "ok", "family": config.get("family_name", "Family Assistant")}


# ── Background: clean up expired sessions ─────────────────────────────────────

def _cleanup_loop():
    while True:
        time.sleep(300)
        now = time.time()
        with _store_lock:
            expired = [p for p, s in _store.items() if (now - s["last_active"]) > INACTIVITY_TIMEOUT]
            for p in expired:
                del _store[p]
        if expired:
            log.info("Cleaned up %d expired session(s)", len(expired))

threading.Thread(target=_cleanup_loop, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("Starting SMS server on port %d", port)
    log.info("Family: %s", config.get("family_name"))
    log.info("Members with phones: %s", [m["name"] for m in config.get("members", []) if m.get("phone")])
    app.run(host="0.0.0.0", port=port, debug=False)
