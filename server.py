# server.py
# MCP Calendar Server with a tiny web UI served from / (static/index.html)
# and a helper endpoint /api/book_and_confirm to find+create an event and return an LLM confirmation.
#
# Run: uvicorn server:app --reload --port 8000

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List
from datetime import datetime, timedelta
import uuid
import json
import os

# import the llm wrapper you already have (it will use OPENROUTER_API_KEY if set)
from llm import generate as llm_generate

app = FastAPI(title="MCP Calendar Server (demo with UI)")

# serve static files from ./static (index.html)
# make sure to create a folder named "static" next to this file and put index.html inside
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"⚠️  Static directory not found at {STATIC_DIR}. Create ./static/index.html to serve UI.")

@app.get("/", response_class=FileResponse)
def read_index():
    if os.path.isfile(INDEX_FILE):
        return INDEX_FILE
    raise HTTPException(status_code=404, detail="Index not found")

# In-memory calendar events (demo)
EVENTS: List[Dict[str, Any]] = [
    {
        "id": "e1",
        "title": "Weekly team sync",
        "start": "2025-10-22T10:00:00",
        "end": "2025-10-22T10:30:00",
        "attendees": ["alice@example.com"],
        "created_by": "system"
    },
    {
        "id": "e2",
        "title": "Project planning",
        "start": "2025-10-22T15:00:00",
        "end": "2025-10-22T16:00:00",
        "attendees": ["bob@example.com"],
        "created_by": "system"
    }
]

class JSONRPCRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Dict[str, Any] = {}
    id: Any = None

def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)

def iso(dt: datetime) -> str:
    return dt.isoformat(timespec='seconds')

@app.post("/jsonrpc")
async def jsonrpc(req: Request):
    body = await req.json()
    try:
        rpc = JSONRPCRequest(**body)
    except Exception as e:
        return {"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid Request","data":str(e)},"id":None}

    try:
        if rpc.method == "list_events":
            return {"jsonrpc":"2.0","result": EVENTS, "id": rpc.id}

        elif rpc.method == "get_events_for_day":
            day = rpc.params.get("day")
            if not day:
                return {"jsonrpc":"2.0","error":{"code":-32602,"message":"Missing param 'day'"},"id":rpc.id}
            start_day = datetime.fromisoformat(day)
            end_day = start_day + timedelta(days=1)
            matches = [e for e in EVENTS if (parse_iso(e["start"]) >= start_day and parse_iso(e["start"]) < end_day)]
            return {"jsonrpc":"2.0","result": matches, "id": rpc.id}

        elif rpc.method == "find_free_slot":
            day = rpc.params.get("day")
            duration = int(rpc.params.get("duration_minutes", 60))
            if not day:
                return {"jsonrpc":"2.0","error":{"code":-32602,"message":"Missing param 'day'"},"id":rpc.id}
            work_start = datetime.fromisoformat(day).replace(hour=9, minute=0, second=0)
            work_end = work_start.replace(hour=17)
            slot = None
            evs = sorted([e for e in EVENTS if parse_iso(e["start"]).date() == work_start.date()], key=lambda x: x["start"])
            cursor = work_start
            for e in evs:
                s = parse_iso(e["start"])
                if (s - cursor).total_seconds() >= duration*60:
                    slot = {"start": iso(cursor), "end": iso(cursor + timedelta(minutes=duration))}
                    break
                cursor = max(cursor, parse_iso(e["end"]))
            if slot is None and (work_end - cursor).total_seconds() >= duration*60:
                slot = {"start": iso(cursor), "end": iso(cursor + timedelta(minutes=duration))}
            return {"jsonrpc":"2.0","result": slot, "id": rpc.id}

        elif rpc.method == "create_event":
            title = rpc.params.get("title")
            start = rpc.params.get("start")
            end = rpc.params.get("end")
            attendees = rpc.params.get("attendees", [])
            if not (title and start and end):
                return {"jsonrpc":"2.0","error":{"code":-32602,"message":"Missing title/start/end"},"id":rpc.id}
            new_e = {
                "id": str(uuid.uuid4())[:8],
                "title": title,
                "start": start,
                "end": end,
                "attendees": attendees,
                "created_by": rpc.params.get("created_by","client")
            }
            EVENTS.append(new_e)
            return {"jsonrpc":"2.0","result": new_e, "id": rpc.id}

        else:
            return {"jsonrpc":"2.0","error":{"code":-32601,"message":"Method not found"},"id":rpc.id}

    except Exception as e:
        return {"jsonrpc":"2.0","error":{"code":-32000,"message":"Server error","data":str(e)},"id":rpc.id}


# -------------------------
# New REST helper endpoint used by the frontend
# -------------------------
from pydantic import BaseModel as PydanticBaseModel

class BookRequest(PydanticBaseModel):
    day: str  # "YYYY-MM-DD"
    duration_minutes: int = 60
    title: str = "Booked via UI"
    attendees: List[str] = []

@app.post("/api/book_and_confirm")
async def book_and_confirm(req: BookRequest):
    """
    Helper endpoint: finds a free slot, creates the event, then asks llm_generate()
    for a human-friendly confirmation message and returns both event + confirmation.
    """
    day = req.day
    duration = req.duration_minutes
    # 1) find slot (reuse same logic as JSON-RPC method)
    work_start = datetime.fromisoformat(day).replace(hour=9, minute=0, second=0)
    work_end = work_start.replace(hour=17)
    slot = None
    evs = sorted([e for e in EVENTS if parse_iso(e["start"]).date() == work_start.date()], key=lambda x: x["start"])
    cursor = work_start
    for e in evs:
        s = parse_iso(e["start"])
        if (s - cursor).total_seconds() >= duration*60:
            slot = {"start": iso(cursor), "end": iso(cursor + timedelta(minutes=duration))}
            break
        cursor = max(cursor, parse_iso(e["end"]))
    if slot is None and (work_end - cursor).total_seconds() >= duration*60:
        slot = {"start": iso(cursor), "end": iso(cursor + timedelta(minutes=duration))}

    if not slot:
        raise HTTPException(status_code=404, detail="No free slot found")

    # 2) create event
    new_e = {
        "id": str(uuid.uuid4())[:8],
        "title": req.title,
        "start": slot["start"],
        "end": slot["end"],
        "attendees": req.attendees or [],
        "created_by": "ui"
    }
    EVENTS.append(new_e)

    # 3) ask LLM to produce a confirmation message
    prompt = f"You scheduled an event titled '{new_e['title']}' from {new_e['start']} to {new_e['end']} with attendees {new_e['attendees']}. Produce a short friendly confirmation message."
    confirmation = llm_generate(prompt)

    return {"event": new_e, "confirmation": confirmation}
