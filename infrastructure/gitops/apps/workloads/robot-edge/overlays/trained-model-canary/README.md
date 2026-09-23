# Trained-model GitOps canary

This isolated overlay verifies the fork-owned GitOps serving contract for a
registered GR00T artifact without changing the live `openvla-server` or the
AWS VLA VM.

It deliberately lives below the existing `robot-edge` workload directory so
the current workload ApplicationSet does not discover it automatically. One
of the standalone Argo Applications must be applied explicitly for the test:
the upstream-profile
`tools/vla-training/robot-edge-canary-application.yaml` (after the canary is
merged upstream) or the fork-profile
`tools/vla-training/robot-edge-canary-application-rhkp.yaml` while testing this
fork.

The overlay expects these pre-existing or temporary namespace resources:

- `robot-edge/storage-config` for the Hub MinIO credentials;
- `robot-edge/model-cache` for the model cache;
- `robot-edge/hf-token-stage1-20260923` with key `token`, created temporarily
  from the approved Hugging Face credential and deleted after the canary.

The model URI, model version, GR00T embodiment/video contract, and immutable
fork image digest are declared in the overlay so Argo CD can show and track
the exact canary inputs.
