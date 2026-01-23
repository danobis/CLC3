# Artifact Registry Repository für die Images (optional, falls du saubere Builds willst)
resource "google_artifact_registry_repository" "services" {
  location      = var.region
  repository_id = "clc3-services"
  description   = "Docker repository for CLC3 services"
  format        = "DOCKER"
}

# ------------------------------------------------------------------------------
# 1. Ingestion API Service
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "ingestion_api" {
  name     = "ingestion-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.ingestion.email

    containers {
      # ERSETZEN: Hier muss die volle Image-URL rein.
      # Wenn du gcloud deploy genutzt hast, schau in die Cloud Console nach der URL.
      # Beispiel: "${var.region}-docker.pkg.dev/${var.project_id}/cloud-run-source-deploy/ingestion-api:latest"
      image = "europe-west3-docker.pkg.dev/clc3-481608/clc3-services/ingestion-api@sha256:ee9b37a8e37e4dcba886e411fd55e3e1f485e7f813c52a67af19c26575e7e753"

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "TOPIC_NAME"
        value = google_pubsub_topic.events.name
      }
    }
  }
}

# IAM: Allow unauthenticated access for Ingestion API
resource "google_cloud_run_service_iam_member" "ingestion_noauth" {
  location = google_cloud_run_v2_service.ingestion_api.location
  service  = google_cloud_run_v2_service.ingestion_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ------------------------------------------------------------------------------
# 2. Worker Service
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "worker" {
  name     = "worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" # Oder ALL, wenn du ihn testen willst

  template {
    service_account = google_service_account.worker.email

    containers {
      # ERSETZEN: Volle Image URL
      image = "europe-west3-docker.pkg.dev/clc3-481608/clc3-services/worker@sha256:8093446ebc386972d57469c4f9cd7436330bc0ad0fe8c88975fe562823fb2de6"

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIRESTORE_COLLECTION"
        value = "events"
      }
    }
  }
}

# IAM: Worker darf nicht öffentlich sein (no-allow-unauthenticated ist default bei Terraform wenn keine IAM policy gesetzt ist)
# Wir brauchen aber die Pub/Sub Subscription, die den Worker aufrufen darf.
# Das passiert über den Service Account, der den Push macht.
# Siehe pubsub.tf -> push_config -> oidc_token

resource "google_cloud_run_service_iam_member" "worker_invoker" {
  location = google_cloud_run_v2_service.worker.location
  service  = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.worker.email}" # Der Worker ruft sich selbst via PubSub auf? Prüfe den SA in pubsub.tf
}


# ------------------------------------------------------------------------------
# 3. Dashboard UI Service
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "dashboard_ui" {
  name     = "dashboard-ui"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.dashboard.email # Diesen SA müssen wir noch in iam.tf anlegen!

    containers {
      # ERSETZEN: Volle Image URL
      image = "europe-west3-docker.pkg.dev/clc3-481608/clc3-services/dashboard-ui@sha256:4d4f5fb991fec7e7404978449045e3f9bfd71690eb837f37047f26f2646cf706"

      ports {
        container_port = 8080
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIRESTORE_COLLECTION"
        value = "events"
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "INGESTION_URL"
        value = google_cloud_run_v2_service.ingestion_api.uri
      }
    }
  }
}

# IAM: Allow unauthenticated access for Dashboard UI
resource "google_cloud_run_service_iam_member" "dashboard_noauth" {
  location = google_cloud_run_v2_service.dashboard_ui.location
  service  = google_cloud_run_v2_service.dashboard_ui.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
