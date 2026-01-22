import os
import base64
import json
import time
import random
from google.cloud import firestore
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore

PROJECT_ID = os.getenv("PROJECT_ID")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "events")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID env var is required")

db = firestore.Client(project=PROJECT_ID)

app = FastAPI(title="Worker Service", version="1.0.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}

def _inc_sharded_counter(db: firestore.Client, bucket_id: str, shards: int = 20) -> None:
    """
    Increment a sharded counter: stats/events_per_minute/{bucket_id}/shards/{shard}
    This avoids hot-spotting on a single document under high write concurrency.
    """
    shard = random.randint(0, shards - 1)
    ref = (
        db.collection("stats")
        .document("events_per_minute")
        .collection(bucket_id)
        .document(str(shard))
    )
    ref.set({"count": firestore.Increment(1)}, merge=True)


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

    # TEMPORARY (DLQ demo): force failure for specific eventType
    if event.get("eventType") == "fail":
        raise HTTPException(status_code=500, detail="Intentional failure for DLQ demo")

    event_id = event.get("eventId") or event.get("_pubsub", {}).get("messageId")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing eventId")

    # idempotency check
    doc_ref = db.collection(FIRESTORE_COLLECTION).document(str(event_id))
    if doc_ref.get().exists:
        return {"ok": True, "storedAs": event_id, "status": "duplicate"}

    event["processedAt"] = int(time.time())

    try:
        doc_ref.set(event)
        bucket_id = time.strftime("%Y%m%d%H%M")
        shard = random.randint(0, 19)

        stats_ref = (
            db.collection("stats")
            .document(bucket_id)
            .collection("shards")
            .document(str(shard))
        )

        stats_ref.set(
            {"count": firestore.Increment(1)},
            merge=True
        )

        print(f"SHARDED_COUNTER updated bucket={bucket_id} shard={shard}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firestore write failed: {e}")

    return {"ok": True, "storedAs": event_id}


