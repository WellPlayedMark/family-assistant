"""
Scheduled background jobs for the Family Assistant.

Jobs:
  - 6:00 AM ET: Conflict scan — check next 7 days for scheduling conflicts
  - 7:00 AM ET: Morning briefing — text parents today's family events
"""

import datetime
import logging
from typing import Callable, Optional

import anthropic
import pytz

from assistant_core import tool_get_events, tool_get_school_events

log = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_parent_phones(config: dict) -> list:
    """Return phone numbers for Mark and Emily."""
    return [
        m["phone"] for m in config.get("members", [])
        if m.get("phone") and m.get("role") in ("Dad", "Mom")
    ]


def format_time(time_str: str) -> str:
    """Convert '2026-04-05 09:00' to '9:00 AM'."""
    try:
        dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%-I:%M %p")
    except Exception:
        return time_str


# ── Morning briefing ───────────────────────────────────────────────────────────

def morning_briefing(config: dict, send_sms: Callable):
    """
    Fetch today's events for all family members and text parents a briefing.
    Runs at 7:00 AM ET.
    """
    today = datetime.date.today().isoformat()
    log.info("Running morning briefing for %s", today)

    try:
        events = tool_get_events(config, today, today)
        school_events = tool_get_school_events(today, today)
    except Exception as e:
        log.error("Morning briefing failed to fetch events: %s", e)
        return

    # Group family events by person
    by_person = {}
    for e in events:
        if "error" in e or "note" in e:
            continue
        cal = e.get("calendar", "")
        name = cal.split(" (")[0] if " (" in cal else cal
        by_person.setdefault(name, []).append(e)

    lines = [f"Good morning from ROSIE! Here's what's on the books today 🌅\n"]

    members = config.get("members", [])
    for member in members:
        name = member["name"]
        person_events = by_person.get(name, [])
        if person_events:
            event_strs = []
            for e in person_events:
                title = e.get("title", "")
                if e.get("all_day"):
                    event_strs.append(title)
                else:
                    event_strs.append(f"{title} {format_time(e.get('start', ''))}")
            lines.append(f"{name}: {', '.join(event_strs)}")
        else:
            lines.append(f"{name}: Free day")

    # Add school events
    school_today = [e for e in school_events if "error" not in e and "message" not in e]
    if school_today:
        school_titles = [e["title"] for e in school_today]
        lines.append(f"\n🏫 Westminster: {', '.join(school_titles[:3])}")

    message = "\n".join(lines)

    # Trim if too long
    if len(message) > 1500:
        message = message[:1450] + "\n..."

    phones = get_parent_phones(config)
    for phone in phones:
        send_sms(phone, message)
        log.info("Morning briefing sent to %s", phone)


# ── Conflict detection ─────────────────────────────────────────────────────────

def _parse_datetime(dt_str: str):
    """Parse event datetime string to datetime object."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def events_overlap(a: dict, b: dict) -> bool:
    """Check if two timed events overlap."""
    if a.get("all_day") or b.get("all_day"):
        return False
    a_start = _parse_datetime(a.get("start", ""))
    a_end = _parse_datetime(a.get("end", ""))
    b_start = _parse_datetime(b.get("start", ""))
    b_end = _parse_datetime(b.get("end", ""))
    if not all([a_start, a_end, b_start, b_end]):
        return False
    return a_start < b_end and b_start < a_end


def conflict_scan(config: dict, send_sms: Callable):
    """
    Scan the next 7 days for scheduling conflicts across all family members.
    Texts parents if any are found. Runs at 6:00 AM ET.
    """
    today = datetime.date.today()
    end = today + datetime.timedelta(days=7)
    log.info("Running conflict scan %s to %s", today, end)

    try:
        events = tool_get_events(config, today.isoformat(), end.isoformat())
    except Exception as e:
        log.error("Conflict scan failed: %s", e)
        return

    # Filter to timed events only (skip errors/notes)
    timed = [
        e for e in events
        if "title" in e and not e.get("all_day") and " " in e.get("start", "")
    ]

    conflicts = []

    # Check for overlapping events between different people
    for i, a in enumerate(timed):
        for b in timed[i+1:]:
            a_person = a.get("calendar", "").split(" (")[0]
            b_person = b.get("calendar", "").split(" (")[0]
            if a_person == b_person:
                continue  # same person, not a conflict
            if a.get("start", "")[:10] != b.get("start", "")[:10]:
                continue  # different days
            if events_overlap(a, b):
                conflicts.append(
                    f"⚠️ {a.get('start','')[:10]}: {a_person}'s '{a['title']}' "
                    f"overlaps with {b_person}'s '{b['title']}'"
                )

    # Check nighttime overbooking (>2 events starting at/after 5pm in any Mon-Sun week)
    nighttime = [
        e for e in timed
        if len(e.get("start", "")) >= 16 and e["start"][11:13] >= "17"
    ]
    by_week = {}
    for e in nighttime:
        try:
            d = datetime.date.fromisoformat(e["start"][:10])
            week_start = d - datetime.timedelta(days=d.weekday())
            by_week.setdefault(str(week_start), []).append(e)
        except Exception:
            pass
    for week, week_events in by_week.items():
        if len(week_events) > 2:
            titles = [f"{e['title']} ({e['start'][:10]})" for e in week_events]
            conflicts.append(
                f"📅 Week of {week}: {len(week_events)} evening events — "
                + ", ".join(titles)
            )

    if not conflicts:
        log.info("Conflict scan: no conflicts found")
        return

    message = "🚨 Family schedule heads-up:\n\n" + "\n".join(conflicts)
    if len(message) > 1500:
        message = message[:1450] + "\n..."

    phones = get_parent_phones(config)
    for phone in phones:
        send_sms(phone, message)
        log.info("Conflict alert sent to %s", phone)


# ── Scheduler setup ────────────────────────────────────────────────────────────

def start_scheduler(config: dict, ai_client: anthropic.Anthropic, send_sms: Callable):
    """Initialize and start APScheduler with all jobs."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("APScheduler not installed — scheduled jobs disabled. Run: pip3 install apscheduler pytz")
        return

    scheduler = BackgroundScheduler(timezone=ET)

    scheduler.add_job(
        lambda: conflict_scan(config, send_sms),
        CronTrigger(hour=6, minute=0, timezone=ET),
        id="conflict_scan",
        replace_existing=True,
    )

    scheduler.add_job(
        lambda: morning_briefing(config, send_sms),
        CronTrigger(hour=7, minute=0, timezone=ET),
        id="morning_briefing",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Scheduler started — conflict scan at 6am ET, briefing at 7am ET")
    return scheduler


