# Family Assistant — Setup Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Add this to your `~/.zshrc` to make it permanent:
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
```

## 3. Get your Google Calendar ICS URLs (2 minutes per person)

No OAuth, no Google Cloud project needed. Google Calendar lets you export a private read-only URL for each calendar.

### For each family member:

1. Open **Google Calendar** → click the three dots next to the calendar name (in the left sidebar)
2. Click **Settings and sharing**
3. Scroll down to **"Secret address in iCal format"**
4. Click **Copy** — you'll get a URL that looks like:
   ```
   https://calendar.google.com/calendar/ical/your.email%40gmail.com/private-abc123.../basic.ics
   ```
5. Paste it into `family_config.json` as the `ics_url` for that person

### Example `family_config.json` after setup:

```json
{
  "members": [
    {
      "name": "Mark",
      "role": "Dad",
      "calendars": [
        { "label": "Personal", "ics_url": "https://calendar.google.com/calendar/ical/mark%40gmail.com/private-abc123/basic.ics" },
        { "label": "Work",     "ics_url": "https://calendar.google.com/calendar/ical/mark%40company.com/private-def456/basic.ics" }
      ]
    },
    {
      "name": "Sarah",
      "role": "Mom",
      "calendars": [
        { "label": "Personal", "ics_url": "https://calendar.google.com/calendar/ical/sarah%40gmail.com/private-xyz789/basic.ics" },
        { "label": "Work",     "ics_url": "https://calendar.google.com/calendar/ical/sarah%40company.com/private-ghi012/basic.ics" }
      ]
    },
    {
      "name": "Emma",
      "role": "Child",
      "calendars": [
        { "label": "School",      "ics_url": "https://calendar.google.com/calendar/ical/emma%40gmail.com/private-jkl345/basic.ics" },
        { "label": "Activities",  "ics_url": "https://calendar.google.com/calendar/ical/emma%40gmail.com/private-mno678/basic.ics" }
      ]
    }
  ]
}
```

You can add as many `calendars` entries as you want per person — work, personal, school, sports, shared family calendar, etc.

> **Note:** The ICS URL is private — treat it like a password. It gives read-only access to that calendar.
> If you ever need to revoke access, go back to that calendar's settings and click "Reset" next to the secret address.

## 4. Customize your family rules

Edit `family_config.json`:
- Update your actual names under `members`
- Edit `rules` to match your real family rules
- Add any preferences you want the assistant to know about

## 5. Run the assistant

```bash
# As Mark
python family_assistant.py --user Mark

# As your wife
python family_assistant.py --user Sarah

# Or just start and type 'switch' to change who's talking
python family_assistant.py
```

## Example questions to try

- "Can I go on a business trip April 10–14?"
- "Is Thursday evening free?"
- "What does our week look like?"
- "We want to go out for dinner Friday — is that okay?"
- "What family events do we have next month?"
- "Does anything conflict with the school play on the 15th?"

## 6. SMS Bot Setup (Twilio)

Everyone texts a single phone number — the bot replies as if it knows who you are.

### Step 1: Get a Twilio account

1. Sign up at **twilio.com** — the free trial includes a phone number and some credits
2. From the Twilio Console dashboard, copy your **Account SID** and **Auth Token**
3. Your trial phone number is listed under **Phone Numbers → Manage → Active Numbers**

### Step 2: Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your Twilio credentials and Anthropic key.

### Step 3: Add phone numbers to family_config.json

Add each person's cell number in E.164 format (`+1XXXXXXXXXX`):

```json
{ "name": "Mark", "phone": "+15551234567", ... }
```

This is how the bot knows who is texting.

### Step 4: Install dependencies and start the server

```bash
pip install -r requirements.txt
python sms_server.py
```

You should see:
```
Starting SMS server on port 5000
Family: The Allenbach Family
Members with phones: ['Mark', 'Sarah']
```

### Step 5: Expose your server publicly with ngrok

Twilio needs a public HTTPS URL to send messages to.

```bash
# Install ngrok if you don't have it: https://ngrok.com/download
ngrok http 5000
```

Copy the `https://xxxx.ngrok-free.app` URL it gives you.

### Step 6: Point Twilio at your server

1. In the Twilio Console → **Phone Numbers → Manage → Active Numbers**
2. Click your number
3. Under **Messaging Configuration → "A message comes in"**:
   - Set to **Webhook**
   - URL: `https://xxxx.ngrok-free.app/sms`
   - Method: **HTTP POST**
4. Click **Save**

### Step 7: Test it

Text your Twilio number from your phone. You should get a reply within a few seconds.

### Making it permanent (instead of ngrok)

ngrok URLs change every restart. For a stable always-on setup:

- **[Railway](https://railway.app)** — connect your GitHub repo, set env vars in dashboard, deploy. Free tier available.
- **[Render](https://render.com)** — same process. Free tier sleeps after 15 min of inactivity (slow first response).
- **[Fly.io](https://fly.io)** — `fly launch` then `fly deploy`. Small always-on free tier.

Any of these gives you a permanent HTTPS URL to paste into Twilio.

---

## Tips

- Keep `family_config.json` updated with accurate family rules — this is what the assistant enforces
- If a new calendar is added (kids, shared family calendar), add it as a new member entry with an ICS URL
- The SMS bot remembers context for 30 minutes of inactivity, then resets for the next conversation
- The CLI (`family_assistant.py`) and SMS bot share the same brain — both stay in sync automatically
