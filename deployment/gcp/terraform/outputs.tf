# =============================================================================
# Outputs
# =============================================================================

output "cloud_run_url" {
  description = "URL pública del Cloud Run service."
  value       = google_cloud_run_v2_service.orchestrator.uri
}

output "cloud_run_image" {
  description = "Imagen resuelta a digest y tag de commit."
  value       = data.external.image_info.result
}

output "app_engine_default_hostname" {
  description = "Hostname por defecto de App Engine."
  value       = google_app_engine_application.app.default_hostname
}

output "app_engine_version" {
  description = "Versión desplegada en App Engine."
  value       = google_app_engine_standard_app_version.orchestrator.version_id
}
