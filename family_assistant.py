#!/usr/bin/env python3
"""
Family Assistant — interactive CLI.

Usage:
    python family_assistant.py
    python family_assistant.py --user Mark
"""

import argparse
import sys
import anthropic

from assistant_core import load_config, build_system_prompt, run_agentic_loop


def run(current_user=None):
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        sys.exit(1)

    client = anthropic.Anthropic()

    configured = [
        m for m in config.get("members", [])
        if any(c.get("ics_url", "").strip() for c in (m.get("calendars") or []))
        or m.get("ics_url", "").strip()
    ]

    print()
    print(f"  🏠  {config.get('family_name', 'Family Assistant')}")
    print("  " + "─" * 44)
    if current_user:
        print(f"  Talking to: {current_user}")
    if configured:
        print(f"  📅  Calendars: {', '.join(m['name'] for m in configured)}")
    else:
        print("  ⚠️   No calendars configured yet — see SETUP.md")
    print("  Type 'quit' to exit, 'switch' to change user")
    print()

    system_prompt = build_system_prompt(config, current_user)
    messages: list[dict] = []

    while True:
        speaker = current_user or "You"
        try:
            user_input = input(f"  {speaker}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye! 👋\n")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye"):
            print("\n  Goodbye! 👋\n")
            break

        if user_input.lower() == "switch":
            current_user = input("  Who is now speaking? ").strip() or None
            system_prompt = build_system_prompt(config, current_user)
            print(f"  Switched to: {current_user or 'anonymous'}\n")
            continue

        messages.append({"role": "user", "content": user_input})

        reply, messages = run_agentic_loop(
            client,
            config,
            messages,
            system_prompt,
            on_tool_call=lambda name: print(f"  [🔍 {name}...]"),
        )

        if reply:
            print(f"\n  Assistant: {reply}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Family scheduling assistant (CLI)")
    parser.add_argument("--user", "-u", default=None, help="Your name, e.g. --user Mark")
    args = parser.parse_args()
    run(current_user=args.user)
