resource "google_pubsub_topic" "events" {
  name    = "events-ingestion"
  project = var.project_id
}

resource "google_pubsub_topic" "events_dlq" {
  name    = "events-dlq"
  project = var.project_id
}

resource "google_pubsub_subscription" "events_dlq_sub" {
  name    = "events-dlq-sub"
  topic   = google_pubsub_topic.events_dlq.name
  project = var.project_id
}

resource "google_pubsub_subscription" "events_worker" {
  name    = "events-worker-sub"
  topic   = google_pubsub_topic.events.name
  project = var.project_id

  ack_deadline_seconds = 20

  push_config {
    push_endpoint = "https://worker-863930563168.europe-west3.run.app/pubsub"

    oidc_token {
      service_account_email = google_service_account.worker.email
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.events_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.events_dlq.id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
