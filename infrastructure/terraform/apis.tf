resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com"
  ])

  service = each.value

  disable_on_destroy = false
}

resource "google_project_service" "cloudscheduler" {
  project            = var.project_id
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}



