# This project was developed with assistance from AI tools.
"""
FastAPI server for agentic orchestrator
Exposes HTTP API for agent interactions
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx
import os
import json
# Use full orchestrator with HIL gate (Milestone 2)
from orchestrator import run_agent, mcp_client

# Environment configuration
AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://audit-service.agentic-ops.svc.cluster.local:8090")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080")
MCP_FLEET_URL = os.getenv("MCP_FLEET_URL", "http://mcp-fleet-server.agentic-ops.svc.cluster.local:8080")

app = FastAPI(
    title="Agentic Orchestrator",
    description="LangGraph-based read-only agent with MLflow tools",
    version="0.1.0"
)


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None  # Optional session ID for tracking approvals


class QueryResponse(BaseModel):
    query: str
    response: str
    pending_approval_id: int | None = None  # HIL approval ID if created


class ApprovalResumeRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    reason: str | None = None  # Required for rejection


class ApprovalResumeResponse(BaseModel):
    response: str
    status: str


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "agentic-orchestrator",
        "version": "0.1.0"
    }


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Process a user query through the agent"""
    try:
        result = run_agent(request.query, session_id=request.session_id)
        return QueryResponse(
            query=request.query,
            response=result["response"],
            pending_approval_id=result.get("pending_approval_id")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
async def list_tools():
    """List available MCP tools"""
    try:
        tools = mcp_client.discover_tools()
        return {"tools": tools}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approval/{approval_id}/resume", response_model=ApprovalResumeResponse)
async def resume_after_approval(approval_id: int, request: ApprovalResumeRequest):
    """
    Resume execution after HIL approval decision.
    If approved: executes the tool and returns result.
    If rejected: returns rejection message.
    """
    try:
        # Fetch approval request details from audit service
        client = httpx.Client(timeout=30.0)

        # Check pending approvals first
        pending_resp = client.get(f"{AUDIT_SERVICE_URL}/audit/pending")
        pending_resp.raise_for_status()
        pending_data = pending_resp.json()

        # Find the specific approval request in pending
        approval_request = None
        for entry in pending_data.get("pending", []):
            if entry["id"] == approval_id:
                approval_request = entry
                break

        # If not in pending, check history
        if not approval_request:
            history_resp = client.get(f"{AUDIT_SERVICE_URL}/audit/history?limit=100")
            history_resp.raise_for_status()
            history_data = history_resp.json()

            for entry in history_data.get("history", []):
                if entry["id"] == approval_id:
                    approval_request = entry
                    break

        if not approval_request:
            raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")

        tool_name = approval_request["tool_name"]
        tool_arguments = approval_request["tool_arguments"]

        if request.decision == "rejected":
            # Update audit record with result
            try:
                client.post(
                    f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                    json={"result": {"status": "rejected", "reason": request.reason}}
                )
            except Exception as e:
                print(f"Warning: Failed to update audit result: {e}")

            return ApprovalResumeResponse(
                response=f"Action rejected by operator: {request.reason or 'No reason provided'}",
                status="rejected"
            )

        elif request.decision == "approved":
            # Execute the tool based on tool_name
            if tool_name == "register_model":
                run_id = tool_arguments.get("run_id")
                model_name = tool_arguments.get("model_name")

                # Call MCP server directly with POST
                try:
                    mcp_resp = client.post(
                        f"{MCP_BASE_URL}/tools/register_model",
                        params={"run_id": run_id, "model_name": model_name}
                    )
                    mcp_resp.raise_for_status()
                    result = mcp_resp.json()
                except Exception as e:
                    error_msg = f"Failed to execute register_model: {str(e)}"
                    # Update audit record with error
                    try:
                        client.post(
                            f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                            json={"error": error_msg}
                        )
                    except:
                        pass
                    raise HTTPException(status_code=500, detail=error_msg)

                # Update audit record with result
                try:
                    client.post(
                        f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                        json={"result": {"status": "success", "data": result}}
                    )
                except Exception as e:
                    print(f"Warning: Failed to update audit result: {e}")

                return ApprovalResumeResponse(
                    response=f"✅ Approved and executed: Model '{result['model_name']}' version {result['version']} registered from run {result['run_id']}",
                    status="approved"
                )

            elif tool_name == "promote_policy_version":
                factory = tool_arguments.get("factory")
                model_version = tool_arguments.get("model_version")

                # Call MCP Fleet server directly with POST (opens GitHub PR)
                try:
                    mcp_resp = client.post(
                        f"{MCP_FLEET_URL}/tools/promote_policy_version",
                        params={"factory": factory, "model_version": model_version}
                    )
                    mcp_resp.raise_for_status()
                    result = mcp_resp.json()
                except Exception as e:
                    error_msg = f"Failed to execute promote_policy_version: {str(e)}"
                    # Update audit record with error
                    try:
                        client.post(
                            f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                            json={"error": error_msg}
                        )
                    except:
                        pass
                    raise HTTPException(status_code=500, detail=error_msg)

                # Update audit record with result (including PR URL)
                try:
                    client.post(
                        f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                        json={"result": {"status": "pr_created", "data": result}}
                    )
                except Exception as e:
                    print(f"Warning: Failed to update audit result: {e}")

                pr_url = result.get("pr_url", "")
                pr_number = result.get("pr_number", "")

                return ApprovalResumeResponse(
                    response=f"✅ Approved and executed: PR #{pr_number} created for {factory} → {model_version}. PR URL: {pr_url}",
                    status="approved"
                )

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown tool: {tool_name}"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid decision: {request.decision}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)