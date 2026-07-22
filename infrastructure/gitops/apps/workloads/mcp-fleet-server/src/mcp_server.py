# This project was developed with assistance from AI tools.
"""
MCP server for Fleet Manager operations.
Exposes read-only and state-modifying fleet tools.

Key architectural pattern: promote_policy_version DOES NOT call cluster API.
Instead, it generates Kustomize overlay and opens PR. Argo CD syncs on merge.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import httpx
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../agentic-orchestrator/src'))

from github_client import get_github_client
from kustomize_generator import (
    generate_model_promotion_overlay,
    generate_promotion_git_diff,
    generate_promotion_summary
)

app = FastAPI(
    title="MCP Fleet Server",
    description="Fleet Manager MCP tools for agentic operations",
    version="0.1.0"
)

# Environment
FLEET_MANAGER_URL = os.getenv("FLEET_MANAGER_URL", "http://fleet-manager.fleet-ops.svc.cluster.local:8080")
CONSOLE_BACKEND_URL = os.getenv("CONSOLE_BACKEND_URL", "http://showcase-console-backend.fleet-ops.svc.cluster.local:8090")
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "phase3")  # Target branch for PRs (phase3 during development, main for production)

# Showcase mode: use HF models instead of MLflow/MinIO
# Set SHOWCASE_MODE=false for production deployments with real training pipeline
SHOWCASE_MODE = os.getenv("SHOWCASE_MODE", "true").lower() == "true"

# HF model version mapping for showcase mode
# Maps version strings to HF model URIs (using ungated models that don't require auth)
HF_MODEL_VERSIONS = {
    "v1.4": "hf://Qwen/Qwen2.5-3B-Instruct",
    "v1.5": "hf://Qwen/Qwen2.5-7B-Instruct",
    "v1.6": "hf://microsoft/Phi-3.5-mini-instruct",
}


# ========== READ-ONLY TOOLS ==========

@app.get("/tools/get_fleet_status")
async def get_fleet_status(factory: Optional[str] = None):
    """
    Get current fleet status (read-only).

    Args:
        factory: Filter by factory (optional)

    Returns:
        Fleet status summary

    Example:
        GET /tools/get_fleet_status?factory=factory-a
        →
        {
          "factories": [{
            "name": "Factory A",
            "namespace": "robot-edge",
            "policyVersion": "vla-warehouse-v1.3",
            "robotId": "fl-07",
            "robotStatus": "active",
            "anomalyScore": 0.12
          }]
        }
    """
    try:
        # Call console backend (which has Fleet Manager integration)
        client = httpx.Client(timeout=10.0)
        resp = client.get(f"{CONSOLE_BACKEND_URL}/api/fleet")
        resp.raise_for_status()

        fleet_data = resp.json()

        # Filter by factory if specified
        if factory:
            factories = [
                f for f in fleet_data.get("factories", [])
                if f.get("name", "").lower() == factory.lower()
                or f.get("namespace", "") == factory
            ]
            return {"factories": factories}

        return fleet_data

    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Fleet Manager unavailable: {str(e)}")


@app.get("/tools/get_factory_config")
async def get_factory_config(factory: str):
    """
    Get factory configuration (read-only).

    Args:
        factory: Factory name ("factory-a" | "Factory A" | "robot-edge")

    Returns:
        Factory config (robots, policy version, safety zones, etc.)

    Example:
        GET /tools/get_factory_config?factory=factory-a
        →
        {
          "name": "Factory A",
          "namespace": "robot-edge",
          "policy_version": "vla-warehouse-v1.3",
          "robots": ["fl-07", "fl-08", "fl-09"],
          "robot_count": 3,
          "max_speed": 2.0,
          "safety_zones": ["loading-dock", "aisle-1", "aisle-2", "aisle-3"]
        }
    """
    # Normalize factory name
    factory_lower = factory.lower()

    # Map common aliases to canonical names
    factory_map = {
        "factory-a": "factory-a",
        "factory a": "factory-a",
        "robot-edge": "factory-a",
        "factory-b": "factory-b",
        "factory b": "factory-b"
    }

    canonical_factory = factory_map.get(factory_lower)

    # Get current factory status from fleet API
    try:
        status_data = await get_fleet_status(factory=factory)
        factories = status_data.get("factories", [])

        if not factories:
            raise HTTPException(status_code=404, detail=f"Factory {factory} not found")

        # Use first match
        factory_status = factories[0]

        # Enrich with static config
        config = {
            "name": factory_status.get("name"),
            "namespace": factory_status.get("namespace"),
            "policy_version": factory_status.get("policyVersion"),
            "robot_id": factory_status.get("robotId"),
            "robot_status": factory_status.get("robotStatus"),
            "anomaly_score": factory_status.get("anomalyScore"),
            "last_heartbeat": factory_status.get("lastHeartbeat")
        }

        # Add static factory-specific config
        if canonical_factory == "factory-a":
            config.update({
                "robots": ["fl-07", "fl-08", "fl-09"],
                "robot_count": 3,
                "max_speed": 2.0,
                "safety_zones": ["loading-dock", "aisle-1", "aisle-2", "aisle-3"]
            })
        elif canonical_factory == "factory-b":
            config.update({
                "robots": ["fl-10", "fl-11"],
                "robot_count": 2,
                "max_speed": 1.5,
                "safety_zones": ["warehouse-north", "warehouse-south"]
            })

        return config

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools/get_robot_telemetry")
async def get_robot_telemetry(robot_id: str, hours: int = 24):
    """
    Get robot telemetry (read-only).

    Args:
        robot_id: Robot ID (e.g., "fl-07")
        hours: Hours of history (default: 24)

    Returns:
        Telemetry data (mock for now)
    """
    # Mock implementation
    # In real implementation, would query Kafka or telemetry database
    return {
        "robot_id": robot_id,
        "hours": hours,
        "telemetry": {
            "uptime_hours": 23.5,
            "missions_completed": 47,
            "average_mission_duration_sec": 180,
            "errors": 0,
            "battery_level_pct": 85,
            "current_location": "aisle-2"
        }
    }


@app.get("/tools/get_anomaly_history")
async def get_anomaly_history(factory: str, hours: int = 24):
    """
    Get anomaly detection history (read-only).

    Args:
        factory: Factory name
        hours: Hours of history (default: 24)

    Returns:
        Anomaly history
    """
    # Mock implementation
    # In real implementation, would query anomaly detection service
    return {
        "factory": factory,
        "hours": hours,
        "anomalies": [],
        "total_count": 0,
        "max_score": 0.0
    }


# ========== STATE-MODIFYING TOOLS ==========

@app.post("/tools/promote_policy_version")
async def promote_policy_version(factory: str, model_version: str):
    """
    Promote model policy version to factory (state-modifying).

    **CRITICAL**: This tool DOES NOT call the cluster API directly.
    Instead, it:
    1. Generates Kustomize overlay
    2. Opens PR to infrastructure/gitops/
    3. Returns PR URL
    4. Argo CD will sync on PR merge

    This is the agent-opens-PR pattern: every state change flows through Git.

    Args:
        factory: Factory name ("factory-a" | "factory-b")
        model_version: Model version to promote (e.g., "v1.4")

    Returns:
        PR details (URL, number, branch, summary)

    Example:
        POST /tools/promote_policy_version
        {"factory": "factory-a", "model_version": "v1.4"}
        →
        {
          "status": "pr_created",
          "pr_url": "https://github.com/jeremyary/industrial-ai-showcase/pull/42",
          "pr_number": 42,
          "branch_name": "agent/promote-model-v1-4-to-factory-a-20260709-143022",
          "factory": "factory-a",
          "model_version": "v1.4",
          "summary": "Model promotion PR created...",
          "git_diff": "```diff\\n+++ b/infrastructure/gitops/..."
        }
    """
    # 1. Get current factory config (for validation and current version)
    try:
        config = await get_factory_config(factory)
        current_version = config.get("policy_version", "unknown")
        factory_namespace = config.get("namespace")  # Get actual namespace (e.g., "factory-b")
        model_name = "vla-warehouse"  # Hardcoded for now - could extract from policy_version

    except HTTPException as e:
        raise HTTPException(status_code=400, detail=f"Invalid factory: {e.detail}")

    # 2. Construct model URI
    # Showcase mode: use HF models (no training required)
    # Production mode: use MLflow S3 storage (requires training pipeline)
    if SHOWCASE_MODE:
        model_uri = HF_MODEL_VERSIONS.get(model_version, HF_MODEL_VERSIONS["v1.4"])
    else:
        model_uri = f"s3://mlflow/models/{model_name}/{model_version}"

    # 3. Generate Kustomize overlay (use namespace, not display name with spaces)
    # factory_namespace is valid Kubernetes namespace (e.g., "factory-b")
    # factory is display name (could be "Factory B" with space - invalid for K8s)
    try:
        overlay_files = generate_model_promotion_overlay(
            model_name=model_name,
            model_version=model_version,
            model_uri=model_uri,
            factory=factory_namespace,  # Use namespace, not display name
            namespace=factory_namespace
        )

        # Generate human-readable summary and diff (use display name for human readability)
        summary = generate_promotion_summary(
            model_name=model_name,
            model_version=model_version,
            model_uri=model_uri,
            factory=factory,  # Display name for summary
            namespace=factory_namespace
        )

        git_diff = generate_promotion_git_diff(
            model_name=model_name,
            model_version=model_version,
            model_uri=model_uri,
            factory=factory_namespace,  # Use namespace for paths
            namespace=factory_namespace
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Kustomize overlay: {str(e)}")

    # 4. Open PR via GitHub API
    try:
        github = get_github_client()

        pr_title = f"Promote {model_name} {model_version} to {factory}"
        pr_body = f"""{summary}

### Current State
- **Current Version**: {current_version}

### Proposed Changes

{git_diff}

---

**Approval**: This PR was approved via Human-in-the-Loop gate in the Showcase Console.

**Generated by**: Agentic Orchestrator
**Pattern**: Agent-opens-PR (no direct cluster API calls)

Co-Authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>
"""

        pr = github.create_pr(
            title=pr_title,
            body=pr_body,
            file_changes=overlay_files,
            base_branch=GITHUB_BASE_BRANCH
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create GitHub PR: {str(e)}")

    # 5. Return PR details
    return {
        "status": "pr_created",
        "pr_url": pr.pr_url,
        "pr_number": pr.pr_number,
        "branch_name": pr.branch_name,
        "commit_sha": pr.commit_sha,
        "factory": factory,
        "model_name": model_name,
        "model_version": model_version,
        "model_uri": model_uri,
        "current_version": current_version,
        "summary": summary,
        "git_diff": git_diff,
        "message": f"PR #{pr.pr_number} created. Argo CD will sync after merge."
    }


# ========== MCP PROTOCOL ENDPOINTS ==========

@app.get("/mcp/tools")
async def list_tools():
    """
    List available MCP tools.
    Returns tool schemas for LangGraph agent.
    """
    return {
        "tools": [
            # Read-only tools
            {
                "name": "get_fleet_status",
                "description": "Get current fleet status across all factories or specific factory. Returns robot status, policy version, anomaly scores.",
                "state_modifying": False,
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Filter by factory name (optional). Use 'factory-a', 'factory-b', or 'Factory A', 'Factory B'.",
                        "required": False
                    }
                },
                "endpoint": "/tools/get_fleet_status"
            },
            {
                "name": "get_factory_config",
                "description": "Get configuration for a specific factory including robots, policy version, safety zones, and operational parameters.",
                "state_modifying": False,
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Factory name (factory-a, factory-b, Factory A, Factory B, or namespace like robot-edge)",
                        "required": True
                    }
                },
                "endpoint": "/tools/get_factory_config"
            },
            {
                "name": "get_robot_telemetry",
                "description": "Get telemetry data for a specific robot including uptime, missions completed, battery level, and current location.",
                "state_modifying": False,
                "parameters": {
                    "robot_id": {
                        "type": "string",
                        "description": "Robot ID (e.g., fl-07, fl-08)",
                        "required": True
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Hours of history to retrieve (default: 24)",
                        "required": False
                    }
                },
                "endpoint": "/tools/get_robot_telemetry"
            },
            {
                "name": "get_anomaly_history",
                "description": "Get anomaly detection history for a factory over specified time window.",
                "state_modifying": False,
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Factory name",
                        "required": True
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Hours of history (default: 24)",
                        "required": False
                    }
                },
                "endpoint": "/tools/get_anomaly_history"
            },

            # State-modifying tool
            {
                "name": "promote_policy_version",
                "description": "Promote model policy version to factory. IMPORTANT: This does NOT modify cluster directly. Instead, it generates Kustomize overlay and opens GitHub PR. Argo CD syncs after PR merge. Use this for safe, auditable model promotions.",
                "state_modifying": True,  # <-- Triggers HIL gate
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Factory name (factory-a or factory-b)",
                        "required": True
                    },
                    "model_version": {
                        "type": "string",
                        "description": "Model version to promote (e.g., v1.4, v1.5)",
                        "required": True
                    }
                },
                "endpoint": "/tools/promote_policy_version"
            }
        ]
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mcp-fleet-server",
        "version": "0.1.0",
        "pattern": "agent-opens-pr"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
