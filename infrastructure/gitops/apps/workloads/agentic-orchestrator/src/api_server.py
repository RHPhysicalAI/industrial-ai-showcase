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
import logging
from uuid import uuid4
from datetime import datetime, UTC

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
# Use full orchestrator with HIL gate (Milestone 2)
from orchestrator import run_agent, mcp_client

# Kafka for events
from kafka import KafkaProducer

# Llama Stack integration (Milestone 3 - Phase 3)
from llama_stack_adapter import get_llama_stack_adapter, is_llama_stack_enabled

# Content moderation (Phase 3 - ADR-019)
from moderation_client import (
    moderate_input,
    moderate_output,
    BLOCKED_INPUT_RESPONSE,
    BLOCKED_OUTPUT_RESPONSE
)

# Environment configuration
AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://audit-service.agentic-ops.svc.cluster.local:8090")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080")
MCP_FLEET_URL = os.getenv("MCP_FLEET_URL", "http://mcp-fleet-server.agentic-ops.svc.cluster.local:8080")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka-kafka-bootstrap.amq-streams.svc.cluster.local:9092")

app = FastAPI(
    title="Agentic Orchestrator",
    description="LangGraph-based read-only agent with MLflow tools",
    version="0.1.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize Llama Stack integration on startup"""
    adapter = get_llama_stack_adapter()

    print(f"Agentic Orchestrator starting...")
    print(f"HIL Mode: {adapter.get_mode_description()}")

    if adapter.is_enabled():
        try:
            # Discover and register MCP tools with Llama Stack
            print("Initializing Llama Stack with MCP tools...")

            # Get tools from MCP servers
            mlflow_tools = mcp_client.discover_tools()
            from orchestrator import mcp_fleet_client
            fleet_tools = mcp_fleet_client.discover_tools()

            all_tools = mlflow_tools + fleet_tools

            # Convert to Llama Stack format
            llama_tools = []
            for tool in all_tools:
                llama_tools.append({
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("parameters", {}),
                    "metadata": {
                        "state_modifying": tool.get("state_modifying", False),
                        "endpoint": tool.get("endpoint", "")
                    }
                })

            # Initialize agent with tools
            agent_id = adapter.initialize_agent(
                tools=llama_tools,
                instructions="""
                You are an AI assistant for physical AI operations in industrial warehouses.
                You help operators manage robot fleets and ML model deployments.

                Available tools:
                - Fleet management: Check factory status, robot telemetry, anomaly history
                - Model operations: Promote models to factories, register models in MLflow
                - MLflow: List experiments, get run metrics

                Important:
                - Always check current state before making changes
                - Explain what you're about to do for state-modifying operations
                - State-modifying operations require human approval (HIL)
                """
            )

            print(f"Llama Stack agent initialized: {agent_id}")

        except Exception as e:
            print(f"Warning: Llama Stack initialization failed: {e}")
            print("Falling back to passthrough mode")
    else:
        print("Running in passthrough mode (custom HIL in orchestrator.py)")

    # Start fleet event listener for rollback analysis (Phase 3 Item #8)
    try:
        from event_listener import start_event_listener
        start_event_listener(on_rollback_callback=handle_rollback_event)
        print("Fleet event listener started (listening for rollbacks)")
    except Exception as e:
        print(f"Warning: Fleet event listener failed to start: {e}")
        print("Rollback analysis will not be available")


def publish_policy_promoted_event(factory: str, version: str, trace_id: str = None):
    """
    Publish policy.promoted event to Kafka fleet.events topic.
    This notifies the console that a new version has been promoted.

    Args:
        factory: Factory name (e.g., "Factory A", "Factory B")
        version: Model version (e.g., "vla-warehouse-v1.4")
        trace_id: Optional trace ID for correlation
    """
    try:
        from kafka import KafkaProducer

        if trace_id is None:
            trace_id = str(uuid4())

        # Map display names to namespace names for Kafka
        factory_namespace_map = {
            "Factory A": "factory-a",
            "Factory B": "factory-b",
            "factory-a": "factory-a",
            "factory-b": "factory-b",
            "robot-edge": "factory-a",  # Legacy mapping
        }
        factory_key = factory_namespace_map.get(factory, factory.lower().replace(" ", "-"))

        event = {
            "event_id": str(uuid4()),
            "trace_id": trace_id,
            "event_class": "policy.promoted",
            "source": "agentic-orchestrator",
            "location": factory_key,
            "confidence": 1.0,
            "emitted_at": datetime.now(UTC).isoformat(),
            "payload": {
                "factory": factory_key,
                "version": version
            }
        }

        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )

        producer.send("fleet.events", value=event)
        producer.flush(timeout=5)
        producer.close()

        print(f"Published policy.promoted event: {factory} → {version}")

    except Exception as e:
        # Log error but don't fail the approval - the PR is already merged
        print(f"Warning: Failed to publish Kafka event: {e}")


async def handle_rollback_event(event: dict):
    """
    Handle fleet rollback event by triggering agent investigation.

    Called by event_listener when policy.rollback event is received.
    Agent investigates what happened (read-only) and generates analysis.

    Args:
        event: Rollback event from Kafka fleet.events topic
    """
    factory = event.get('factory', 'unknown')
    from_version = event.get('from_version', 'unknown')
    to_version = event.get('to_version', 'unknown')
    trigger = event.get('trigger', 'unknown')

    logger.info(
        f"🔍 Rollback event received: {factory} {from_version} → {to_version} "
        f"(trigger: {trigger})"
    )

    # Build investigation query for agent
    query = f"""
A policy rollback just occurred in {factory}:
- Rolled back FROM: {from_version}
- Rolled back TO: {to_version}
- Trigger: {trigger}

Please investigate what happened and provide analysis:
1. When was {from_version} promoted? (check recent promotion history)
2. What is the current factory status?
3. What were the training characteristics of {from_version}?
4. What hypothesis can you form about why the rollback occurred?

Provide a concise analysis with evidence, hypothesis, and recommendations.
"""

    try:
        # Trigger agent investigation (read-only, no HIL needed)
        session_id = f"rollback-analysis-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        logger.info(f"Triggering agent investigation (session: {session_id})")

        # Run agent investigation
        result = run_agent(query, session_id=session_id)
        agent_response = result.get("response", "No response from agent")

        logger.info(f"✅ Agent analysis complete:")
        logger.info(f"   Factory: {factory}")
        logger.info(f"   Rollback: {from_version} → {to_version}")
        logger.info(f"   Analysis preview: {agent_response[:200]}...")

        # TODO (Day 3-4): Store analysis and publish to Console UI
        # For now, just log it - UI integration comes next

        # Publish analysis event to Console (simple version for Day 2)
        try:
            from kafka import KafkaProducer

            analysis_event = {
                "type": "rollback.analysis",
                "timestamp": datetime.now(UTC).isoformat(),
                "factory": factory,
                "from_version": from_version,
                "to_version": to_version,
                "trigger": trigger,
                "agent_analysis": agent_response,
                "session_id": session_id
            }

            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8")
            )

            producer.send("fleet.events", value=analysis_event)
            producer.flush(timeout=5)
            producer.close()

            logger.info("Published rollback.analysis event to Kafka")

        except Exception as e:
            logger.error(f"Failed to publish analysis event: {e}")

    except Exception as e:
        logger.error(f"Agent investigation failed: {e}", exc_info=True)


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
    """Health check endpoint with Llama Stack and moderation status"""
    adapter = get_llama_stack_adapter()

    health_info = {
        "status": "healthy",
        "service": "agentic-orchestrator",
        "version": "0.1.0",
        "hil_mode": adapter.mode.value
    }

    # Check Llama Stack connectivity if enabled
    if adapter.is_enabled():
        try:
            from llama_stack_client import get_llama_stack_client
            llama_client = get_llama_stack_client()
            llama_health = llama_client.health_check()
            health_info["llama_stack"] = {
                "status": "connected",
                "health": llama_health
            }
        except Exception as e:
            health_info["llama_stack"] = {
                "status": "error",
                "error": str(e)
            }

    # Check moderation client connectivity
    try:
        from moderation_client import get_moderation_client
        mod_client = get_moderation_client()

        if mod_client.enabled:
            # Quick health check (timeout=2s)
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{mod_client.endpoint.replace('/v1/moderations', '')}/health")
                response.raise_for_status()
                health_info["moderation"] = {
                    "status": "connected",
                    "endpoint": mod_client.endpoint,
                    "enabled": True
                }
        else:
            health_info["moderation"] = {
                "status": "disabled",
                "enabled": False
            }
    except Exception as e:
        health_info["moderation"] = {
            "status": "error",
            "error": str(e),
            "enabled": True
        }

    return health_info


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Process a user query through the agent with input/output moderation.

    Flow:
    1. Moderate user input (fail-closed)
    2. If blocked: return policy-safe response, skip LLM
    3. If allowed: invoke agent
    4. Moderate agent output (fail-closed)
    5. If blocked: suppress output, return controlled fallback
    6. If allowed: return normal response
    """
    try:
        # Step 1: Input moderation (fail-closed)
        input_result = await moderate_input(request.query)

        if not input_result.is_allowed():
            # BLOCKED INPUT: Return policy-safe response without invoking LLM
            logger.warning(
                f"Input blocked: categories={input_result.get_blocked_categories()}, "
                f"error={input_result.error}"
            )
            return QueryResponse(
                query=request.query,
                response=BLOCKED_INPUT_RESPONSE,
                pending_approval_id=None
            )

        # Log allowed input
        logger.info(f"Input allowed (latency={input_result.latency_ms:.0f}ms)")

        # Step 2: Invoke agent
        result = run_agent(request.query, session_id=request.session_id)

        # Handle both dict and string returns (recursion limit returns string)
        if isinstance(result, dict):
            agent_response = result["response"]
            pending_approval_id = result.get("pending_approval_id")
        else:
            # String fallback (error case)
            agent_response = str(result)
            pending_approval_id = None

        # Step 3: Output moderation (fail-closed)
        output_result = await moderate_output(agent_response)

        if not output_result.is_allowed():
            # BLOCKED OUTPUT: Suppress LLM output, return controlled fallback
            logger.warning(
                f"Output blocked: categories={output_result.get_blocked_categories()}, "
                f"error={output_result.error}"
            )
            return QueryResponse(
                query=request.query,
                response=BLOCKED_OUTPUT_RESPONSE,
                pending_approval_id=pending_approval_id  # Preserve HIL state
            )

        # Log allowed output
        logger.info(f"Output allowed (latency={output_result.latency_ms:.0f}ms)")

        # Step 3.5: If approval was created, attach moderation results
        if pending_approval_id:
            try:
                moderation_data = {
                    "input": {
                        "decision": input_result.decision.value,
                        "flagged": input_result.flagged,
                        "categories": input_result.get_blocked_categories() if input_result.flagged else [],
                        "latency_ms": input_result.latency_ms
                    },
                    "output": {
                        "decision": output_result.decision.value,
                        "flagged": output_result.flagged,
                        "categories": output_result.get_blocked_categories() if output_result.flagged else [],
                        "latency_ms": output_result.latency_ms
                    }
                }

                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{AUDIT_SERVICE_URL}/audit/moderation/{pending_approval_id}",
                        json=moderation_data
                    )
                logger.info(f"Attached moderation results to approval #{pending_approval_id}")
            except Exception as e:
                logger.warning(f"Failed to attach moderation results: {e}")

        # Step 4: Return normal response
        return QueryResponse(
            query=request.query,
            response=agent_response,
            pending_approval_id=pending_approval_id
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

                pr_url = result.get("pr_url", "")
                pr_number = result.get("pr_number", "")

                # Auto-merge the PR since operator approved the git diff
                merge_result = None
                try:
                    from github_client import get_github_client
                    github = get_github_client()
                    merge_result = github.merge_pr(pr_number, merge_method="squash")

                    if merge_result.get("merged"):
                        print(f"✅ Auto-merged PR #{pr_number}: {merge_result.get('message')}")

                        # Publish Kafka event to update console UI immediately
                        publish_policy_promoted_event(
                            factory=factory,
                            version=model_version,
                            trace_id=f"pr-{pr_number}"
                        )
                    else:
                        # Merge failed - mark approval as merge_failed
                        print(f"❌ PR #{pr_number} merge failed: {merge_result.get('error')}")

                        # Call audit service to mark as merge_failed
                        try:
                            client.post(
                                f"{AUDIT_SERVICE_URL}/audit/merge-failed/{approval_id}",
                                json={
                                    "error": merge_result.get("error", "Unknown error"),
                                    "error_type": merge_result.get("error_type", "unknown"),
                                    "status_code": merge_result.get("status_code"),
                                    "pr_number": pr_number
                                }
                            )
                        except Exception as mark_error:
                            print(f"Warning: Failed to mark approval as merge_failed: {mark_error}")

                except Exception as e:
                    # Unexpected exception during merge attempt
                    print(f"⚠️  Exception during auto-merge of PR #{pr_number}: {e}")
                    merge_result = {"merged": False, "error": str(e), "error_type": "unknown"}

                # Update audit record with result (including PR URL and merge status)
                try:
                    client.post(
                        f"{AUDIT_SERVICE_URL}/audit/result/{approval_id}",
                        json={"result": {
                            "status": "merged" if merge_result and not merge_result.get("error") else "pr_created",
                            "data": result,
                            "merge_result": merge_result
                        }}
                    )
                except Exception as e:
                    print(f"Warning: Failed to update audit result: {e}")

                # Response message based on merge success
                if merge_result and merge_result.get("merged"):
                    return ApprovalResumeResponse(
                        response=f"✅ Approved and merged: PR #{pr_number} merged for {factory} → {model_version}. Argo CD will sync shortly. PR URL: {pr_url}",
                        status="approved"
                    )
                else:
                    # Merge failed - provide detailed error message
                    error_type = merge_result.get("error_type", "unknown") if merge_result else "unknown"
                    error_msg = merge_result.get("error", "Unknown error") if merge_result else "Unknown error"

                    # User-friendly error messages
                    friendly_messages = {
                        "conflict": "Merge conflict detected. Manual resolution required.",
                        "not_mergeable": "PR is not in a mergeable state. Check branch protection rules or required checks.",
                        "checks_failed": "Required status checks have not passed. Check CI/CD pipeline.",
                        "unknown": f"Merge failed: {error_msg}"
                    }

                    friendly_msg = friendly_messages.get(error_type, friendly_messages["unknown"])

                    return ApprovalResumeResponse(
                        response=f"⚠️  Approved but merge failed: PR #{pr_number} for {factory} → {model_version}. {friendly_msg} PR URL: {pr_url}",
                        status="merge_failed"
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