# =============================================================================
# Main Configuration — Cloud Run + App Engine (mínimo)
# =============================================================================

data "external" "image_info" {
  program = ["bash", "-c", <<-EOT
    set -euo pipefail

    IMAGE_BASE="${var.region}-docker.pkg.dev/${var.project_id}/${var.cloud_run.artifact_registry_repository}/${var.cloud_run.image_name}"
    IMAGE_TAG="${var.cloud_run.image_tag}"

    # Fail closed: never fall back to a mutable tag reference
    if ! ALL_TAGS_OUTPUT=$(gcloud artifacts docker tags list "$IMAGE_BASE" \
      --format="value(tag,version)" 2>&1); then
      echo "ERROR: cannot list tags for $IMAGE_BASE: $ALL_TAGS_OUTPUT" >&2
      exit 1
    fi

    # Digest of the exact target tag (e.g., 'latest')
    DIGEST=$(echo "$ALL_TAGS_OUTPUT" \
      | awk -v t="$IMAGE_TAG" '
          {
            n = split($1, a, "/");
            last = a[n];
            if (last == t || last ~ (":" t "$")) { print $2; exit }
          }' \
      | grep -Eo 'sha256:[0-9a-f]{64}' | head -n 1 || true)

    if [ -z "$DIGEST" ]; then
      echo "ERROR: tag '$IMAGE_TAG' of $IMAGE_BASE did not resolve to a valid sha256 digest" >&2
      exit 1
    fi

    # Find another tag sharing the digest (e.g., the commit SHA tag)
    COMMIT_TAG=$(echo "$ALL_TAGS_OUTPUT" \
      | awk -v d="$DIGEST" -v t="$IMAGE_TAG" '
          index($2, d) {
            n = split($1, a, "/");
            last = a[n];
            sub(/^.*:/, "", last);
            if (last != t) { print last; exit }
          }' || true)

    if [ -n "$COMMIT_TAG" ]; then
      FINAL_TAG="$COMMIT_TAG"
    else
      FINAL_TAG="$IMAGE_TAG"
    fi

    IMAGE_REF="$IMAGE_BASE@$DIGEST"

    echo "{\"image\":\"$IMAGE_REF\",\"commit_tag\":\"$FINAL_TAG\",\"digest\":\"$DIGEST\"}"
  EOT
  ]
}

resource "google_cloud_run_v2_service" "orchestrator" {
  name     = var.cloud_run.name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = var.labels

  template {
    containers {
      image = data.external.image_info.result.image

      resources {
        limits = {
          cpu    = var.cloud_run.cpu
          memory = var.cloud_run.memory
        }
      }

      dynamic "env" {
        for_each = var.cloud_run.env_variables
        content {
          name  = env.key
          value = env.value
        }
      }
    }

    scaling {
      min_instance_count = var.cloud_run.min_instances
      max_instance_count = var.cloud_run.max_instances
    }
  }
}

resource "google_app_engine_application" "app" {
  project     = var.project_id
  location_id = var.app_engine.location
}

resource "google_app_engine_standard_app_version" "orchestrator" {
  project        = var.project_id
  service        = "default"
  version_id     = var.app_engine.version_id
  runtime        = var.app_engine.runtime
  instance_class = var.app_engine.instance_class

  entrypoint {
    shell = var.app_engine.entrypoint
  }

  deployment {
    zip {
      source_url = var.app_engine.source_url
    }
  }

  automatic_scaling {
    min_idle_instances = var.app_engine.min_idle_instances
    max_idle_instances = var.app_engine.max_idle_instances
  }

  env_variables = var.app_engine.env_variables

  depends_on = [google_app_engine_application.app]
}
