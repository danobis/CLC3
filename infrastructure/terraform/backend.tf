terraform {
  backend "gcs" {
    bucket = "clc3-terraform-state-2410454025"
    prefix = "serverless-event-ingestion"
  }
}
