# CLC3

**Project Members**
- Christopher Nobis
- Daniel Hametner

## Project Status & Shared Context

### What has been implemented

The foundational cloud infrastructure has been fully set up using **Terraform** on Google Cloud Platform.

The following components are already provisioned and managed via Terraform:

- Google Cloud project and access (IAM)
- Terraform remote state stored in a private GCS bucket
- Required GCP APIs enabled (Cloud Run, Pub/Sub, Firestore, Artifact Registry)
- Firestore database (Native mode)
- Pub/Sub topic and subscription
- Dedicated service accounts with least-privilege permissions

No application services have been deployed yet.

---

### Shared facts (stable baseline)

The following values are considered **fixed** and should not be changed without coordination:

- **GCP Project:** `clc3-481608`
- **Region:** `europe-west3`
- **Firestore:** Native mode, default database
- **Pub/Sub topic:** `events-ingestion`
- **Pub/Sub subscription:** `events-worker-sub`

Infrastructure is managed exclusively via Terraform.  
Cloud resources should not be created manually in the GCP Console.

---

### What can be done next

From this point on, application development can start in parallel:

- Implement the **Cloud Run ingestion service**  
  (HTTP endpoint → publish events to Pub/Sub)
- Implement the **Cloud Run worker service**  
  (consume Pub/Sub messages → persist data in Firestore)
- Define the event payload structure and Firestore collections
- Decide and refine responsibilities as development progresses

Infrastructure changes should only be made if a new requirement emerges and should be coordinated first.
