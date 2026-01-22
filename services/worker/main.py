import base64
import json
import logging
import os
import time
from typing import Any, Dict

import google.cloud.logging
from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
class ServiceConfig:
    PROJECT_ID: str = os.getenv("PROJECT_ID")
    FIRESTORE_COLLECTION: str = os.getenv("FIRESTORE_COLLECTION", "events")
    SERVICE_NAME: str = "worker"
    VERSION: str = "1.0.0"

    @classmethod
    def validate(cls):
        if not cls.PROJECT_ID:
            raise RuntimeError("Environment variable 'PROJECT_ID' is required.")

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
# Cloud Clients
# -----------------------------------------------------------------------------
db = firestore.Client(project=ServiceConfig.PROJECT_ID)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _decode_pubsub_message(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decodes the Pub/Sub push payload.
    Expected format:
    { "message": { "data": "base64...", "attributes": {...}, ... }, ... }
    """
    if "message" not in body or "data" not in body["message"]:
        raise ValueError("Invalid Pub/Sub push payload: missing message.data")

    msg = body["message"]
    data_b64 = msg["data"]
    data_json = base64.b64decode(data_b64).decode("utf-8")
    payload = json.loads(data_json)

    # Attach metadata
    payload["_pubsub"] = {
        "messageId": msg.get("messageId"),
        "publishTime": msg.get("publishTime"),
        "attributes": msg.get("attributes", {}),
    }
    return payload

# -----------------------------------------------------------------------------
# App & Routes
# -----------------------------------------------------------------------------
app = FastAPI(title="Worker Service", version=ServiceConfig.VERSION)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/pubsub")
async def handle_pubsub(request: Request):
    try:
        body = await request.json()
        event = _decode_pubsub_message(body)
    except Exception as e:
        logger.error(f"Failed to decode Pub/Sub message: {e}")
        raise HTTPException(status_code=400, detail=f"Bad Pub/Sub message: {str(e)}")

    # TEMPORARY (DLQ demo): force failure for specific eventType
    if event.get("eventType") == "fail":
        logger.warning("Simulating failure for eventType='fail' (DLQ Demo)")
        raise HTTPException(status_code=500, detail="Intentional failure for DLQ demo")

    event_id = event.get("eventId") or event.get("_pubsub", {}).get("messageId")
    if not event_id:
        logger.error("Event received without eventId")
        raise HTTPException(status_code=400, detail="Missing eventId")

    # Idempotency check
    doc_ref = db.collection(ServiceConfig.FIRESTORE_COLLECTION).document(str(event_id))
    if doc_ref.get().exists:
        logger.info(f"Skipping duplicate event: {event_id}")
        return {"ok": True, "storedAs": event_id, "status": "duplicate"}

    event["processedAt"] = int(time.time())

    try:
        doc_ref.set(event)
        logger.info(f"Successfully processed and stored event: {event_id}")
    except Exception as e:
        logger.error(f"Firestore write failed for {event_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Firestore write failed: {str(e)}")

    return {"ok": True, "storedAs": event_id}
