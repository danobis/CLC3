import os
import base64
import json
import time
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

PROJECT_ID = os.getenv("PROJECT_ID")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "events")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

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
        raise HTTPException(status_code=400, detail=f"Bad Pub/Sub message: {e}")

    # (DLQ demo): force failure for specific eventType
    if event.get("eventType") == "fail":
        raise HTTPException(status_code=500, detail="Intentional failure for DLQ demo")

    event_id = event.get("eventId") or event.get("_pubsub", {}).get("messageId")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing eventId")

    # idempotency check
    doc_ref = db.collection(FIRESTORE_COLLECTION).document(str(event_id))
    if doc_ref.get().exists:
        logger.info(json.dumps({
            "service": "worker",
            "status": "duplicate",
            "eventId": event_id,
            "eventType": event.get("eventType"),
        }))
        return {"ok": True, "storedAs": event_id, "status": "duplicate"}

    event["processedAt"] = int(time.time())

    try:
        doc_ref.set(event)
    except Exception as e:
        logger.error(json.dumps({
            "service": "worker",
            "status": "firestore_failed",
            "eventId": event_id,
            "eventType": event.get("eventType"),
            "error": str(e),
        }))
        raise HTTPException(status_code=500, detail=f"Firestore write failed: {e}")

    logger.info(json.dumps({
        "service": "worker",
        "status": "stored",
        "eventId": event_id,
        "eventType": event.get("eventType"),
    }))
    return {"ok": True, "storedAs": event_id}


