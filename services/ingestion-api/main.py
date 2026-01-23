import json  # <--- HIER GEÄNDERT
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import google.cloud.logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from google.cloud import firestore, pubsub_v1
from pydantic import BaseModel, Field

PROJECT_ID = os.getenv("PROJECT_ID")
# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
class ServiceConfig:
    PROJECT_ID: str = os.getenv("PROJECT_ID")
    TOPIC_NAME: str = os.getenv("TOPIC_NAME", "events-ingestion")
    SERVICE_NAME: str = "ingestion-api"
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
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(ServiceConfig.PROJECT_ID, ServiceConfig.TOPIC_NAME)
db = firestore.Client(project=ServiceConfig.PROJECT_ID)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class EventIn(BaseModel):
    eventType: str = Field(..., min_length=1, max_length=128)
    source: Optional[str] = Field(default=None, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)
    # optional client-provided id; if missing we generate one
    eventId: Optional[str] = Field(default=None, max_length=128)

# -----------------------------------------------------------------------------
# App & Routes
# -----------------------------------------------------------------------------
app = FastAPI(title="Ingestion Service", version=ServiceConfig.VERSION)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def root():
    return {"service": ServiceConfig.SERVICE_NAME, "ok": True}

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
        logger.error(f"Pub/Sub publish failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pub/Sub publish failed: {e}")

    return {"status": "accepted", "eventId": event_id, "pubsubMessageId": message_id}
