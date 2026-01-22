import json
import logging
import os
import time
from typing import Any, Dict, List

import google.cloud.logging
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.cloud import firestore

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
class ServiceConfig:
    PROJECT_ID: str = os.getenv("PROJECT_ID")
    REGION: str = os.getenv("REGION", "europe-west3")
    FIRESTORE_COLLECTION: str = os.getenv("FIRESTORE_COLLECTION", "events")
    TOPIC_NAME: str = os.getenv("TOPIC_NAME", "events-ingestion")
    INGESTION_URL: str = os.getenv("INGESTION_URL")
    SERVICE_NAME: str = "dashboard-ui"
    VERSION: str = "1.0.0"

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID:
            raise RuntimeError("Environment variable 'PROJECT_ID' is required.")
        if not cls.INGESTION_URL:
            raise RuntimeError("Environment variable 'INGESTION_URL' is required.")

ServiceConfig.validate()

# -----------------------------------------------------------------------------
# Logging Setup
# -----------------------------------------------------------------------------
def setup_logging():
    client = google.cloud.logging.Client()
    client.setup_logging()
    return logging.getLogger(ServiceConfig.SERVICE_NAME)

logger = setup_logging()

# -----------------------------------------------------------------------------
# Cloud Clients & Templates
# -----------------------------------------------------------------------------
db = firestore.Client(project=ServiceConfig.PROJECT_ID)
templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _fetch_latest_events(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves the latest events from Firestore.
    Attempts to sort by 'processedAt' descending. Falls back to default order if index is missing.
    """
    collection_ref = db.collection(ServiceConfig.FIRESTORE_COLLECTION)
    try:
        docs_stream = (
            collection_ref
            .order_by("processedAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
    except Exception:
        # Fallback: no ordering
        docs_stream = collection_ref.limit(limit).stream()

    out: List[Dict[str, Any]] = []
    for d in docs_stream:
        data = d.to_dict() or {}
        data["_docId"] = d.id
        out.append(data)
    return out

# -----------------------------------------------------------------------------
# App & Routes
# -----------------------------------------------------------------------------
app = FastAPI(title="CLC3 Dashboard UI", version=ServiceConfig.VERSION)

# Mount static files if directory exists
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "project_id": ServiceConfig.PROJECT_ID,
            "region": ServiceConfig.REGION,
            "collection": ServiceConfig.FIRESTORE_COLLECTION,
            "topic": ServiceConfig.TOPIC_NAME,
            "ingestion_url": ServiceConfig.INGESTION_URL,
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

    # Handle payload if it comes as a string (e.g. from textarea)
    if isinstance(payload, str):
        payload = payload.strip()
        if payload:
            try:
                payload = json.loads(payload)
            except Exception:
                raise HTTPException(status_code=400, detail="payload must be valid JSON")
        else:
            payload = {}

    target_url = f"{ServiceConfig.INGESTION_URL.rstrip('/')}/events"
    
    try:
        resp = requests.post(
            target_url,
            json={"eventType": event_type, "source": source, "payload": payload},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.warning(f"Ingestion API returned error: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Failed to call Ingestion API: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to call upstream: {str(e)}")

    return JSONResponse(
        status_code=resp.status_code,
        content={
            "status_code": resp.status_code,
            "response": resp.json() if resp.content else {}
        },
    )
