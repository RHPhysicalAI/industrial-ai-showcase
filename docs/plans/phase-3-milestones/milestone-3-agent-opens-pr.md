# Milestone 3: Agent-Opens-PR Pattern — Implementation Plan

> [!NOTE]
> This project was developed with assistance from AI tools.

**Status**: In Progress  
**Duration**: 2 weeks (Weeks 5-6 of Phase 3)  
**Prerequisites**: Milestone 2 (HIL Gate) complete ✅

---

## Goal

**Agent never calls the cluster API directly.** Every state-modifying action flows through Git:
1. Agent proposes change (e.g., "promote model v1.4 to Factory A")
2. HIL gate triggers, drawer opens
3. Operator reviews **proposed Git diff** (Kustomize overlay)
4. On approval: Agent **opens PR** to `infrastructure/gitops/`
5. PR merges (auto or manual)
6. Argo CD detects change, syncs cluster

**Key Architectural Insight**: This reframes "LLM touching OT infrastructure" as "LLM participating in code review" — a familiar, auditable, rollback-friendly pattern.

---

## Success Criteria

Milestone 3 is **complete** when:

1. ✅ **Agent opens real PR** (visible in GitHub UI at `infrastructure/gitops/apps/workloads/`)
2. ✅ **PR contains correct Kustomize overlay diff** (model URI change, not arbitrary YAML)
3. ✅ **HIL drawer shows Git diff** in new "Proposed Changes" pane
4. ✅ **Argo CD picks up merged PR** and syncs within 30 seconds
5. ✅ **Audit record includes PR URL** (immutable trail links approval → PR → cluster state)
6. ✅ **Read-only fleet queries work** (`get_fleet_status`, `get_factory_config`)
7. ✅ **End-to-end test passes**: Query → HIL → Approve → PR → Argo sync → Success

---

## Architecture Overview

### Current State (Milestone 2)
```
User Query → Orchestrator → vLLM → Tool Call (register_model)
                                          ↓
                                    HIL Gate Triggers
                                          ↓
                                    Operator Approves
                                          ↓
                              Direct MCP Server Call (MLflow API)
```

### Target State (Milestone 3)
```
User Query → Orchestrator → vLLM → Tool Call (promote_policy_version)
                                          ↓
                                    HIL Gate Triggers
                                          ↓
                                    Drawer Shows Git Diff
                                          ↓
                                    Operator Approves
                                          ↓
                              GitHub API: Create PR
                                          ↓
                              PR Merges (auto via CODEOWNERS)
                                          ↓
                              Argo CD: git pull → sync
                                          ↓
                              Cluster State Updated
```

**Key Change**: No direct API calls to Fleet Manager, KServe, or OpenShift. All state changes are Git-mediated.

---

## Week 1: GitHub Integration Foundation

### Day 1-2: GitHub Bot Account Setup

**Objective**: Create dedicated bot account with minimal permissions.

**Steps**:

1. **Create GitHub machine user** (or use existing Red Hat bot account):
   - Username: `rh-industrial-ai-bot` (or similar)
   - Email: `industrial-ai-showcase-bot@redhat.com`
   - Description: "Automated PR creator for Industrial AI Showcase agentic operations"

2. **Grant repository access**:
   - Add bot as collaborator to `jeremyary/industrial-ai-showcase` (or fork)
   - Permissions: **Write** (can create branches, open PRs)
   - **NOT** Admin (cannot merge without review, cannot modify settings)

3. **Generate Personal Access Token (PAT)**:
   - Scope: `repo` (full control of private repositories)
   - Expiration: 90 days (set reminder to rotate)
   - Store in OpenShift Secret:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: github-bot-token
     namespace: agentic-ops
   type: Opaque
   stringData:
     token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

4. **Test token manually**:
   ```bash
   export GITHUB_TOKEN=ghp_xxxx
   export GITHUB_REPO=jeremyary/industrial-ai-showcase
   
   # Test: Create a branch
   curl -H "Authorization: token $GITHUB_TOKEN" \
     -X POST https://api.github.com/repos/$GITHUB_REPO/git/refs \
     -d '{"ref":"refs/heads/test-bot-branch","sha":"<main-commit-sha>"}'
   
   # Test: Open a PR
   curl -H "Authorization: token $GITHUB_TOKEN" \
     -X POST https://api.github.com/repos/$GITHUB_REPO/pulls \
     -d '{"title":"Test Bot PR","head":"test-bot-branch","base":"main","body":"Test"}'
   ```

**Deliverable**: Bot account functional, token stored in cluster secret.

---

### Day 3-4: PR Creation Logic in Orchestrator

**Objective**: Orchestrator can programmatically create PRs.

**New File**: `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/github_client.py`

```python
# This project was developed with assistance from AI tools.
"""
GitHub API client for creating PRs from agentic orchestrator.
"""
import os
import httpx
from typing import Optional
from dataclasses import dataclass


@dataclass
class PRResult:
    """Result of PR creation."""
    pr_number: int
    pr_url: str
    branch_name: str
    commit_sha: str


class GitHubClient:
    """GitHub API client for PR operations."""
    
    def __init__(self, token: str, repo: str):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub Personal Access Token
            repo: Repository in format "owner/repo"
        """
        self.token = token
        self.repo = repo
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def create_pr(
        self,
        title: str,
        body: str,
        file_changes: dict[str, str],
        base_branch: str = "main"
    ) -> PRResult:
        """
        Create a PR with specified file changes.
        
        Args:
            title: PR title
            body: PR description
            file_changes: Dict of {file_path: new_content}
            base_branch: Base branch (default: main)
        
        Returns:
            PRResult with PR details
        """
        # 1. Get base branch SHA
        base_sha = self._get_branch_sha(base_branch)
        
        # 2. Create new branch
        branch_name = self._generate_branch_name(title)
        self._create_branch(branch_name, base_sha)
        
        # 3. Get base tree SHA
        base_tree_sha = self._get_tree_sha(base_sha)
        
        # 4. Create new tree with file changes
        new_tree_sha = self._create_tree(base_tree_sha, file_changes)
        
        # 5. Create commit
        commit_message = f"{title}\n\n{body}\n\nCo-Authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>"
        commit_sha = self._create_commit(commit_message, new_tree_sha, base_sha)
        
        # 6. Update branch to point to new commit
        self._update_branch(branch_name, commit_sha)
        
        # 7. Create PR
        pr_data = self._create_pull_request(title, body, branch_name, base_branch)
        
        return PRResult(
            pr_number=pr_data["number"],
            pr_url=pr_data["html_url"],
            branch_name=branch_name,
            commit_sha=commit_sha
        )
    
    def _get_branch_sha(self, branch: str) -> str:
        """Get SHA of latest commit on branch."""
        resp = httpx.get(
            f"{self.api_base}/repos/{self.repo}/git/refs/heads/{branch}",
            headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()["object"]["sha"]
    
    def _create_branch(self, branch_name: str, sha: str) -> None:
        """Create new branch from SHA."""
        resp = httpx.post(
            f"{self.api_base}/repos/{self.repo}/git/refs",
            headers=self.headers,
            json={"ref": f"refs/heads/{branch_name}", "sha": sha}
        )
        resp.raise_for_status()
    
    def _get_tree_sha(self, commit_sha: str) -> str:
        """Get tree SHA from commit SHA."""
        resp = httpx.get(
            f"{self.api_base}/repos/{self.repo}/git/commits/{commit_sha}",
            headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()["tree"]["sha"]
    
    def _create_tree(self, base_tree_sha: str, file_changes: dict[str, str]) -> str:
        """Create new tree with file changes."""
        tree_items = []
        for path, content in file_changes.items():
            # Create blob for file content
            blob_resp = httpx.post(
                f"{self.api_base}/repos/{self.repo}/git/blobs",
                headers=self.headers,
                json={"content": content, "encoding": "utf-8"}
            )
            blob_resp.raise_for_status()
            blob_sha = blob_resp.json()["sha"]
            
            tree_items.append({
                "path": path,
                "mode": "100644",  # regular file
                "type": "blob",
                "sha": blob_sha
            })
        
        # Create tree
        tree_resp = httpx.post(
            f"{self.api_base}/repos/{self.repo}/git/trees",
            headers=self.headers,
            json={"base_tree": base_tree_sha, "tree": tree_items}
        )
        tree_resp.raise_for_status()
        return tree_resp.json()["sha"]
    
    def _create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        """Create commit."""
        resp = httpx.post(
            f"{self.api_base}/repos/{self.repo}/git/commits",
            headers=self.headers,
            json={
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha]
            }
        )
        resp.raise_for_status()
        return resp.json()["sha"]
    
    def _update_branch(self, branch_name: str, commit_sha: str) -> None:
        """Update branch to point to commit."""
        resp = httpx.patch(
            f"{self.api_base}/repos/{self.repo}/git/refs/heads/{branch_name}",
            headers=self.headers,
            json={"sha": commit_sha}
        )
        resp.raise_for_status()
    
    def _create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str
    ) -> dict:
        """Create pull request."""
        resp = httpx.post(
            f"{self.api_base}/repos/{self.repo}/pulls",
            headers=self.headers,
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    def _generate_branch_name(self, title: str) -> str:
        """Generate branch name from PR title."""
        import re
        from datetime import datetime
        
        # Slugify title
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"agent/{slug}-{timestamp}"


# Singleton instance (loaded from environment)
def get_github_client() -> GitHubClient:
    """Get GitHub client from environment."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO", "jeremyary/industrial-ai-showcase")
    
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set")
    
    return GitHubClient(token=token, repo=repo)
```

**Test**:
```python
# Test PR creation
client = get_github_client()

# Simple test: update README
file_changes = {
    "README.md": "# Test\nThis is a test PR from the bot."
}

pr = client.create_pr(
    title="Test: Bot PR Creation",
    body="Testing automated PR creation from agentic orchestrator.",
    file_changes=file_changes
)

print(f"PR created: {pr.pr_url}")
```

**Deliverable**: `github_client.py` functional, can create PRs programmatically.

---

### Day 5: Kustomize Overlay Generator

**Objective**: Convert model promotion request into Kustomize overlay diff.

**New File**: `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/kustomize_generator.py`

```python
# This project was developed with assistance from AI tools.
"""
Kustomize overlay generator for model promotions.
Converts agent requests into Git-committable YAML changes.
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


class KustomizeGenerator:
    """Generate Kustomize overlays for model promotions."""
    
    def generate_overlay(self, promotion: ModelPromotion) -> dict[str, str]:
        """
        Generate Kustomize overlay files for model promotion.
        
        Returns:
            Dict of {file_path: yaml_content}
        """
        base_path = f"infrastructure/gitops/apps/workloads/{promotion.factory}"
        
        # Generate InferenceService patch
        isvc_patch = self._generate_isvc_patch(promotion)
        
        # Generate kustomization.yaml update
        kustomization = self._generate_kustomization(promotion)
        
        return {
            f"{base_path}/model-{promotion.model_name}-patch.yaml": yaml.dump(isvc_patch),
            f"{base_path}/kustomization.yaml": yaml.dump(kustomization)
        }
    
    def _generate_isvc_patch(self, promotion: ModelPromotion) -> dict:
        """Generate InferenceService patch YAML."""
        return {
            "apiVersion": "serving.kserve.io/v1beta1",
            "kind": "InferenceService",
            "metadata": {
                "name": promotion.model_name,
                "namespace": promotion.factory
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
    
    def _generate_kustomization(self, promotion: ModelPromotion) -> dict:
        """Generate kustomization.yaml with patch reference."""
        return {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": promotion.factory,
            "resources": [
                "../../base/vla-inference"
            ],
            "patches": [
                {
                    "path": f"model-{promotion.model_name}-patch.yaml",
                    "target": {
                        "kind": "InferenceService",
                        "name": promotion.model_name
                    }
                }
            ]
        }
    
    def generate_git_diff_preview(self, promotion: ModelPromotion) -> str:
        """
        Generate human-readable Git diff preview for HIL drawer.
        """
        overlay = self.generate_overlay(promotion)
        
        diff_lines = []
        for path, content in overlay.items():
            diff_lines.append(f"--- a/{path}")
            diff_lines.append(f"+++ b/{path}")
            diff_lines.append("@@ -0,0 +1,XX @@")
            for line in content.split("\n"):
                diff_lines.append(f"+{line}")
        
        return "\n".join(diff_lines)


# Singleton
_generator = KustomizeGenerator()

def generate_model_promotion_overlay(
    model_name: str,
    model_version: str,
    model_uri: str,
    factory: str
) -> dict[str, str]:
    """Generate Kustomize overlay for model promotion."""
    promotion = ModelPromotion(
        model_name=model_name,
        model_version=model_version,
        model_uri=model_uri,
        factory=factory
    )
    return _generator.generate_overlay(promotion)
```

**Test**:
```python
# Test overlay generation
overlay = generate_model_promotion_overlay(
    model_name="vla-warehouse",
    model_version="v1.4",
    model_uri="s3://mlflow/models/vla-warehouse/v1.4",
    factory="factory-a"
)

for path, content in overlay.items():
    print(f"\n=== {path} ===")
    print(content)
```

**Deliverable**: Kustomize generator produces valid YAML overlays.

---

## Week 2: Fleet MCP Server + Integration

### Day 6-7: mcp-fleet Server (Read-Only Tools)

**Objective**: Build MCP server for fleet operations queries.

**New Directory**: `infrastructure/gitops/apps/workloads/mcp-fleet-server/`

**Structure**:
```
mcp-fleet-server/
├── Dockerfile
├── requirements.txt
├── src/
│   ├── mcp_server.py
│   └── fleet_client.py
├── deployment.yaml
└── service.yaml
```

**File**: `src/mcp_server.py` (skeleton - full implementation in next message)

```python
# This project was developed with assistance from AI tools.
"""
MCP server for Fleet Manager operations.
Exposes read-only and state-modifying fleet tools.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import httpx
import os

app = FastAPI(
    title="MCP Fleet Server",
    description="Fleet Manager MCP tools for agentic operations",
    version="0.1.0"
)

# Environment
FLEET_MANAGER_URL = os.getenv("FLEET_MANAGER_URL", "http://fleet-manager.fleet-ops.svc.cluster.local:8080")


# ========== READ-ONLY TOOLS ==========

@app.get("/tools/get_fleet_status")
async def get_fleet_status(factory: Optional[str] = None):
    """
    Get current fleet status (read-only).
    
    Args:
        factory: Filter by factory (optional)
    
    Returns:
        Fleet status summary
    """
    # Call Fleet Manager API
    client = httpx.Client(timeout=10.0)
    resp = client.get(f"{FLEET_MANAGER_URL}/api/fleet")
    resp.raise_for_status()
    
    fleet_data = resp.json()
    
    # Filter by factory if specified
    if factory:
        factories = [f for f in fleet_data.get("factories", []) if f.get("name") == factory]
        return {"factories": factories}
    
    return fleet_data


@app.get("/tools/get_factory_config")
async def get_factory_config(factory: str):
    """
    Get factory configuration (read-only).
    
    Args:
        factory: Factory name ("factory-a" | "factory-b")
    
    Returns:
        Factory config (robots, policy version, etc.)
    """
    # Mock implementation - replace with real API call
    # In real implementation, this would query OpenShift ConfigMaps or GitOps repo
    
    configs = {
        "factory-a": {
            "name": "Factory A",
            "namespace": "robot-edge",
            "policy_version": "vla-warehouse-v1.3",
            "robots": ["fl-07", "fl-08", "fl-09"],
            "robot_count": 3,
            "max_speed": 2.0,
            "safety_zones": ["loading-dock", "aisle-1", "aisle-2", "aisle-3"]
        },
        "factory-b": {
            "name": "Factory B",
            "namespace": "factory-b",
            "policy_version": "vla-warehouse-v1.2",
            "robots": ["fl-10", "fl-11"],
            "robot_count": 2,
            "max_speed": 1.5,
            "safety_zones": ["warehouse-north", "warehouse-south"]
        }
    }
    
    if factory not in configs:
        raise HTTPException(status_code=404, detail=f"Factory {factory} not found")
    
    return configs[factory]


# ========== MCP PROTOCOL ENDPOINTS ==========

@app.get("/mcp/tools")
async def list_tools():
    """
    List available MCP tools.
    Returns tool schemas for LangGraph agent.
    """
    return {
        "tools": [
            {
                "name": "get_fleet_status",
                "description": "Get current fleet status across all factories or specific factory",
                "state_modifying": False,
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Filter by factory name (optional)",
                        "required": False
                    }
                },
                "endpoint": "/tools/get_fleet_status"
            },
            {
                "name": "get_factory_config",
                "description": "Get configuration for a specific factory (robots, policy version, safety zones)",
                "state_modifying": False,
                "parameters": {
                    "factory": {
                        "type": "string",
                        "description": "Factory name (factory-a or factory-b)",
                        "required": True
                    }
                },
                "endpoint": "/tools/get_factory_config"
            }
        ]
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mcp-fleet-server"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Deliverable**: mcp-fleet server running, read-only tools queryable.

---

### Day 8-9: promote_policy_version Tool (Opens PR)

**Objective**: Add state-modifying tool that opens PR instead of calling cluster API.

**Add to** `src/mcp_server.py`:

```python
# ========== STATE-MODIFYING TOOLS ==========

@app.post("/tools/promote_policy_version")
async def promote_policy_version(factory: str, model_version: str):
    """
    Promote model policy version to factory (state-modifying).
    
    This tool DOES NOT call the cluster API directly.
    Instead, it:
    1. Generates Kustomize overlay
    2. Opens PR to infrastructure/gitops/
    3. Returns PR URL
    4. Argo CD will sync on PR merge
    
    Args:
        factory: Factory name
        model_version: Model version to promote (e.g., "v1.4")
    
    Returns:
        PR details (URL, number, branch)
    """
    from kustomize_generator import generate_model_promotion_overlay
    from github_client import get_github_client
    
    # 1. Get current factory config (for model name)
    config = await get_factory_config(factory)
    current_version = config["policy_version"]
    model_name = "vla-warehouse"  # Hardcoded for now
    
    # 2. Generate Kustomize overlay
    model_uri = f"s3://mlflow/models/{model_name}/{model_version}"
    overlay_files = generate_model_promotion_overlay(
        model_name=model_name,
        model_version=model_version,
        model_uri=model_uri,
        factory=factory
    )
    
    # 3. Open PR via GitHub API
    github = get_github_client()
    pr = github.create_pr(
        title=f"Promote {model_name} {model_version} to {factory}",
        body=f"""
## Model Promotion

- **Factory**: {factory}
- **Model**: {model_name}
- **Current Version**: {current_version}
- **New Version**: {model_version}
- **Model URI**: {model_uri}

### Changes
- Updates InferenceService `{model_name}` storageUri
- Generated by agentic orchestrator

### Approval
This PR was approved via Human-in-the-Loop gate.

Co-Authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>
        """,
        file_changes=overlay_files
    )
    
    return {
        "status": "pr_created",
        "pr_url": pr.pr_url,
        "pr_number": pr.pr_number,
        "branch_name": pr.branch_name,
        "factory": factory,
        "model_version": model_version,
        "message": f"PR #{pr.pr_number} created. Argo CD will sync after merge."
    }
```

**Update MCP tool list**:
```python
{
    "name": "promote_policy_version",
    "description": "Promote model policy version to factory (opens PR, does not modify cluster directly)",
    "state_modifying": True,  # <-- Triggers HIL gate
    "parameters": {
        "factory": {"type": "string", "required": True},
        "model_version": {"type": "string", "required": True}
    },
    "endpoint": "/tools/promote_policy_version"
}
```

**Deliverable**: promote_policy_version opens PR, returns PR URL.

---

### Day 10: Update Orchestrator to Connect mcp-fleet

**Update**: `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/orchestrator.py`

Add mcp-fleet tools to orchestrator:

```python
# Connect to mcp-fleet server
MCP_FLEET_URL = os.getenv("MCP_FLEET_URL", "http://mcp-fleet-server.agentic-ops.svc.cluster.local:8080")

# ... (existing MCP client code) ...

# Add fleet tools
@tool
def get_fleet_status(factory: str = None) -> str:
    """Get current fleet status across factories"""
    result = mcp_client.invoke_tool("get_fleet_status", {"factory": factory})
    return json.dumps(result, indent=2)

@tool
def get_factory_config(factory: str) -> str:
    """Get factory configuration (robots, policy version, safety zones)"""
    result = mcp_client.invoke_tool("get_factory_config", {"factory": factory})
    return json.dumps(result, indent=2)

@tool
def promote_policy_version(factory: str, model_version: str) -> str:
    """Promote model policy version to factory (opens PR, triggers HIL gate)"""
    # This will be intercepted by custom_tool_node before execution
    result = mcp_client.invoke_tool("promote_policy_version", {
        "factory": factory,
        "model_version": model_version
    })
    return json.dumps(result, indent=2)

# Update STATE_MODIFYING_TOOLS
STATE_MODIFYING_TOOLS = {"register_model", "promote_policy_version"}

# Update tool lists
read_only_tools = [
    list_experiments, get_experiment, list_runs, get_run, get_metrics,
    get_fleet_status, get_factory_config  # NEW
]

state_modifying_tools_list = [
    register_model,
    promote_policy_version  # NEW
]
```

**Deliverable**: Orchestrator can call fleet tools, promote_policy_version triggers HIL gate.

---

## Testing Plan

### Unit Tests

**Test 1: GitHub Client**
```python
def test_github_pr_creation():
    client = get_github_client()
    
    file_changes = {
        "test/README.md": "# Test PR\nThis is automated."
    }
    
    pr = client.create_pr(
        title="Test: Automated PR",
        body="Testing PR creation logic",
        file_changes=file_changes
    )
    
    assert pr.pr_number > 0
    assert "github.com" in pr.pr_url
    assert pr.branch_name.startswith("agent/")
```

**Test 2: Kustomize Generator**
```python
def test_kustomize_overlay_generation():
    overlay = generate_model_promotion_overlay(
        model_name="vla-warehouse",
        model_version="v1.4",
        model_uri="s3://mlflow/models/vla-warehouse/v1.4",
        factory="factory-a"
    )
    
    # Check files generated
    assert "infrastructure/gitops/apps/workloads/factory-a/model-vla-warehouse-patch.yaml" in overlay
    assert "infrastructure/gitops/apps/workloads/factory-a/kustomization.yaml" in overlay
    
    # Check YAML is valid
    patch_yaml = yaml.safe_load(overlay[list(overlay.keys())[0]])
    assert patch_yaml["kind"] == "InferenceService"
```

**Test 3: mcp-fleet Tools**
```python
async def test_fleet_tools():
    # Test read-only
    status = await get_fleet_status(factory="factory-a")
    assert "factories" in status
    
    config = await get_factory_config(factory="factory-a")
    assert config["name"] == "Factory A"
    assert "robots" in config
```

---

### Integration Test: End-to-End PR Flow

**Test Case**:
```gherkin
Given: Orchestrator + mcp-fleet + GitHub integration are running
When: Operator asks "Promote vla-warehouse v1.4 to Factory A"
Then:
  1. Agent queries mcp-fleet.get_factory_config("factory-a") [read-only]
  2. Agent proposes mcp-fleet.promote_policy_version [state-modifying]
  3. HIL gate triggers
  4. Drawer shows Git diff (Kustomize overlay)
  5. Operator approves
  6. Tool executes: opens PR
  7. PR visible in GitHub at infrastructure/gitops/apps/workloads/factory-a/
  8. Audit record includes PR URL
```

**Automated Test Script**:
```bash
#!/bin/bash
# test-pr-flow.sh

set -euo pipefail

echo "=== Test: End-to-End PR Flow ==="

# 1. Send agent query
RESPONSE=$(oc exec -n agentic-ops deployment/agentic-orchestrator -- curl -s -X POST \
  http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Promote vla-warehouse v1.4 to Factory A", "session_id": "test-pr-flow"}')

echo "Agent Response: $RESPONSE"

# 2. Check if HIL gate triggered
if echo "$RESPONSE" | grep -q "Request #"; then
  echo "✅ HIL gate triggered"
  APPROVAL_ID=$(echo "$RESPONSE" | grep -oP 'Request #\K\d+')
  echo "Approval ID: $APPROVAL_ID"
else
  echo "❌ HIL gate did NOT trigger"
  exit 1
fi

# 3. Approve the request
APPROVAL_RESULT=$(oc exec -n fleet-ops deployment/showcase-console-backend -- curl -s -X POST \
  http://localhost:8090/api/approval/$APPROVAL_ID/approve)

echo "Approval Result: $APPROVAL_RESULT"

# 4. Check if PR was created
if echo "$APPROVAL_RESULT" | grep -q "pr_url"; then
  PR_URL=$(echo "$APPROVAL_RESULT" | jq -r '.pr_url // empty')
  echo "✅ PR created: $PR_URL"
else
  echo "❌ PR was NOT created"
  exit 1
fi

# 5. Verify audit record includes PR URL
AUDIT_RECORD=$(oc exec -n agentic-ops deployment/audit-service -- curl -s \
  "http://localhost:8090/audit/history?limit=1")

if echo "$AUDIT_RECORD" | grep -q "$PR_URL"; then
  echo "✅ Audit record includes PR URL"
else
  echo "❌ Audit record does NOT include PR URL"
  exit 1
fi

echo "=== All tests passed! ==="
```

---

## Deliverables

### Week 1
- ✅ GitHub bot account created with PAT stored in cluster secret
- ✅ `github_client.py` functional (can create PRs programmatically)
- ✅ `kustomize_generator.py` produces valid Kustomize overlays

### Week 2
- ✅ `mcp-fleet-server` running with read-only tools
- ✅ `promote_policy_version` tool opens PR (not direct API call)
- ✅ Orchestrator connects to mcp-fleet, classifies promote_policy_version as state-modifying
- ✅ End-to-end test passes: Query → HIL → Approve → PR → Audit includes PR URL

---

## Known Limitations & Phase 4 Enhancements

### Limitation 1: PR Auto-Merge Not Implemented
**Current State**: PR is created, but requires manual merge (or GitHub Actions workflow).

**Phase 4**: 
- Add CODEOWNERS file to auto-approve bot PRs
- Or: GitHub Actions workflow that merges PRs from bot account after checks pass

### Limitation 2: No Rollback Mechanism
**Current State**: If promoted model fails, operator must manually revert PR.

**Phase 4**:
- Add "Rollback" button in Console that opens revert PR
- Audit trail links original promotion → rollback

### Limitation 3: Single Factory at a Time
**Current State**: promote_policy_version handles one factory per call.

**Phase 4**:
- Batch promotions: "Promote v1.4 to Factory A, B, and C"
- Single PR with multiple Kustomize overlays

---

## Success Metrics

**Milestone 3 Complete When**:
1. ✅ Agent opens real PR visible in GitHub UI
2. ✅ PR contains correct Kustomize overlay (not arbitrary YAML)
3. ✅ Argo CD syncs after PR merge (< 30 seconds)
4. ✅ Audit record includes PR URL
5. ✅ End-to-end test script passes 3 consecutive runs

**Ready to proceed to Milestone 4** (Full 6-Pane Drawer + TrustyAI).

---

**Co-Authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>**
