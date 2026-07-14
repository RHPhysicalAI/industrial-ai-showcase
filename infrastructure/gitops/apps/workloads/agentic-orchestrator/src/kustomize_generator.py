# This project was developed with assistance from AI tools.
"""
Kustomize overlay generator for model promotions.
Converts agent requests into Git-committable YAML changes.

Agent-opens-PR pattern: Instead of calling KServe API directly,
agent generates Kustomize overlay and opens PR. Argo CD syncs on merge.
"""
from typing import Optional
from dataclasses import dataclass
import yaml


@dataclass
class ModelPromotion:
    """Model promotion request."""
    model_name: str
    model_version: str
    model_uri: str  # e.g., "s3://mlflow/models/vla-warehouse/v1.4"
    factory: str  # "factory-a" | "factory-b"
    runtime: str = "vllm"  # or "triton"
    namespace: Optional[str] = None  # defaults to factory name


class KustomizeGenerator:
    """Generate Kustomize overlays for model promotions."""

    def generate_overlay(self, promotion: ModelPromotion) -> dict[str, str]:
        """
        Generate Kustomize overlay files for model promotion.

        Creates two files:
        1. InferenceService patch (updates storageUri)
        2. kustomization.yaml (references the patch)

        Returns:
            Dict of {file_path: yaml_content}

        Example:
            >>> gen = KustomizeGenerator()
            >>> promotion = ModelPromotion(
            ...     model_name="vla-warehouse",
            ...     model_version="v1.4",
            ...     model_uri="s3://mlflow/models/vla-warehouse/v1.4",
            ...     factory="factory-a"
            ... )
            >>> overlay = gen.generate_overlay(promotion)
            >>> for path, content in overlay.items():
            ...     print(f"{path}:\\n{content}\\n")
        """
        # Use namespace (K8s-compliant, e.g., "factory-b") for both namespace field and paths
        # promotion.factory could be display name with spaces (e.g., "Factory B") - NEVER use it for paths
        namespace = promotion.namespace or promotion.factory
        base_path = f"infrastructure/gitops/apps/workloads/{namespace}"

        # Generate InferenceService (full resource, not patch)
        isvc = self._generate_isvc_patch(promotion, namespace)  # Reuse same structure

        # Generate kustomization.yaml
        kustomization = self._generate_kustomization(promotion, namespace)

        return {
            f"{base_path}/model-{promotion.model_name}-isvc.yaml": yaml.dump(
                isvc,
                default_flow_style=False,
                sort_keys=False
            ),
            f"{base_path}/kustomization.yaml": yaml.dump(
                kustomization,
                default_flow_style=False,
                sort_keys=False
            )
        }

    def _generate_isvc_patch(self, promotion: ModelPromotion, namespace: str) -> dict:
        """
        Generate InferenceService patch YAML.

        This is a strategic merge patch that updates only the storageUri field.
        """
        return {
            "apiVersion": "serving.kserve.io/v1beta1",
            "kind": "InferenceService",
            "metadata": {
                "name": promotion.model_name,
                "namespace": namespace
            },
            "spec": {
                "predictor": {
                    "model": {
                        "modelFormat": {"name": promotion.runtime},
                        "storageUri": promotion.model_uri,
                        "resources": {
                            "limits": {
                                "nvidia.com/gpu": "1",
                                "cpu": "4",
                                "memory": "16Gi"
                            },
                            "requests": {
                                "nvidia.com/gpu": "1",
                                "cpu": "2",
                                "memory": "8Gi"
                            }
                        }
                    }
                }
            }
        }

    def _generate_kustomization(self, promotion: ModelPromotion, namespace: str) -> dict:
        """
        Generate kustomization.yaml with InferenceService resource.

        For now, creates standalone InferenceService (not a patch).
        TODO: Once base vla-inference exists, switch to patch-based approach.
        """
        return {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": namespace,
            "resources": [
                f"model-{promotion.model_name}-isvc.yaml"
            ]
        }

    def generate_git_diff_preview(self, promotion: ModelPromotion) -> str:
        """
        Generate human-readable Git diff preview for HIL drawer.

        Shows what will be committed when PR is created.

        Returns:
            Git-style diff string
        """
        overlay = self.generate_overlay(promotion)

        diff_lines = ["```diff"]

        for path, content in overlay.items():
            diff_lines.append(f"--- /dev/null")
            diff_lines.append(f"+++ b/{path}")
            diff_lines.append("@@ -0,0 +1,{} @@".format(len(content.split("\n"))))

            for line in content.split("\n"):
                if line.strip():  # Skip empty lines for cleaner diff
                    diff_lines.append(f"+{line}")

        diff_lines.append("```")

        return "\n".join(diff_lines)

    def generate_summary(self, promotion: ModelPromotion) -> str:
        """
        Generate human-readable summary of promotion for HIL drawer.

        Returns:
            Markdown-formatted summary
        """
        return f"""## Model Promotion

- **Factory**: {promotion.factory}
- **Model**: {promotion.model_name}
- **New Version**: {promotion.model_version}
- **Model URI**: `{promotion.model_uri}`
- **Runtime**: {promotion.runtime}

### What will change

This promotion will update the InferenceService `{promotion.model_name}`
in namespace `{promotion.namespace or promotion.factory}` to serve the new model version.

### Impact

- **Deployment**: KServe will create new predictor pod with updated model
- **Rollout**: Zero-downtime (canary deployment via Knative)
- **Rollback**: Revert this PR if issues detected
"""


# Singleton
_generator = KustomizeGenerator()


def generate_model_promotion_overlay(
    model_name: str,
    model_version: str,
    model_uri: str,
    factory: str,
    runtime: str = "vllm",
    namespace: Optional[str] = None
) -> dict[str, str]:
    """
    Generate Kustomize overlay for model promotion.

    Convenience function that uses singleton generator.

    Args:
        model_name: Name of the model (e.g., "vla-warehouse")
        model_version: Version to promote (e.g., "v1.4")
        model_uri: S3/storage URI for model artifacts
        factory: Target factory ("factory-a" | "factory-b")
        runtime: Model runtime (default: "vllm")
        namespace: Target namespace (default: same as factory)

    Returns:
        Dict of {file_path: yaml_content}

    Example:
        >>> overlay = generate_model_promotion_overlay(
        ...     model_name="vla-warehouse",
        ...     model_version="v1.4",
        ...     model_uri="s3://mlflow/models/vla-warehouse/v1.4",
        ...     factory="factory-a"
        ... )
        >>> for path in overlay.keys():
        ...     print(path)
        infrastructure/gitops/apps/workloads/factory-a/model-vla-warehouse-patch.yaml
        infrastructure/gitops/apps/workloads/factory-a/kustomization.yaml
    """
    promotion = ModelPromotion(
        model_name=model_name,
        model_version=model_version,
        model_uri=model_uri,
        factory=factory,
        runtime=runtime,
        namespace=namespace
    )
    return _generator.generate_overlay(promotion)


def generate_promotion_git_diff(
    model_name: str,
    model_version: str,
    model_uri: str,
    factory: str,
    runtime: str = "vllm",
    namespace: Optional[str] = None
) -> str:
    """
    Generate Git diff preview for HIL drawer.

    Shows operator what will be committed to Git when PR is created.

    Args:
        Same as generate_model_promotion_overlay

    Returns:
        Git-style diff string (markdown formatted)
    """
    promotion = ModelPromotion(
        model_name=model_name,
        model_version=model_version,
        model_uri=model_uri,
        factory=factory,
        runtime=runtime,
        namespace=namespace
    )
    return _generator.generate_git_diff_preview(promotion)


def generate_promotion_summary(
    model_name: str,
    model_version: str,
    model_uri: str,
    factory: str,
    runtime: str = "vllm",
    namespace: Optional[str] = None
) -> str:
    """
    Generate human-readable summary for HIL drawer.

    Args:
        Same as generate_model_promotion_overlay

    Returns:
        Markdown-formatted summary
    """
    promotion = ModelPromotion(
        model_name=model_name,
        model_version=model_version,
        model_uri=model_uri,
        factory=factory,
        runtime=runtime,
        namespace=namespace
    )
    return _generator.generate_summary(promotion)
