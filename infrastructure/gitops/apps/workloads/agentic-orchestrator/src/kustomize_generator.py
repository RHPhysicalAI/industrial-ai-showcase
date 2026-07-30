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

        Creates only policy-version ConfigMap (updates version displayed in UI).
        The actual VLA model deployment (openvla-server) is already deployed
        and doesn't need to be regenerated on version changes.

        Returns:
            Dict of {file_path: yaml_content}

        Example:
            >>> gen = KustomizeGenerator()
            >>> promotion = ModelPromotion(
            ...     model_name="vla-warehouse",
            ...     model_version="v1.4",
            ...     model_uri="hf://openvla/openvla-7b",
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

        # Generate policy-version ConfigMap (for UI display)
        policy_configmap = self._generate_policy_version_configmap(promotion, namespace)

        return {
            f"{base_path}/policy-version.yaml": yaml.dump(
                policy_configmap,
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

    def _generate_policy_version_configmap(self, promotion: ModelPromotion, namespace: str) -> dict:
        """
        Generate policy-version ConfigMap YAML.

        This ConfigMap is read by the console backend to display the current
        policy version in the Fleet view UI.
        """
        from datetime import datetime, timezone

        # Format version as "model-name-version" (e.g., "vla-warehouse-v1.4")
        policy_version = f"{promotion.model_name}-{promotion.model_version}"

        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "policy-version",
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/part-of": namespace,
                    "showcase.redhat.com/component": "policy-version"
                }
            },
            "data": {
                "version": policy_version,
                "model-uri": promotion.model_uri,
                "promoted-at": datetime.now(timezone.utc).isoformat()
            }
        }

    def _generate_kustomization(self, promotion: ModelPromotion, namespace: str) -> dict:
        """
        NOTE: Not used anymore. Policy-version ConfigMap is already in kustomization.yaml.
        Keeping this method for backward compatibility but it's not called.
        """
        return {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": namespace,
            "resources": [
                "policy-version.yaml"
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

### What will change

This promotion will update the policy-version ConfigMap in namespace `{promotion.namespace or promotion.factory}`.
The VLA model (`openvla-server`) is already deployed and serving `{promotion.model_uri}`.

### Impact

- **UI Display**: Console will show updated version ({promotion.model_version})
- **Deployment**: No pod restarts (VLA server already running)
- **Rollback**: Revert this PR if needed
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
