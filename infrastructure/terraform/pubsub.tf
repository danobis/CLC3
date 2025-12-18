resource "google_pubsub_topic" "events" {
  name    = "events-ingestion"
  project = var.project_id
}

resource "google_pubsub_subscription" "events_worker" {
  name    = "events-worker-sub"
  topic   = google_pubsub_topic.events.name
  project = var.project_id

  ack_deadline_seconds = 20
}