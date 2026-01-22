import os
import json
from typing import Any, Dict, List

import requests
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

PROJECT_ID = os.getenv("PROJECT_ID")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "events")
INGESTION_URL = os.getenv("INGESTION_URL")  # e.g. https://ingestion-api-...run.app

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")
if not INGESTION_URL:
    raise RuntimeError("INGESTION_URL env var is required")

db = firestore.Client(project=PROJECT_ID)

app = FastAPI(title="CLC3 Dashboard UI", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# static files
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _fetch_latest_events(limit: int = 20) -> List[Dict[str, Any]]:
    # We sort by processedAt descending if present; otherwise fallback to doc id order.
    # Firestore requires an index for complex queries; this simple sort typically works
    # if processedAt exists on all docs. If not, it still returns documents, just not perfectly sorted.
    try:
        docs = (
            db.collection(FIRESTORE_COLLECTION)
            .order_by("processedAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
    except Exception:
        # Fallback: no ordering (works even if processedAt missing on some docs)
        docs = db.collection(FIRESTORE_COLLECTION).limit(limit).stream()

    out: List[Dict[str, Any]] = []
    for d in docs:
        data = d.to_dict() or {}
        data["_docId"] = d.id
        out.append(data)
    return out


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "project_id": PROJECT_ID,
            "region": os.getenv("REGION", "europe-west3"),
            "collection": FIRESTORE_COLLECTION,
            "topic": os.getenv("TOPIC_NAME", "events-ingestion"),
            "ingestion_url": INGESTION_URL,
        },
    )


@app.get("/api/events")
def api_events(limit: int = 20):
    events = _fetch_latest_events(limit=limit)
    return JSONResponse({"events": events})

@app.get("/api/stats/minute")
def api_stats_minute():
    # current minute bucket
    bucket_id = time.strftime("%Y%m%d%H%M")
    # sum all shard docs for that bucket
    docs = (
        db.collection("stats")
        .document("events_per_minute")
        .collection(bucket_id)
        .stream()
    )

    total = 0
    shards = 0
    for d in docs:
        data = d.to_dict() or {}
        total += int(data.get("count", 0))
        shards += 1

    return JSONResponse({"bucket": bucket_id, "total": total, "shards_seen": shards})

@app.post("/api/publish")
async def api_publish(request: Request):
    body = await request.json()
    event_type = body.get("eventType", "demo.created")
    source = body.get("source", "dashboard-ui")
    payload = body.get("payload", {})

    # payload may be a string from textarea; allow JSON string too
    if isinstance(payload, str):
        payload = payload.strip()
        if payload:
            try:
                payload = json.loads(payload)
            except Exception:
                raise HTTPException(status_code=400, detail="payload must be valid JSON")
        else:
            payload = {}

    resp = requests.post(
        f"{INGESTION_URL.rstrip('/')}/events",
        json={"eventType": event_type, "source": source, "payload": payload},
        timeout=10,
    )

    # pass through response for debugging
    return JSONResponse(
        status_code=resp.status_code,
        content={"status_code": resp.status_code, "response": resp.json() if resp.content else {}},
    )
