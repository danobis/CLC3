resource "google_service_account" "ingestion" {
  account_id   = "ingestion-sa"
  display_name = "Cloud Run Ingestion Service Account"
  project      = var.project_id
}

resource "google_service_account" "worker" {
  account_id   = "worker-sa"
  display_name = "Cloud Run Worker Service Account"
  project      = var.project_id
}

resource "google_service_account" "dashboard" {
  account_id   = "dashboard-sa"
  display_name = "Cloud Run Dashboard Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "ingestion_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ingestion_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "worker_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "dashboard_firestore_viewer" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = "serviceAccount:${google_service_account.dashboard.email}"
}