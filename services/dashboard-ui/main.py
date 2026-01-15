import os
import json
import base64
from typing import Any, Dict, List

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore, pubsub_v1

PROJECT_ID = os.getenv("PROJECT_ID")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "events")
INGESTION_URL = os.getenv("INGESTION_URL")  # e.g. https://ingestion-api-...run.app

TOPIC_NAME = os.getenv("TOPIC_NAME", "events-ingestion")
DLQ_SUBSCRIPTION = os.getenv("DLQ_SUBSCRIPTION", "events-dlq-sub")

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)
dlq_sub_path = subscriber.subscription_path(PROJECT_ID, DLQ_SUBSCRIPTION)

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
        # fallback: no ordering (works even if processedAt missing on some docs)
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
        content={
            "status_code": resp.status_code,
            "response": resp.json() if resp.content else {},
        },
    )


def _decode_pubsub_data(
    msg: pubsub_v1.subscriber.message.Message,
) -> Dict[str, Any]:
    data = msg.message.data.decode("utf-8")
    try:
        return json.loads(data)
    except Exception:
        return {"raw": data}


@app.get("/api/dlq/pull")
def dlq_pull(limit: int = 10):
    resp = subscriber.pull(
        request={"subscription": dlq_sub_path, "max_messages": limit}
    )

    out = []
    for rm in resp.received_messages:
        m = rm.message
        out.append(
            {
                "ackId": rm.ack_id,
                "messageId": m.message_id,
                "publishTime": m.publish_time.isoformat()
                if m.publish_time
                else None,
                "attributes": dict(m.attributes),
                "data": _decode_pubsub_data(rm),
            }
        )

    # sort newest first (publishTime desc)
    out.sort(
        key=lambda x: x["publishTime"] or "",
        reverse=True,
    )

    return {"messages": out}


@app.post("/api/dlq/replay")
async def dlq_replay(request: Request):
    body = await request.json()
    ack_id = body.get("ackId")
    data = body.get("data")

    if not ack_id or not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="ackId and data required")

    # data is the original event envelope from ingestion
    event_id = data.get("eventId")
    event_type = data.get("eventType")

    if not event_id or not event_type:
        raise HTTPException(
            status_code=400,
            detail="DLQ message missing eventId/eventType",
        )

    # publish same event back to main topic (preserve eventId!)
    payload_bytes = json.dumps(data).encode("utf-8")
    publisher.publish(
        topic_path,
        data=payload_bytes,
        eventType=event_type,
        eventId=str(event_id),
    ).result(timeout=10)

    # ack the DLQ message so it doesn't show up again
    subscriber.acknowledge(
        request={"subscription": dlq_sub_path, "ack_ids": [ack_id]}
    )

    return {"ok": True, "replayedEventId": event_id}
