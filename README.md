# CLC3

**Project Members**
- Christopher Nobis
- Daniel Hametner

---

## Project Status & Shared Context

### What has been implemented

A complete **serverless, event-driven ingestion pipeline** has been implemented on **Google Cloud Platform**, with infrastructure managed via **Terraform**.

The following components are provisioned and in active use:

- Google Cloud project and access control (IAM)
- Terraform remote state stored in a private GCS bucket
- Required GCP APIs enabled (Cloud Run, Pub/Sub, Firestore, Artifact Registry, Cloud Build)
- Firestore database (Native mode)
- Pub/Sub topic and push subscription
- Dedicated service accounts with least-privilege permissions
- Cloud Run ingestion service (public HTTP API)
- Cloud Run worker service (private, Pub/Sub push target)

The system has been tested end-to-end and is fully functional.

---

### Architecture Overview

- **Ingestion Service (Cloud Run)**  
  Public HTTP endpoint that accepts events and publishes them to Pub/Sub.

- **Message Broker (Pub/Sub)**  
  Decouples ingestion from processing and delivers events asynchronously.

- **Worker Service (Cloud Run)**  
  Consumes Pub/Sub push messages, processes events, and persists them in Firestore.

- **Storage (Firestore)**  
  Stores processed event documents, including ingestion and processing metadata.

---

### Shared facts (stable baseline)

The following values are considered **fixed** and should not be changed without coordination:

- **GCP Project:** `clc3-481608`
- **Region:** `europe-west3`
- **Firestore:** Native mode, default database
- **Firestore collection:** `events`
- **Pub/Sub topic:** `events-ingestion`
- **Pub/Sub subscription:** `events-worker-sub` (push)

Infrastructure is managed exclusively via Terraform.  
Cloud resources should not be created or modified manually in the GCP Console.

---

### End-to-End Verification

The system has been verified end-to-end:

1. Events are sent via HTTP to the ingestion service
2. Events are published to Pub/Sub
3. Worker service receives events asynchronously via push subscription
4. Processed events are stored in Firestore

Firestore documents include:
- Event payload
- Ingestion timestamp
- Processing timestamp
- Pub/Sub metadata (message ID, publish time, attributes)

---

### Reliability: Dead-Letter Queue (DLQ)

The worker subscription is configured with a dead-letter topic (`events-dlq`).
Messages that fail processing repeatedly (max 5 delivery attempts) are automatically routed to the DLQ for inspection and replay.

For demonstration purposes, events with `eventType="fail"` intentionally trigger processing failures to showcase retry and dead-letter handling.

### Reliability: Idempotent Processing

The worker service implements idempotent processing based on `eventId`.
If a message is redelivered by Pub/Sub, the worker detects that the event
was already processed and safely skips duplicate writes.

This ensures correct behavior under retries and at-least-once delivery.

---

### What can be done next

- Extend event validation or schema enforcement
- Add monitoring and alerting (Cloud Logging / Metrics)
- Add authentication to the ingestion endpoint
- Expand worker logic for additional processing steps

Any further infrastructure changes should be coordinated before implementation.
