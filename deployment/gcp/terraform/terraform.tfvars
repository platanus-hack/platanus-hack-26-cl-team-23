# =============================================================================
# Environment Configuration (mínimos)
# =============================================================================

project_id  = "your-project-id"
region      = "us-central1"
environment = "dev"
initiative  = "platanus-hack-26"

labels = {
  environment = "dev"
  initiative  = "platanus-hack-26"
}

cloud_run = {
  name                         = "orchestrator"
  artifact_registry_repository = "platanus-hack-26-repo"
  image_name                   = "orchestrator"
  image_tag                    = "latest"
  cpu                          = "1"
  memory                       = "128Mi"
  min_instances                = 0
  max_instances                = 1

  env_variables = {
    APP_ENV      = "dev"
    APP_HOST     = "0.0.0.0"
    APP_PORT     = "8080"
    HTTP_TIMEOUT = "40"
  }
}

app_engine = {
  location           = "us-central"
  version_id         = "v1"
  runtime            = "python312"
  entrypoint         = "granian --interface asgi --host 0.0.0.0 --port $PORT app.main:app"
  source_url         = "gs://your-app-engine-source/orchestrator.zip"
  instance_class     = "F1"
  min_idle_instances = 0
  max_idle_instances = 1

  env_variables = {
    APP_ENV      = "dev"
    APP_HOST     = "0.0.0.0"
    APP_PORT     = "8080"
    HTTP_TIMEOUT = "40"
  }
}
