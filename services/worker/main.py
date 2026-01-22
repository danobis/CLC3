import base64
import json
import logging
import os
import time
from typing import Any, Dict

import google.cloud.logging
from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

PROJECT_ID = os.getenv("PROJECT_ID")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "events")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")

log_client = google.cloud.logging.Client()
log_client.setup_logging()

logger = logging.getLogger(__name__)

db = firestore.Client(project=PROJECT_ID)

app = FastAPI(title="Worker Service", version="1.0.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _decode_pubsub_message(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pub/Sub push delivers:
    {
      "message": { "data": "base64...", "attributes": {...}, "messageId": "...", ... },
      "subscription": "..."
    }
    """
    if "message" not in body or "data" not in body["message"]:
        raise ValueError("Invalid Pub/Sub push payload: missing message.data")

    msg = body["message"]
    data_b64 = msg["data"]
    data_json = base64.b64decode(data_b64).decode("utf-8")
    payload = json.loads(data_json)

    # include some metadata
    payload["_pubsub"] = {
        "messageId": msg.get("messageId"),
        "publishTime": msg.get("publishTime"),
        "attributes": msg.get("attributes", {}),
    }
    return payload


@app.post("/pubsub")
async def handle_pubsub(request: Request):
    try:
        body = await request.json()
        event = _decode_pubsub_message(body)
    except Exception as e:
        logger.error(f"Failed to decode Pub/Sub message: {e}")
        raise HTTPException(status_code=400, detail=f"Bad Pub/Sub message: {e}")

    # TEMPORARY (DLQ demo): force failure for specific eventType
    if event.get("eventType") == "fail":
        logger.warning("Simulating failure for eventType='fail' (DLQ Demo)")
        raise HTTPException(status_code=500, detail="Intentional failure for DLQ demo")

    event_id = event.get("eventId") or event.get("_pubsub", {}).get("messageId")
    if not event_id:
        logger.error("Event received without eventId")
        raise HTTPException(status_code=400, detail="Missing eventId")

    # idempotency check
    doc_ref = db.collection(FIRESTORE_COLLECTION).document(str(event_id))
    if doc_ref.get().exists:
        logger.info(f"Skipping duplicate event: {event_id}")
        return {"ok": True, "storedAs": event_id, "status": "duplicate"}

    event["processedAt"] = int(time.time())

    try:
        doc_ref.set(event)
        logger.info(f"Successfully processed and stored event: {event_id}")
    except Exception as e:
        logger.error(f"Firestore write failed for {event_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Firestore write failed: {e}")

    return {"ok": True, "storedAs": event_id}
