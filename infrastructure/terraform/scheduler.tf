resource "google_cloud_scheduler_job" "demo_event_generator" {
  name        = "demo-event-generator"
  description = "Generates demo events by calling ingestion-api /events"
  project     = var.project_id
  region      = var.region

  schedule  = var.scheduler_cron
  time_zone = "Europe/Vienna"

  http_target {
    http_method = "POST"
    uri         = "${trim(var.ingestion_url, "/")}/events"

    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode(jsonencode({
      eventType = "scheduled.ping"
      source    = "cloud-scheduler"
      payload   = {
        note      = "automatic demo traffic"
        project   = var.project_id
        generated = "true"
      }
    }))
  }

  depends_on = [
    google_project_service.cloudscheduler
  ]
}
