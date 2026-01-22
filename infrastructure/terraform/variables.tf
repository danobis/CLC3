variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west3"
}

variable "ingestion_url" {
  description = "Public URL of ingestion service, e.g. https://ingestion-api-...run.app"
  type        = string
}

variable "scheduler_cron" {
  description = "Cron schedule for demo events"
  type        = string
  default     = "*/1 * * * *" # jede Minute
}
