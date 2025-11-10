# client.py
# Usage examples:
#  python client.py "Find me a free 60 minute slot on 2025-10-23"
#  python client.py "Book a meeting with John tomorrow at 10"
#  python client.py "Show my events on 2025-10-22"

import sys
import requests
import json
from datetime import datetime, timedelta
from llm import generate

SERVER = "http://localhost:8000/jsonrpc"

def jsonrpc_call(method, params, id=1):
    payload = {"jsonrpc":"2.0","method":method,"params":params,"id":id}
    r = requests.post(SERVER, json=payload, timeout=10)
    return r.json()

def find_free_and_book(day_iso, duration_minutes, title="Meeting via MCP", attendees=None):
    print("→ asking server to find free slot")
    r = jsonrpc_call("find_free_slot", {"day": day_iso, "duration_minutes": duration_minutes}, id=1)
    if "error" in r:
        print("Server error:", r["error"])
        return
    slot = r.get("result")
    if not slot:
        print("No free slot found that day.")
        return
    print("Found slot:", slot)
    # create event
    create = jsonrpc_call("create_event", {
        "title": title,
        "start": slot["start"],
        "end": slot["end"],
        "attendees": attendees or []
    }, id=2)
    if "error" in create:
        print("Create error:", create["error"])
        return
    ev = create.get("result")
    print("Event created:", ev)
    # ask LLM to produce confirmation text
    prompt = f"You scheduled an event titled '{title}' from {ev['start']} to {ev['end']} with attendees {ev['attendees']}. Produce a short friendly confirmation message."
    msg = generate(prompt)
    print("\n=== LLM Confirmation ===")
    print(msg)
    print("========================\n")

def show_events(day_iso):
    r = jsonrpc_call("get_events_for_day", {"day": day_iso}, id=3)
    if "error" in r:
        print("Error:", r["error"])
        return
    evs = r.get("result", [])
    print(f"Events on {day_iso}:")
    for e in evs:
        print("-", e["start"], e["title"])

def main(argv):
    if len(argv) < 2:
        print("Usage: python client.py \"<command>\"")
        return
    cmd = argv[1].lower()
    if "free" in cmd or "find" in cmd:
        # Basic parse: look for date in YYYY-MM-DD or use tomorrow
        # This is a demo; parsing is naive
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", cmd)
        if m:
            day = m.group(1)
        elif "tomorrow" in cmd:
            day = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
        else:
            day = datetime.utcnow().date().isoformat()
        # duration
        dur = 60
        dm = re.search(r"(\d+)\s*min", cmd)
        if dm:
            dur = int(dm.group(1))
        find_free_and_book(day, dur, title="Quick MCP Booking")
    elif "book" in cmd or "schedule" in cmd:
        # naive: assume "book ... on YYYY-MM-DD" or tomorrow 10:00
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", cmd)
        if m:
            day = m.group(1)
            # find a free slot and book
            find_free_and_book(day, 60, title="Booked by user request")
        elif "tomorrow" in cmd:
            day = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
            find_free_and_book(day, 60, title="Booked by user request")
        else:
            print("Could not parse booking date; try including YYYY-MM-DD or 'tomorrow'.")
    elif "show" in cmd or "events" in cmd:
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", cmd)
        if m:
            show_events(m.group(1))
        else:
            # default to today
            show_events(datetime.utcnow().date().isoformat())
    else:
        print("Unrecognized command. Examples: 'find free 60 min on 2025-10-23', 'book tomorrow', 'show events 2025-10-22'")

if __name__ == "__main__":
    main(sys.argv)
