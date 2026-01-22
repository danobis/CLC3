import os
import json
import time
import uuid
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google.cloud import pubsub_v1
import google.cloud.logging

PROJECT_ID = os.getenv("PROJECT_ID")
TOPIC_NAME = os.getenv("TOPIC_NAME", "events-ingestion")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")

# Setup Cloud Logging
# This connects the standard Python logger to Google Cloud Logging.
# In Cloud Run, this automatically ensures JSON formatting.
log_client = google.cloud.logging.Client()
log_client.setup_logging()

logger = logging.getLogger(__name__)

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)

app = FastAPI(title="Ingestion Service", version="1.0.0")


class EventIn(BaseModel):
    eventType: str = Field(..., min_length=1, max_length=128)
    source: Optional[str] = Field(default=None, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)
    # optional client-provided id; if missing, we generate one
    eventId: Optional[str] = Field(default=None, max_length=128)


@app.get("/")
def root():
    return {"service": "ingestion-api", "ok": True}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/events", status_code=202)
def ingest_event(event: EventIn):
    event_id = event.eventId or str(uuid.uuid4())

    logger.info(f"Received ingestion request for eventType: {event.eventType}",
                extra={"json_fields": {"source": event.source}})

    envelope = {
        "eventId": event_id,
        "eventType": event.eventType,
        "source": event.source,
        "payload": event.payload,
        "ingestedAt": int(time.time()),
    }

    data = json.dumps(envelope).encode("utf-8")

    try:
        future = publisher.publish(
            topic_path,
            data=data,
            eventType=envelope["eventType"],
            eventId=envelope["eventId"],
        )
        message_id = future.result(timeout=10)
        logger.info(f"Published message {message_id} to Pub/Sub", extra={"json_fields": {"eventId": event_id}})
    except Exception as e:
        logger.error(f"Pub/Sub publish failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pub/Sub publish failed: {e}")

    return {"status": "accepted", "eventId": event_id, "pubsubMessageId": message_id}
