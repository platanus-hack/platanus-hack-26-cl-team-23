# =============================================================================
# Variables
# =============================================================================

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, prod)"
  type        = string
  default     = "dev"
}

variable "initiative" {
  description = "Initiative name"
  type        = string
  default     = "platanus-hack-26"
}

variable "labels" {
  description = "Additional labels to apply to resources"
  type        = map(string)
  default     = {}
}

variable "cloud_run" {
  description = "Cloud Run service con memoria e instancias mínimas. La imagen se resuelve a digest."
  type = object({
    name                         = string
    artifact_registry_repository = string
    image_name                   = string
    image_tag                    = string
    cpu                          = optional(string, "1")
    memory                       = optional(string, "128Mi")
    min_instances                = optional(number, 0)
    max_instances                = optional(number, 1)
    env_variables                = optional(map(string), {})
  })
}

variable "app_engine" {
  description = "App Engine Standard con instancia y escalado mínimos (F1, 0–1 instancias)."
  type = object({
    location           = optional(string, "us-central")
    version_id         = optional(string, "v1")
    runtime            = optional(string, "python312")
    entrypoint         = optional(string, "granian --interface asgi --host 0.0.0.0 --port $PORT app.main:app")
    source_url         = string
    instance_class     = optional(string, "F1")
    min_idle_instances = optional(number, 0)
    max_idle_instances = optional(number, 1)
    env_variables      = optional(map(string), {})
  })
}
