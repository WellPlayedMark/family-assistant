# The Allenbach Family Assistant — Complete Guide

**Last updated: April 2026**

This document is your single source of truth for the family assistant. If something breaks in 6 months and you have no idea what you built, start here.

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [How to Use It — Day to Day](#2-how-to-use-it--day-to-day)
3. [Managing Family Rules](#3-managing-family-rules)
4. [Managing Calendars](#4-managing-calendars)
5. [Adding Write Access for a New Person](#5-adding-write-access-for-a-new-person)
6. [What to Do If Something Breaks](#6-what-to-do-if-something-breaks)
7. [Accounts and Credentials](#7-accounts-and-credentials)
8. [The Files Explained](#8-the-files-explained)
9. [How to Update and Redeploy](#9-how-to-update-and-redeploy)

---

## 1. What This Is

The Family Assistant is a text message bot that knows your family's schedules. You text it a scheduling question — "Is Thursday evening free?" or "Can Mark go on a business trip next week?" — and it reads everyone's Google Calendars, checks the family rules you've set, and texts back a real answer.

**In plain English, here's how the whole thing works:**

1. You text the family phone number: **+1 (855) 797-1691**
2. That number is owned by Twilio (a phone service company). Twilio immediately forwards the text to a small web server running in the cloud.
3. The server (hosted on Railway) figures out who you are based on your phone number.
4. It passes your question to Claude AI (made by Anthropic), which reads the family rules and everyone's calendar data.
5. Claude checks the actual calendars by fetching "ICS files" — basically a universal calendar export format that Google Calendar can share via a private link. No logins, no passwords, just a special secret URL.
6. Claude thinks it through, checks for rule conflicts, and writes a reply.
7. The reply gets sent back to Twilio, which texts it to your phone.

The whole thing usually takes 5–15 seconds.

**What it can do:**
- Check if a specific day or evening is free for one person or the whole family
- Look for schedule conflicts before committing to something
- Warn you when a request would break a family rule (too many evening events, business trip needs approval, etc.)
- Add events to your Google Calendar (for Mark and Emily, who have write access set up)
- Keep context for 30 minutes — you can have a back-and-forth conversation without repeating yourself

**What it can't do:**
- See calendars that aren't set up in `family_config.json`
- Add events to the kids' calendars (write access not set up for them)
- Send proactive reminders or alerts — it only responds when you text it

---

## 2. How to Use It — Day to Day

**The SMS number is: +1 (855) 797-1691**

Save it in your contacts as something like "Family Assistant" or "Allenbach Bot."

The assistant knows who you are by your phone number. Mark and Emily have their numbers registered. If you text from an unregistered number, it will tell you so.

> **Note on Twilio toll-free verification:** The number is a toll-free number that is currently pending carrier verification. During this process, some carriers may delay or filter messages. If texts seem to not be going through, this is likely why. Once verification completes (Twilio handles this automatically), it should work reliably on all carriers.

### Example questions you can send

**Checking availability:**
- "Is Friday evening free for the family?"
- "What does next week look like?"
- "Does anyone have anything on April 14th?"
- "What's on the calendar this weekend?"

**Before adding something:**
- "I want to plan a birthday dinner for Saturday at 7pm — any conflicts?"
- "Can Mark do a business trip to LA from Tuesday to Thursday?"
- "Emily wants to go out with friends Wednesday night — is that okay?"

**Checking specific people:**
- "What does Lily have this week?"
- "Is Mark free Tuesday morning?"
- "When is Madeline's next thing on her calendar?"

**Adding events (Mark and Emily only):**
- "Add a dentist appointment for Mark on April 10th at 2pm"
- "Put 'Date Night' on Emily's calendar for Saturday at 7pm"

### How the bot remembers context

The bot keeps your conversation going for 30 minutes of inactivity. So if you ask "What's Friday look like?" and then follow up with "What about Saturday?" — it knows you're still talking about scheduling. After 30 minutes of no texts, it forgets the conversation and starts fresh on your next message.

---

## 3. Managing Family Rules

The family rules live in `family_config.json` in the project folder on your Mac. The assistant reads these every time someone sends a message — so changes take effect immediately after you save the file and redeploy.

### What the current rules are

Here's what's set up right now, in plain English:

1. **Business Trips** — If Mark asks about a business trip, the assistant will remind him to get Emily's approval before confirming anything.

2. **Solo Evenings** — No solo evening activities on weeknights without checking with the other parent first. The bot will ask if you've cleared it.

3. **Nighttime Overbooking** — Any event starting at 5pm or later counts as a "nighttime event." If scheduling something would mean more than 2 evening events in a single week (Monday–Sunday), the bot will warn you and name the existing events.

4. **Tentative Events** — If a calendar event title ends with a question mark (like "Soccer Tournament?"), the bot treats it as tentative. If you ask about a day with a tentative event, it will flag that you should confirm it's actually free.

5. **Fieldwork Conflicts** — Mark has several Fieldwork calendars. When scheduling anything on a day with a Fieldwork event, the bot will ask if Mark is moderating that day.

### How to change a rule

The rules are plain sentences in `family_config.json`. To add, change, or remove one:

**Option A — Ask Claude Code to do it for you:**
Open a Claude Code session and say something like:
- "Add a rule that family dinners at 6:30pm on Sundays are protected and can't be overridden"
- "Remove the business trip approval rule"
- "Change the nighttime overbooking limit from 2 to 3 events per week"

**Option B — Edit the file yourself:**
Open `family_config.json` in any text editor. The rules section looks like this:

```json
"rules": [
  "RULE NAME: Description of what to check and what to say.",
  "ANOTHER RULE: Another description."
]
```

Each rule is a sentence in quotes, separated by commas. The format is flexible — just write clearly what the assistant should watch for and what it should say or do.

After editing, save the file, commit it to GitHub, and Railway will redeploy automatically (see Section 9).

### How to add a preference

Preferences are softer than rules — things like dinner time or family meeting day. They're also in `family_config.json`:

```json
"preferences": {
  "dinner_time": "6:30 PM",
  "family_meeting_day": "Sunday"
}
```

You can add any key/value pair here and the assistant will be aware of it.

---

## 4. Managing Calendars

### How calendars work

The assistant reads calendars using "ICS URLs" — a private, secret link that Google Calendar generates for each calendar. The link gives read-only access without requiring anyone to log in. Think of it like a secret RSS feed for your calendar.

These URLs are already configured for all five family members in `family_config.json`. You don't need to do anything unless a URL breaks or you want to add a new calendar.

### Current calendar setup

- **Mark** — Personal (Gmail), Work (WellPlayedLLC), plus four Fieldwork shared calendars
- **Emily** — Personal (Gmail), Work
- **Lily** — Main calendar
- **Madeline** — Main calendar
- **Sadie** — Main calendar

### How to get an ICS URL from Google Calendar

You'll need this if you're adding a new calendar or resetting one that broke.

**Important: This only works on desktop (Mac or PC), not on a phone.**

1. Open **calendar.google.com** in a browser
2. In the left sidebar, find the calendar you want. Hover over it and click the **three dots** (...)
3. Click **"Settings and sharing"**
4. Scroll all the way down to the section called **"Integrate calendar"**
5. Look for **"Secret address in iCal format"**
6. Click the copy icon — you'll get a URL that looks like:
   ```
   https://calendar.google.com/calendar/ical/someone%40gmail.com/private-abc123def456.../basic.ics
   ```
7. Paste that URL into `family_config.json` in the right spot

### Adding a new family member's calendar

In `family_config.json`, find the `members` array and add a new entry following the same pattern as the others:

```json
{
  "name": "NewPerson",
  "role": "Child",
  "phone": "",
  "calendars": [
    { "label": "Calendar", "ics_url": "paste-their-ics-url-here" }
  ],
  "notes": ""
}
```

If the person has a phone and should be able to text the bot, add their number in `"phone"` using the format `"+16465551234"`.

### What to do if a calendar stops working

If the bot says it can't read someone's calendar, the ICS URL may have been reset. This can happen if:
- Someone accidentally clicked "Reset" in Google Calendar settings
- Google rotated the URL for security reasons

**To fix it:**
1. Follow the steps above to get a fresh ICS URL for that person's calendar
2. Replace the old URL in `family_config.json`
3. Save, commit, push to GitHub — Railway redeploys and it's fixed

---

## 5. Adding Write Access for a New Person

Right now, Mark and Emily have write access — the bot can add events to their Google Calendars. The kids' calendars are read-only.

If you want to add write access for another family member (or re-authorize after a token expires), here's the process:

### Step 1: Run the authorization script

On your Mac, in the project folder:

```bash
python3 authorize.py --user Lily
```

Replace `Lily` with whoever you're authorizing.

A browser window will open. Sign in with **their** Google account. When it says "Authorization complete," go back to the terminal.

### Step 2: Copy the output to Railway

The script will print something like:

```
── Add this to Railway environment variables ──
GOOGLE_TOKEN_LILY=eyJhY2Nlc3NfdG9rZW4iOiJ...long string...
───────────────────────────────────────────────
```

Copy that entire `GOOGLE_TOKEN_LILY=...` line.

### Step 3: Add it to Railway

1. Go to **railway.app** and open the Allenbach Family project
2. Click on the service → **Variables** tab
3. Click **New Variable**
4. Paste the entire line — Railway will split it into key and value automatically
5. Click **Add** → the service will redeploy

That's it. The bot can now add events to that person's calendar.

---

## 6. What to Do If Something Breaks

### Step 1: Check if the server is running

Open this URL in any browser:

```
https://web-production-2d533.up.railway.app/health
```

You should see something like:
```json
{"status": "ok", "family": "The Allenbach Family"}
```

If the page doesn't load or shows an error, the server is down. Go check Railway (see below).

### Step 2: Check Railway logs

1. Go to **railway.app** — log in with the account that owns the project
2. Open the **Allenbach Family** project
3. Click on the service → click the **"Deployments"** tab
4. Click on the most recent deployment → scroll down to see logs
5. Look for red error messages

Common things you'll see in the logs and what they mean:

| Log message | What it means |
|---|---|
| `ANTHROPIC_API_KEY` not set | The Anthropic API key environment variable is missing or wrong |
| `Failed Twilio signature validation` | Twilio credentials may have changed, or someone is sending fake requests |
| `Could not fetch 'Personal' calendar for Mark` | Mark's ICS URL stopped working — get a new one |
| `No Google Calendar write access for Emily` | Emily's Google auth token expired — re-run `authorize.py` |
| `503` or `502` errors | Server crashed — look earlier in the logs for the actual error |

### Common issues and fixes

**The bot isn't responding to texts at all**
1. Check the health URL above — is the server up?
2. Check Railway logs for crashes
3. Make sure your Twilio webhook is still pointed at `https://web-production-2d533.up.railway.app/sms`
   - Go to Twilio Console → Phone Numbers → Active Numbers → click the number → check the webhook URL

**The bot says it can't read a calendar**
- That person's ICS URL has broken. Get a new one from Google Calendar settings and update `family_config.json`.

**The bot says it can't add an event (write access)**
- The Google OAuth token has expired. Re-run `python3 authorize.py --user Mark` (or Emily) and update the Railway environment variable.

**The Anthropic API key stopped working**
- Log in to console.anthropic.com, go to API Keys, and check if the key is still active. If it was deleted or expired, generate a new one and update the `ANTHROPIC_API_KEY` variable in Railway.

**Twilio toll-free number issues**
- The number (+1 855 797-1691) requires carrier verification for toll-free numbers. This is a one-time process Twilio manages. If texts are being filtered, log in to the Twilio Console and check the status under Phone Numbers → Regulatory Compliance.

**The bot is responding but with wrong information**
- The rules or calendar data in `family_config.json` may be out of date. Open the file and check that everything looks right.

### When in doubt: trigger a fresh deploy

In Railway, go to your service and click **"Deploy"** (or just make any small change to the repo and push — Railway auto-deploys). This restarts the server fresh and often fixes unexplained weirdness.

---

## 7. Accounts and Credentials

Here's every account this project depends on. If you need to find credentials or log in somewhere, this is your map.

### Anthropic (the AI)
- **What it is:** The company that makes Claude, the AI brain behind the assistant
- **Website:** console.anthropic.com
- **Used for:** The `ANTHROPIC_API_KEY` that lets the server call Claude
- **Where to find the key:** Anthropic Console → API Keys
- **Cost:** Pay-per-use. Each family text costs a few cents. Check usage at console.anthropic.com/usage

### Twilio (the phone number)
- **What it is:** The service that owns the SMS number and routes texts
- **Website:** console.twilio.com
- **Used for:** The phone number (+1 855 797-1691), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- **Where to find credentials:** Twilio Console → Account → API keys & tokens (or the dashboard home page)
- **Important settings:** Phone Numbers → Active Numbers → click the number → the webhook URL must be `https://web-production-2d533.up.railway.app/sms`

### Railway (the server hosting)
- **What it is:** The cloud platform where the SMS bot runs 24/7
- **Website:** railway.app
- **Used for:** Hosting the Python server, storing all environment variables (API keys, tokens)
- **Where to manage:** Log in → open the Allenbach Family project → click the service
- **Environment variables stored here:**
  - `ANTHROPIC_API_KEY`
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `VALIDATE_TWILIO` (set to `true`)
  - `GOOGLE_TOKEN_MARK` (base64-encoded OAuth token)
  - `GOOGLE_TOKEN_EMILY` (base64-encoded OAuth token)

### GitHub (the code)
- **What it is:** Where the code lives and version history is tracked
- **Website:** github.com/WellPlayedMark/family-assistant (private repo)
- **Used for:** Storing the code; Railway watches this repo and auto-deploys when you push changes
- **Important:** Do not commit `.env` or anything in the `credentials/` folder — those are gitignored for a reason

### Google (the calendars)
- **What it is:** Google Calendar, which everyone's schedules live in
- **Used for:** ICS URLs (read-only calendar access) and OAuth tokens (write access for Mark and Emily)
- **OAuth credentials file:** `credentials/google_oauth.json` — this is the Google Cloud app credential. Keep it safe and do not commit it.
- **Where it came from:** Google Cloud Console → a project set up during initial development

---

## 8. The Files Explained

Here's what every file in the project does, in plain English:

| File | What it does |
|---|---|
| `family_config.json` | **The brain of the setup.** Contains family members, their phone numbers, calendar URLs, all the rules, and preferences. Edit this to change how the assistant behaves. |
| `assistant_core.py` | The shared engine. Handles fetching calendars, parsing events, calling Claude, and running the conversation loop. Both the CLI and SMS bot use this. |
| `sms_server.py` | The SMS bot. Runs as a web server, listens for incoming texts from Twilio, figures out who's texting, and sends replies. This is what Railway runs. |
| `family_assistant.py` | A command-line version of the assistant. You can run this on your Mac to chat with the assistant directly without texting. Useful for testing. |
| `authorize.py` | The one-time setup script that grants write access to Google Calendar for a family member. Run it once per person; it opens a browser login. |
| `requirements.txt` | The list of Python libraries the project needs. Railway and your Mac use this to install dependencies. |
| `Procfile` | Tells Railway how to start the server. It just says `web: python3 sms_server.py`. |
| `.env` | Your local API keys and credentials. **Never commit this file.** It's ignored by git. |
| `.env.example` | A blank template showing what variables go in `.env`. Safe to commit. |
| `.gitignore` | Tells git which files to ignore (`.env`, `credentials/`, etc.) |
| `credentials/` | Folder containing your Google OAuth files. **Never commit this folder.** |
| `credentials/google_oauth.json` | The Google Cloud app credentials used by `authorize.py`. Treat this like a password. |
| `credentials/token_mark.json` | Mark's Google Calendar write access token (generated by `authorize.py`). |
| `credentials/token_emily.json` | Emily's Google Calendar write access token (generated by `authorize.py`). |

---

## 9. How to Update and Redeploy

Railway watches your GitHub repo and redeploys automatically every time you push a change. So "deploy" and "push to GitHub" are the same thing.

### The most common update: changing family_config.json

This is how you update rules, fix a broken calendar URL, add a new member, etc.

1. Open `family_config.json` in a text editor (or ask Claude Code to make the change for you)
2. Make your changes and save
3. Open Terminal, navigate to the project folder:
   ```bash
   cd "/Users/markallenbach/Documents/Claude/Ai Family Agent"
   ```
4. Commit and push:
   ```bash
   git add family_config.json
   git commit -m "Update family rules / fix calendar URL / whatever you changed"
   git push
   ```
5. Open Railway and watch the deployment status. It usually takes about 60 seconds to go live.

### Asking Claude Code to make changes

If you're already in a Claude Code session, you can just describe what you want:
- "Add a rule that no one can schedule anything during the family vacation May 20–27"
- "Fix Emily's work calendar URL — here's the new one: [paste URL]"
- "Add a new family member named Jake with phone +16465559876"

Claude Code will edit the file, and you can then commit and push from Terminal.

### Testing on your Mac before deploying

You can run the assistant locally to test a change before pushing it:

```bash
cd "/Users/markallenbach/Documents/Claude/Ai Family Agent"
python3 family_assistant.py --user Mark
```

This opens a command-line chat session. Ask it questions to make sure your changes work the way you expected. Type `quit` to exit. When you're happy, push to GitHub.

### Changing environment variables (API keys, tokens)

Environment variables (API keys, Twilio credentials, Google tokens) are stored directly in Railway — not in the code. To change one:

1. Go to railway.app → your project → your service → Variables tab
2. Find the variable and click to edit, or add a new one
3. Save — Railway will automatically redeploy with the new value

---

## Quick Reference

| Thing | Value |
|---|---|
| SMS number | +1 (855) 797-1691 |
| Railway health check | https://web-production-2d533.up.railway.app/health |
| GitHub repo | https://github.com/WellPlayedMark/family-assistant |
| Anthropic Console | console.anthropic.com |
| Twilio Console | console.twilio.com |
| Railway | railway.app |
| Config file | `family_config.json` in the project folder |
| Project folder on Mac | `/Users/markallenbach/Documents/Claude/Ai Family Agent` |
