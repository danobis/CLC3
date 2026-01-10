import os
import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google.cloud import pubsub_v1

PROJECT_ID = os.getenv("PROJECT_ID")
TOPIC_NAME = os.getenv("TOPIC_NAME", "events-ingestion")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)

app = FastAPI(title="Ingestion Service", version="1.0.0")


class EventIn(BaseModel):
    eventType: str = Field(..., min_length=1, max_length=128)
    source: Optional[str] = Field(default=None, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)
    # optional client-provided id; if missing we generate one
    eventId: Optional[str] = Field(default=None, max_length=128)


@app.get("/")
def root():
    return {"service": "ingestion-api", "ok": True}


@app.post("/events", status_code=202)
def ingest_event(event: EventIn):
    event_id = event.eventId or str(uuid.uuid4())
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pub/Sub publish failed: {e}")

    return {"status": "accepted", "eventId": event_id, "pubsubMessageId": message_id}
