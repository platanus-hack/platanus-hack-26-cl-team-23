# =============================================================================
# Terraform Backend Configuration
# =============================================================================

terraform {
  backend "gcs" {
    bucket = "platanus-26"
    prefix = "apps/state"
  }
}