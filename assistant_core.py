"""
Shared core logic for the Family Assistant.

Used by both family_assistant.py (CLI) and sms_server.py (SMS bot).
"""

import json
import os
import base64
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable

import anthropic
from icalendar import Calendar

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "family_config.json"


# ── Config ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"No config found at {CONFIG_FILE}. See SETUP.md.")
    with open(CONFIG_FILE) as f:
        return json.load(f)


# ── Calendar (ICS) ─────────────────────────────────────────────────────────────

def fetch_ics(url: str) -> Optional[bytes]:
    """Download an ICS calendar file from a URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FamilyAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()
    except Exception:
        return None


def parse_events(ics_data: bytes, calendar_name: str, start: datetime.date, end: datetime.date) -> list[dict]:
    """Parse ICS data and return events in the given date range."""
    try:
        cal = Calendar.from_ical(ics_data)
    except Exception as e:
        return [{"error": f"Failed to parse calendar '{calendar_name}': {e}"}]

    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if not dtstart:
            continue

        ev_start = dtstart.dt
        ev_end = dtend.dt if dtend else ev_start

        # All-day events use date objects; timed events use datetime objects
        all_day = isinstance(ev_start, datetime.date) and not isinstance(ev_start, datetime.datetime)

        ev_start_date = ev_start if all_day else ev_start.date()
        ev_end_date = ev_end if all_day else ev_end.date()

        # All-day event DTEND is exclusive (next day), so subtract one day for comparison
        if all_day and dtend:
            ev_end_date = ev_end - datetime.timedelta(days=1)

        if ev_end_date < start or ev_start_date > end:
            continue

        summary = str(component.get("SUMMARY", "(No title)"))
        description = str(component.get("DESCRIPTION", ""))
        location = str(component.get("LOCATION", ""))

        if all_day:
            start_str = str(ev_start_date)
            end_str = str(ev_end_date)
        else:
            start_str = ev_start.strftime("%Y-%m-%d %H:%M")
            end_str = ev_end.strftime("%Y-%m-%d %H:%M") if dtend else start_str

        events.append({
            "title": summary,
            "start": start_str,
            "end": end_str,
            "all_day": all_day,
            "calendar": calendar_name,
            "location": location if location and location != "None" else "",
            "description": description[:200] if description and description != "None" else "",
        })

    events.sort(key=lambda e: e["start"])
    return events


# ── Tool implementations ───────────────────────────────────────────────────────

def tool_get_events(config: dict, start_date: str, end_date: str, member_name: Optional[str] = None) -> list:
    try:
        start = datetime.date.fromisoformat(start_date.split("T")[0])
        end = datetime.date.fromisoformat(end_date.split("T")[0])
    except ValueError as e:
        return [{"error": f"Invalid date format: {e}. Use YYYY-MM-DD."}]

    members = config.get("members", [])
    if member_name:
        members = [m for m in members if m["name"].lower() == member_name.lower()]
        if not members:
            return [{"error": f"No member named '{member_name}' found in config."}]

    all_events = []
    for member in members:
        raw = member.get("calendars") or []
        if not raw and member.get("ics_url", "").strip():
            raw = [{"label": "Personal", "ics_url": member["ics_url"]}]

        if not raw:
            all_events.append({"person": member["name"], "note": f"No calendars configured for {member['name']}."})
            continue

        for cal_entry in raw:
            ics_url = cal_entry.get("ics_url", "").strip()
            label = cal_entry.get("label", "Calendar")
            if not ics_url:
                continue
            cal_name = f"{member['name']} ({label})"

            ics_data = fetch_ics(ics_url)
            if ics_data is None:
                all_events.append({"calendar": cal_name, "error": f"Could not fetch '{label}' calendar for {member['name']}."})
                continue

            all_events.extend(parse_events(ics_data, cal_name, start, end))

    return all_events or [{"message": f"No events found from {start_date} to {end_date}."}]


def get_google_credentials(member_name: str):
    """Load Google OAuth credentials for a family member."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # Try env var first (Railway), then local file
        env_var = f"GOOGLE_TOKEN_{member_name.upper()}"
        token_data = os.environ.get(env_var)

        if token_data:
            creds_json = base64.b64decode(token_data).decode()
        else:
            token_file = BASE_DIR / "credentials" / f"token_{member_name.lower()}.json"
            if not token_file.exists():
                return None
            creds_json = token_file.read_text()

        creds = Credentials.from_authorized_user_info(json.loads(creds_json))

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token back
            token_file = BASE_DIR / "credentials" / f"token_{member_name.lower()}.json"
            if token_file.parent.exists():
                token_file.write_text(creds.to_json())

        return creds
    except Exception:
        return None


def tool_create_event(config: dict, member_name: str, title: str, start: str, end: str, description: str = "") -> dict:
    """Create a Google Calendar event for a family member."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {"error": "Google Calendar write support not installed. Run: pip3 install google-api-python-client"}

    creds = get_google_credentials(member_name)
    if not creds:
        return {"error": f"No Google Calendar write access for {member_name}. Run: python3 authorize.py --user {member_name}"}

    try:
        service = build("calendar", "v3", credentials=creds)

        # Find the member's primary calendar ID
        member = next((m for m in config.get("members", []) if m["name"].lower() == member_name.lower()), None)
        if not member:
            return {"error": f"No member named {member_name} in config."}

        # Use primary calendar (email address)
        cal_id = "primary"
        for cal in member.get("calendars", []):
            if cal.get("label", "").lower() == "personal":
                # Extract email from ICS URL
                ics = cal.get("ics_url", "")
                if "ical/" in ics:
                    cal_id = ics.split("ical/")[1].split("/")[0].replace("%40", "@")
                break

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": "America/New_York"},
            "end": {"dateTime": end, "timeZone": "America/New_York"},
        }

        result = service.events().insert(calendarId=cal_id, body=event).execute()
        return {"success": True, "event": title, "start": start, "end": end, "link": result.get("htmlLink", "")}

    except Exception as e:
        return {"error": f"Failed to create event: {e}"}


def tool_list_calendars(config: dict) -> list[dict]:
    result = []
    for m in config.get("members", []):
        cals = m.get("calendars") or []
        if not cals and m.get("ics_url", "").strip():
            cals = [{"label": "Personal"}]
        result.append({
            "name": m["name"],
            "role": m.get("role", ""),
            "calendars": [c.get("label", "Calendar") for c in cals],
            "configured": len(cals) > 0,
        })
    return result


# ── Tool definitions for Claude ────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_family_events",
        "description": (
            "Get calendar events for the family (or a specific member) for a date range. "
            "ALWAYS call this before answering any question about availability, scheduling, "
            "or potential rule conflicts. Do not guess — check the calendar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                "member_name": {"type": "string", "description": "Optional: specific family member's name"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "list_calendars",
        "description": "List which family members have calendars configured.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_event",
        "description": (
            "Create a new event on a family member's Google Calendar. "
            "Only use this after confirming the details with the user. "
            "Always confirm the date, time, and title before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "member_name": {"type": "string", "description": "Family member's name, e.g. Mark or Emily"},
                "title": {"type": "string", "description": "Event title"},
                "start": {"type": "string", "description": "Start time in ISO format, e.g. 2025-06-06T09:00:00"},
                "end": {"type": "string", "description": "End time in ISO format, e.g. 2025-06-06T11:00:00"},
                "description": {"type": "string", "description": "Optional event description"},
            },
            "required": ["member_name", "title", "start", "end"],
        },
    },
]


# ── System prompt ──────────────────────────────────────────────────────────────

def build_system_prompt(config: dict, current_user: Optional[str], sms_mode: bool = False) -> str:
    today = datetime.date.today()
    date_str = today.strftime("%A, %B %d, %Y")
    family_name = config.get("family_name", "My Family")

    members_lines = "\n".join(
        f"  - {m['name']} ({m.get('role', 'family member')})"
        + (f": {m['notes']}" if m.get("notes") else "")
        for m in config.get("members", [])
    ) or "  (No members configured)"

    rules_lines = "\n".join(
        f"  {i+1}. {rule}" for i, rule in enumerate(config.get("rules", []))
    ) or "  (No rules configured)"

    prefs = config.get("preferences", {})
    prefs_lines = "\n".join(f"  - {k.replace('_', ' ').title()}: {v}" for k, v in prefs.items()) or "  (No preferences set)"

    user_line = f"\nThe person asking right now is: **{current_user}**\n" if current_user else ""

    sms_note = "\n## SMS mode\nKeep responses concise — under 300 words. No bullet-heavy lists. Plain text only, no markdown.\n" if sms_mode else ""

    return f"""You are the family scheduling assistant for {family_name}. Today is {date_str}.
{user_line}{sms_note}
## Family Members
{members_lines}

## Family Rules — Advisory
These rules are guidelines, not hard blocks. When a request would break a rule:
1. Flag it clearly and briefly
2. Ask if they still want to proceed
3. Respect their answer — it's their family, not yours
{rules_lines}

## Family Preferences
{prefs_lines}

## How to answer scheduling questions
1. ALWAYS use get_family_events to check the actual calendar before answering
2. For multi-day trips, check the entire date range
3. Check all family members' calendars unless the question is clearly about one person
4. Flag rule conflicts warmly — don't lecture, just inform and ask
5. Be warm and direct
""".strip()


# ── Agentic loop ───────────────────────────────────────────────────────────────

def run_agentic_loop(
    client: anthropic.Anthropic,
    config: dict,
    messages: list[dict],
    system_prompt: str,
    on_tool_call: Optional[Callable] = None,
) -> tuple[str, list[dict]]:
    """
    Run Claude's agentic loop for one user turn.
    Returns (reply_text, updated_messages).
    Calls on_tool_call(tool_name) before each tool execution if provided.
    """
    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            messages.append({"role": "assistant", "content": response.content})
            return text, messages

        elif response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_tool_call:
                    on_tool_call(block.name)

                if block.name == "get_family_events":
                    result = tool_get_events(config, block.input["start_date"], block.input["end_date"], block.input.get("member_name"))
                elif block.name == "list_calendars":
                    result = tool_list_calendars(config)
                elif block.name == "create_event":
                    result = tool_create_event(
                        config,
                        block.input["member_name"],
                        block.input["title"],
                        block.input["start"],
                        block.input["end"],
                        block.input.get("description", ""),
                    )
                else:
                    result = {"error": f"Unknown tool: {block.name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

        else:
            text = next((b.text for b in response.content if b.type == "text"), "")
            messages.append({"role": "assistant", "content": response.content})
            return text, messages
