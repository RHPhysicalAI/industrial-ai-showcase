# This project was developed with assistance from AI tools.
"""KFP v2 pipeline: fine-tune GR00T N1.7-3B VLA, export ONNX, validate, register."""

from kfp import dsl, kubernetes

from vla_training.constants import (
    GPU_LIMIT,
    MLFLOW_TRACKING_URI,
    MODEL_REGISTRY_ADDRESS,
    PIPELINE_IMAGE,
    S3_ENDPOINT,
)


def _configure_gpu_step(task: dsl.PipelineTask) -> None:
    task.set_accelerator_type("nvidia.com/gpu")
    task.set_accelerator_limit(GPU_LIMIT)
    task.set_cpu_request("6")
    task.set_memory_request("48Gi")
    task.set_memory_limit("56Gi")
    task.set_env_variable("PYTHONUNBUFFERED", "1")
    task.set_env_variable("S3_ENDPOINT", S3_ENDPOINT)
    task.set_env_variable("S3_BUCKET", "vla-training")
    task.set_env_variable("MLFLOW_TRACKING_URI", MLFLOW_TRACKING_URI)
    task.set_env_variable("MLFLOW_TRACKING_INSECURE_TLS", "true")
    task.set_env_variable("TRITON_CACHE_DIR", "/tmp/.triton")
    task.set_env_variable("HOME", "/tmp")
    kubernetes.empty_dir_mount(task, volume_name="dshm", mount_path="/dev/shm", medium="Memory", size_limit="16Gi")
    kubernetes.add_toleration(task, key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
    kubernetes.use_secret_as_env(
        task,
        secret_name="minio-credentials",
        secret_key_to_env={
            "MINIO_ROOT_USER": "AWS_ACCESS_KEY_ID",
            "MINIO_ROOT_PASSWORD": "AWS_SECRET_ACCESS_KEY",
        },
    )
    kubernetes.use_secret_as_env(
        task,
        secret_name="hf-credentials",
        secret_key_to_env={"HF_TOKEN": "HF_TOKEN"},
    )
    kubernetes.set_image_pull_policy(task, "Always")


def _configure_cpu_step(task: dsl.PipelineTask) -> None:
    task.set_cpu_request("2")
    task.set_memory_request("4Gi")
    task.set_env_variable("PYTHONUNBUFFERED", "1")
    task.set_env_variable("S3_ENDPOINT", S3_ENDPOINT)
    task.set_env_variable("S3_BUCKET", "vla-training")
    kubernetes.add_toleration(task, key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
    kubernetes.use_secret_as_env(
        task,
        secret_name="minio-credentials",
        secret_key_to_env={
            "MINIO_ROOT_USER": "AWS_ACCESS_KEY_ID",
            "MINIO_ROOT_PASSWORD": "AWS_SECRET_ACCESS_KEY",
        },
    )
    kubernetes.set_image_pull_policy(task, "Always")


@dsl.container_component
def vla_data_prep_op(
    base_model_repo: str,
    dataset_repo: str,
    s3_prefix: str,
    s3_prefix_out: dsl.OutputPath(str),
):
    """Download GR00T N1.7-3B base model and training dataset from HuggingFace, cache in S3."""
    return dsl.ContainerSpec(
        image=PIPELINE_IMAGE,
        command=["/bin/bash"],
        args=[
            "-c",
            "set -euo pipefail\n"
            'BASE_MODEL_REPO="$1"; DATASET_REPO="$2"; S3_PREFIX="$3"; OUTPUT_FILE="$4"\n'
            "\n"
            'echo "=== VLA Data Prep ==="\n'
            'echo "Base model: ${BASE_MODEL_REPO}"\n'
            'echo "Dataset: ${DATASET_REPO}"\n'
            'echo "S3 prefix: ${S3_PREFIX}"\n'
            'echo "Start time: $(date -u)"\n'
            "\n"
            'export VLA_BASE_MODEL_REPO="${BASE_MODEL_REPO}"\n'
            'export VLA_DATASET_REPO="${DATASET_REPO}"\n'
            'export VLA_S3_MODEL_PREFIX="${S3_PREFIX}/base-model"\n'
            'export VLA_S3_DATASET_PREFIX="${S3_PREFIX}/dataset"\n'
            "\n"
            "python -m vla_training.data_prep\n"
            "\n"
            'printf "%s" "${S3_PREFIX}" > "${OUTPUT_FILE}"\n'
            'echo "End time: $(date -u)"\n'
            'echo "=== VLA Data Prep: COMPLETE ==="',
            "--",
            base_model_repo,
            dataset_repo,
            s3_prefix,
            s3_prefix_out,
        ],
    )


@dsl.container_component
def vla_fine_tune_and_export_op(
    s3_prefix: str,
    embodiment_tag: str,
    max_steps: int,
    global_batch_size: int,
    num_gpus: int,
    onnx_s3_prefix: dsl.OutputPath(str),
):
    """Fine-tune GR00T N1.7-3B and export ONNX."""
    return dsl.ContainerSpec(
        image=PIPELINE_IMAGE,
        command=["/bin/bash"],
        args=[
            "-c",
            "set -euo pipefail\n"
            'S3_PREFIX="$1"; EMBODIMENT_TAG="$2"\n'
            'MAX_STEPS="$3"; BATCH_SIZE="$4"; NUM_GPUS="$5"; OUTPUT_FILE="$6"\n'
            "\n"
            'echo "=== VLA Fine-Tuning ==="\n'
            'echo "S3 prefix: ${S3_PREFIX}"\n'
            'echo "Embodiment: ${EMBODIMENT_TAG}"\n'
            'echo "GPUs: ${NUM_GPUS}"\n'
            'echo "Max steps: ${MAX_STEPS}"\n'
            'echo "Batch size: ${BATCH_SIZE}"\n'
            'echo "Start time: $(date -u)"\n'
            "\n"
            'export VLA_S3_MODEL_PREFIX="${S3_PREFIX}/base-model"\n'
            'export VLA_S3_DATASET_PREFIX="${S3_PREFIX}/dataset"\n'
            'export VLA_S3_CHECKPOINT_PREFIX="${S3_PREFIX}"\n'
            'export VLA_EMBODIMENT_TAG="${EMBODIMENT_TAG}"\n'
            'export DSPA_RUN_ID="${DSPA_RUN_ID:-unknown}"\n'
            "\n"
            "python -m vla_training.fine_tune \\\n"
            '  --max-steps "${MAX_STEPS}" \\\n'
            '  --global-batch-size "${BATCH_SIZE}" \\\n'
            '  --num-gpus "${NUM_GPUS}"\n'
            "\n"
            'printf "%s" "${S3_PREFIX}" > "${OUTPUT_FILE}"\n'
            'echo "End time: $(date -u)"\n'
            'echo "=== VLA Fine-Tuning: COMPLETE ==="',
            "--",
            s3_prefix,
            embodiment_tag,
            max_steps,
            global_batch_size,
            num_gpus,
            onnx_s3_prefix,
        ],
    )


@dsl.container_component
def vla_validate_onnx_op(
    s3_prefix: str,
    validation_result: dsl.OutputPath(str),
):
    """Validate VLA ONNX model: shapes, inference, determinism."""
    return dsl.ContainerSpec(
        image=PIPELINE_IMAGE,
        command=["/bin/bash"],
        args=[
            "-c",
            "set -euo pipefail\n"
            'S3_PREFIX="$1"; OUTPUT_FILE="$2"\n'
            "\n"
            'echo "=== VLA ONNX Validation ==="\n'
            'echo "S3 prefix: ${S3_PREFIX}"\n'
            'echo "Start time: $(date -u)"\n'
            "\n"
            "python -m vla_training.validate_onnx \\\n"
            '  --checkpoint-prefix "${S3_PREFIX}"\n'
            "\n"
            'echo "PASSED" > "${OUTPUT_FILE}"\n'
            'echo "End time: $(date -u)"\n'
            'echo "=== VLA ONNX Validation: COMPLETE ==="',
            "--",
            s3_prefix,
            validation_result,
        ],
    )


@dsl.container_component
def vla_register_model_op(
    model_name: str,
    model_version: str,
    s3_prefix: str,
    s3_bucket: str,
    base_model_repo: str,
    dataset_repo: str,
    embodiment_tag: str,
    max_steps: int,
    registration_result: dsl.OutputPath(str),
):
    """Register fine-tuned VLA ONNX model with RHOAI Model Registry."""
    return dsl.ContainerSpec(
        image=PIPELINE_IMAGE,
        command=["/bin/bash"],
        args=[
            "-c",
            "set -euo pipefail\n"
            'MODEL_NAME="$1"; MODEL_VERSION="$2"; S3_PREFIX="$3"\n'
            'S3_BUCKET="$4"; BASE_MODEL="$5"; DATASET="$6"\n'
            'EMBODIMENT="$7"; STEPS="$8"; OUTPUT_FILE="$9"\n'
            'MODEL_URI="s3://${S3_BUCKET}/${S3_PREFIX}/onnx"\n'
            "\n"
            'export VLA_BASE_MODEL_REPO="${BASE_MODEL}"\n'
            'export VLA_DATASET_REPO="${DATASET}"\n'
            'export VLA_EMBODIMENT_TAG="${EMBODIMENT}"\n'
            'export VLA_MAX_STEPS="${STEPS}"\n'
            'export VLA_S3_CHECKPOINT_PREFIX="${S3_PREFIX}"\n'
            'export DSPA_RUN_ID="${DSPA_RUN_ID:-unknown}"\n'
            "\n"
            'echo "=== VLA Model Registration ==="\n'
            'echo "Model: ${MODEL_NAME} v${MODEL_VERSION}"\n'
            'echo "URI: ${MODEL_URI}"\n'
            'echo "Start time: $(date -u)"\n'
            "\n"
            "python -m vla_training.register_model \\\n"
            '  --name "${MODEL_NAME}" \\\n'
            '  --uri "${MODEL_URI}" \\\n'
            '  --version "${MODEL_VERSION}" \\\n'
            '  --description "GR00T N1.7-3B fine-tuned VLA for G1 teleop"\n'
            "\n"
            'echo "REGISTERED" > "${OUTPUT_FILE}"\n'
            'echo "End time: $(date -u)"\n'
            'echo "=== VLA Model Registration: COMPLETE ==="',
            "--",
            model_name,
            model_version,
            s3_prefix,
            s3_bucket,
            base_model_repo,
            dataset_repo,
            embodiment_tag,
            max_steps,
            registration_result,
        ],
    )


@dsl.pipeline(
    name="vla-finetune",
    description="GR00T N1.7-3B VLA fine-tuning for G1 teleop",
)
def vla_finetune_pipeline(
    base_model_repo: str = "nvidia/GR00T-N1.7-3B",
    dataset_repo: str = "nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1",
    embodiment_tag: str = "UNITREE_G1",
    max_steps: int = 2000,
    global_batch_size: int = 64,
    num_gpus: int = GPU_LIMIT,
    s3_prefix: str = "vla-finetune",
    s3_bucket: str = "vla-training",
    model_name: str = "g1-vla-finetune",
    model_version: str = "v1",
):
    versioned_prefix = f"{s3_prefix}/{model_version}"

    data_prep_task = vla_data_prep_op(
        base_model_repo=base_model_repo,
        dataset_repo=dataset_repo,
        s3_prefix=versioned_prefix,
    )
    _configure_cpu_step(data_prep_task)
    data_prep_task.set_cpu_request("4")
    data_prep_task.set_memory_request("16Gi")
    kubernetes.use_secret_as_env(
        data_prep_task,
        secret_name="hf-credentials",
        secret_key_to_env={"HF_TOKEN": "HF_TOKEN"},
    )
    data_prep_task.set_caching_options(False)

    fine_tune_task = vla_fine_tune_and_export_op(
        s3_prefix=data_prep_task.outputs["s3_prefix_out"],
        embodiment_tag=embodiment_tag,
        max_steps=max_steps,
        global_batch_size=global_batch_size,
        num_gpus=num_gpus,
    )
    _configure_gpu_step(fine_tune_task)
    kubernetes.set_timeout(fine_tune_task, 7200)
    fine_tune_task.set_caching_options(False)

    validate_task = vla_validate_onnx_op(
        s3_prefix=fine_tune_task.outputs["onnx_s3_prefix"],
    )
    _configure_cpu_step(validate_task)
    kubernetes.set_timeout(validate_task, 1800)
    validate_task.set_caching_options(False)

    register_task = vla_register_model_op(
        model_name=model_name,
        model_version=model_version,
        s3_prefix=fine_tune_task.outputs["onnx_s3_prefix"],
        s3_bucket=s3_bucket,
        base_model_repo=base_model_repo,
        dataset_repo=dataset_repo,
        embodiment_tag=embodiment_tag,
        max_steps=max_steps,
    )
    register_task.after(validate_task)
    _configure_cpu_step(register_task)
    register_task.set_cpu_request("1")
    register_task.set_memory_request("2Gi")
    register_task.set_env_variable("MODEL_REGISTRY_ADDRESS", MODEL_REGISTRY_ADDRESS)
    kubernetes.set_timeout(register_task, 600)
    register_task.set_caching_options(False)


if __name__ == "__main__":
    import sys

    from kfp import compiler

    output = sys.argv[1] if len(sys.argv) > 1 else "vla_finetune_pipeline.yaml"
    compiler.Compiler().compile(vla_finetune_pipeline, output)
    print(f"Pipeline compiled to {output}")
