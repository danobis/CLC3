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
      image = "europe-west3-docker.pkg.dev/clc3-481608/cloud-run-source-deploy/ingestion-api@sha256:bb21f3e8f2a7aa7fb9cd846bcd2221774075dcd6445c540cbf27def1b38d589a"

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
      image = "europe-west3-docker.pkg.dev/clc3-481608/cloud-run-source-deploy/worker@sha256:fa3624534bf0c32ff71ef0ddcc9b2bd424a66f26239f6f0ed78aa4f82a5d403d"

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
      image = "europe-west3-docker.pkg.dev/clc3-481608/cloud-run-source-deploy/dashboard-ui@sha256:7c969f56a2ccd4e5734fd0b79218875300bf545c1e90235c5d16802f25402f18"

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
