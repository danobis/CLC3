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

<img width="5220" height="2480" alt="dashboard-ui" src="https://github.com/user-attachments/assets/34acc9e3-2a5c-4989-9e77-319ae7d6426f" />


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

### Load Generator (Traffic Simulation)

A dedicated **Load Generator** service (`services/generator`) is included to simulate realistic production traffic and verify system stability.

<img width="5226" height="2486" alt="Screenshot From 2026-01-23 16-01-46" src="https://github.com/user-attachments/assets/20192d4a-2725-4bff-847c-7f8536bfdb5c" />

**Key Capabilities:**
- **Synthetic Data:** Generates randomized e-commerce order payloads using `Faker`.
- **Chaos Injection:** Intentionally sends "fail" event types (approx. 10%) to trigger and verify the Dead-Letter Queue (DLQ) logic.
- **Parallel Execution:** Uses multi-threading to simulate concurrent clients.

**Impact on Load Balancing:**
The generator is designed to thoroughly test the infrastructure efficiency:
- **Connection Pooling:** It reuses TCP connections (Keep-Alive). This forces the Cloud Load Balancer to distribute traffic based on HTTP requests (Layer 7) rather than just connection availability, ensuring a robust test of the ingress capabilities without the overhead of establishing new handshakes for every request.
- **Sustained Load:** By maintaining a steady stream of concurrent requests (4 worker threads), it challenges the Cloud Run autoscaler to provision instances dynamically based on the request concurrency metric.

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
└── events_per_minute (document)
    └── {YYYYMMDDHHMM} (collection: time bucket per minute)
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

### Security Architecture

The system implements a **Defense-in-Depth** strategy using GCP IAM and Network Security:

- **Public Zone:**
  - `Ingestion API` and `Dashboard UI` are publicly accessible (`roles/run.invoker` granted to `allUsers`).
  - They serve as the controlled entry points into the system.

- **Private Zone:**
  - The `Worker Service` is **not publicly accessible**.
  - It is configured to only accept traffic from authenticated internal sources (specifically the Pub/Sub push subscription).
  - Authentication relies on OIDC tokens generated by the Pub/Sub service account, ensuring that only valid messages from the topic can trigger the worker.

- **Least Privilege:**
  - Each service runs with its own dedicated Service Account.
  - The Ingestion service can *only* publish to Pub/Sub (no database write access).
  - The Worker service can write to Firestore but cannot serve public web traffic.

---

### Project Type

**Type A – Architectural Design Prototype**

- Fully functional serverless system
- Automated infrastructure provisioning using Terraform
- Live demonstration via Dashboard UI
- Focus on scalability, reliability, and NoSQL design principles
