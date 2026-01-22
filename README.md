# CLC3

**Project Members**
- Christopher Nobis
- Daniel Hametner

---

## Project Status & Shared Context

### What has been implemented

<img width="8191" height="993" alt="mermaid-ai-diagram-2026-01-11-165116" src="https://github.com/user-attachments/assets/3510725d-0bc7-436e-ad59-9b0d20db5f69" />

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
- Cloud Run dashboard UI service (visualization and demo)

The system has been tested end-to-end and is fully functional.

---

### Architecture Overview

- **Ingestion Service (Cloud Run)**  
  Public HTTP endpoint that accepts events and publishes them to Pub/Sub.

- **Message Broker (Pub/Sub)**  
  Decouples ingestion from processing and delivers events asynchronously.

- **Worker Service (Cloud Run)**  
  Consumes Pub/Sub push messages, processes events, persists them in Firestore, and updates distributed statistics.

- **Storage (Firestore)**  
  Stores processed event documents and aggregated statistical data using NoSQL patterns.

---

### Dashboard UI (Visualization & Demo)

A lightweight **Dashboard UI** is deployed as an additional Cloud Run service to visualize and demonstrate the system end-to-end.

**Purpose:**
- Provide a clear, human-readable view of the system state
- Support live demos without using the GCP Console
- Make the event-driven architecture and scalability behavior tangible

**Features:**
- Displays the latest events stored in Firestore (`events` collection)
- Shows event metadata (eventId, type, timestamps, payload)
- Allows publishing test events via the ingestion service
- Includes a “Turbo” mode to generate burst traffic
- Enables inspection of system behavior under load
- Optionally embeds the architecture diagram for reference

**Architecture role:**
- Implemented as a separate Cloud Run service (`dashboard-ui`)
- Reads Firestore data using a read-only service account
- Publishes test events by calling the public ingestion endpoint
- Does not participate in the core data pipeline

The dashboard is intended for demonstration and inspection purposes only and does not affect production data flow.

---

### Shared facts (stable baseline)

The following values are considered **fixed** and should not be changed without coordination:

- **GCP Project:** `clc3-481608`
- **Region:** `europe-west3`
- **Firestore:** Native mode, default database
- **Firestore collections:** `events`, `stats`
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
5. Statistical counters are updated using a sharded NoSQL pattern

Firestore event documents include:
- Event payload
- Ingestion timestamp
- Processing timestamp
- Pub/Sub metadata (message ID, publish time, attributes)

---

### Scalability: Sharded Counter (NoSQL Design)

To demonstrate **NoSQL scalability and hotspot avoidance**, the worker service implements a **sharded counter** for tracking the number of processed events per minute.

**Motivation:**
- A single counter document would become a write hotspot under high load
- Firestore performs best when writes are distributed across multiple documents

**Implementation:**
- For each processed event, the worker selects a **random shard** (0–19)
- Only the selected shard document is incremented
- The total number of events per minute is the **sum of all shard counts**

**Firestore Structure (stats collection):**

```text
stats (collection)
└── {YYYYMMDDHHMM} (document: time bucket per minute)
    └── shards (subcollection)
        ├── 0 (shard document)
        │   └── count: <int>
        ├── 1 (shard document)
        │   └── count: <int>
        ├── ...
        └── 19 (shard document)
            └── count: <int>
```

This approach distributes write load and allows the system to scale under burst traffic (e.g., Turbo mode).

---

### Reliability: Dead-Letter Queue (DLQ)

The worker subscription is configured with a dead-letter topic (`events-dlq`).

- Messages that fail processing repeatedly are retried automatically
- After the maximum number of delivery attempts, messages are routed to the DLQ
- This mechanism demonstrates fault tolerance and failure isolation in an event-driven system

---

### Reliability: Idempotent Processing

The worker service implements idempotent processing based on `eventId`.

- Before writing to Firestore, the worker checks whether the event already exists
- Duplicate deliveries caused by retries are safely ignored

This ensures correct behavior under Pub/Sub’s at-least-once delivery semantics.

---

### Project Type

**Type A – Architectural Design Prototype**

- Fully functional serverless system
- Automated infrastructure provisioning using Terraform
- Live demonstration via Dashboard UI
- Focus on scalability, reliability, and NoSQL design principles
