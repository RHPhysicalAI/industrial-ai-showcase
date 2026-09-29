# This project was developed with assistance from AI tools.
"""Cluster-internal service URLs and pipeline defaults."""

S3_ENDPOINT = "http://seaweedfs.mlflow.svc:8333"
MLFLOW_TRACKING_URI = "https://mlflow.redhat-ods-applications.svc:8443"
MODEL_REGISTRY_ADDRESS = "http://wbc-model-registry.rhoai-model-registries.svc:8080"

PIPELINE_IMAGE = "image-registry.openshift-image-registry.svc:5000/vla-training/vla-training:latest"
GPU_LIMIT = 1
