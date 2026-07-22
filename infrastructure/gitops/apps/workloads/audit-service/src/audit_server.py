#!/usr/bin/env python3
"""
Audit Service - HIL Approval Tracking

This project was developed with assistance from AI tools.

Purpose: Manage Human-in-the-Loop (HIL) approval requests and persist audit trail
for state-modifying agentic actions.

Endpoints:
- POST /audit/pending - Create pending approval request
- GET /audit/pending - List all pending approvals
- POST /audit/approve/{id} - Approve request
- POST /audit/reject/{id} - Reject request
- GET /audit/history - Query audit history
- GET /health - Health check
"""

import os
import uvicorn
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor, Json

app = FastAPI(
    title="Audit Service",
    description="HIL approval tracking and audit trail for agentic actions",
    version="0.1.0"
)


# --- Database Connection ---

def get_db_connection():
    """Get PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "mlflow-db-rw.mlflow.svc.cluster.local"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "mlflow"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "mlflow")
    )


# --- Pydantic Models ---

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str


class CreateApprovalRequest(BaseModel):
    session_id: str
    user_identity: str = "demo-operator"
    tool_name: str
    tool_arguments: dict
    git_diff: Optional[str] = None  # For promote_policy_version (Milestone 3)
    summary: Optional[str] = None   # For promote_policy_version (Milestone 3)
    blast_radius: Optional[dict] = None  # For promote_policy_version (Milestone 4)
    tool_call_trace: Optional[list] = None  # Read-only tool calls before approval (Milestone 4)
    reasoning_summary: Optional[str] = None  # Agent's explanation of WHY (Milestone 4)


class ApprovalRequest(BaseModel):
    id: int
    timestamp: str
    session_id: str
    user_identity: str
    tool_name: str
    tool_arguments: dict
    approval_status: str
    git_diff: Optional[str] = None  # For promote_policy_version
    summary: Optional[str] = None   # For promote_policy_version
    blast_radius: Optional[dict] = None  # For promote_policy_version (Milestone 4)
    moderation_results: Optional[dict] = None  # Input/output moderation (Milestone 4)
    tool_call_trace: Optional[list] = None  # Read-only tool calls before approval (Milestone 4)
    reasoning_summary: Optional[str] = None  # Agent's explanation of WHY (Milestone 4)
    pr_url: Optional[str] = None    # After approval creates PR


class ApproveRequest(BaseModel):
    approver_identity: str = "demo-operator"


class RejectRequest(BaseModel):
    approver_identity: str = "demo-operator"
    reason: str


class MergeFailedRequest(BaseModel):
    error: str
    error_type: str  # "conflict", "not_mergeable", "checks_failed", "unknown"
    status_code: Optional[int] = None
    pr_number: Optional[int] = None


class AuditHistoryResponse(BaseModel):
    history: List[dict]


# --- Health Check ---

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint with database connectivity test."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "audit-service",
        "version": "0.1.0",
        "database": db_status
    }


# --- Approval Management ---

@app.post("/audit/pending", response_model=dict)
async def create_pending_approval(request: CreateApprovalRequest):
    """
    Create a pending approval request.

    Returns: Created approval request with ID
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            INSERT INTO hil_audit (
                session_id, user_identity, tool_name, tool_arguments, approval_status,
                git_diff, summary, blast_radius, tool_call_trace, reasoning_summary
            )
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s)
            RETURNING id, timestamp, session_id, user_identity, tool_name,
                      tool_arguments, approval_status, git_diff, summary, blast_radius,
                      tool_call_trace, reasoning_summary, pr_url
            """,
            (
                request.session_id,
                request.user_identity,
                request.tool_name,
                Json(request.tool_arguments),
                request.git_diff,
                request.summary,
                Json(request.blast_radius) if request.blast_radius else None,
                Json(request.tool_call_trace) if request.tool_call_trace else None,
                request.reasoning_summary
            )
        )

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "id": result["id"],
            "timestamp": result["timestamp"].isoformat(),
            "session_id": result["session_id"],
            "user_identity": result["user_identity"],
            "tool_name": result["tool_name"],
            "tool_arguments": result["tool_arguments"],
            "approval_status": result["approval_status"],
            "reasoning_summary": result.get("reasoning_summary")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create approval request: {str(e)}")


@app.get("/audit/pending", response_model=dict)
async def list_pending_approvals():
    """
    List all pending approval requests.

    Returns: List of pending approvals
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT id, timestamp, session_id, user_identity, tool_name,
                   tool_arguments, approval_status, git_diff, summary, blast_radius,
                   moderation_results, pr_url
            FROM hil_audit
            WHERE approval_status = 'pending'
            ORDER BY timestamp ASC
            """
        )

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        pending = [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "session_id": row["session_id"],
                "user_identity": row["user_identity"],
                "tool_name": row["tool_name"],
                "tool_arguments": row["tool_arguments"],
                "approval_status": row["approval_status"],
                "git_diff": row.get("git_diff"),
                "summary": row.get("summary"),
                "blast_radius": row.get("blast_radius"),
                "moderation_results": row.get("moderation_results"),
                "pr_url": row.get("pr_url")
            }
            for row in results
        ]

        return {"pending": pending}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list pending approvals: {str(e)}")


@app.post("/audit/approve/{approval_id}")
async def approve_request(approval_id: int, request: ApproveRequest):
    """
    Approve a pending request.

    Updates approval_status to 'approved', records approver and timestamp.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE hil_audit
            SET approval_status = 'approved',
                approval_timestamp = %s,
                approver_identity = %s
            WHERE id = %s AND approval_status = 'pending'
            RETURNING id
            """,
            (datetime.now(timezone.utc), request.approver_identity, approval_id)
        )

        result = cursor.fetchone()

        if result is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Pending approval {approval_id} not found")

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "approved", "id": approval_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve request: {str(e)}")


@app.post("/audit/reject/{approval_id}")
async def reject_request(approval_id: int, request: RejectRequest):
    """
    Reject a pending request.

    Updates approval_status to 'rejected', records approver, timestamp, and reason.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE hil_audit
            SET approval_status = 'rejected',
                approval_timestamp = %s,
                approver_identity = %s,
                rejection_reason = %s
            WHERE id = %s AND approval_status = 'pending'
            RETURNING id
            """,
            (
                datetime.now(timezone.utc),
                request.approver_identity,
                request.reason,
                approval_id
            )
        )

        result = cursor.fetchone()

        if result is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Pending approval {approval_id} not found")

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "rejected", "id": approval_id, "reason": request.reason}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject request: {str(e)}")


@app.post("/audit/merge-failed/{approval_id}")
async def mark_merge_failed(approval_id: int, request: MergeFailedRequest):
    """
    Mark an approved request as merge_failed when PR merge fails.

    Updates approval_status to 'merge_failed' and stores error details.
    This allows retries and provides troubleshooting information.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        merge_error_data = {
            "error": request.error,
            "error_type": request.error_type,
            "status_code": request.status_code,
            "pr_number": request.pr_number,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        cursor.execute(
            """
            UPDATE hil_audit
            SET approval_status = 'merge_failed',
                merge_error = %s
            WHERE id = %s AND approval_status = 'approved'
            RETURNING id
            """,
            (Json(merge_error_data), approval_id)
        )

        result = cursor.fetchone()

        if result is None:
            conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"Approved request {approval_id} not found (may have already been processed)"
            )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "merge_failed",
            "id": approval_id,
            "error": request.error,
            "error_type": request.error_type
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark merge failed: {str(e)}")


@app.post("/audit/moderation/{approval_id}")
async def attach_moderation_results(approval_id: int, moderation_data: dict):
    """
    Attach moderation results to an approval request.

    Called by orchestrator after creating approval to add input/output moderation data.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE hil_audit
            SET moderation_results = %s
            WHERE id = %s
            RETURNING id
            """,
            (Json(moderation_data), approval_id)
        )

        updated = cursor.fetchone()

        if updated is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "updated", "id": approval_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to attach moderation results: {str(e)}")


@app.post("/audit/result/{approval_id}")
async def update_result(approval_id: int, result: dict):
    """
    Update approval record with execution result.

    Called after tool execution completes.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE hil_audit
            SET result = %s
            WHERE id = %s
            RETURNING id
            """,
            (Json(result), approval_id)
        )

        updated = cursor.fetchone()

        if updated is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "updated", "id": approval_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update result: {str(e)}")


@app.get("/audit/history", response_model=AuditHistoryResponse)
async def query_audit_history(limit: int = 10, session_id: Optional[str] = None):
    """
    Query audit history.

    Returns recent audit records (approved and rejected).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if session_id:
            cursor.execute(
                """
                SELECT id, timestamp, session_id, user_identity, tool_name,
                       tool_arguments, approval_status, approval_timestamp,
                       approver_identity, rejection_reason, result
                FROM hil_audit
                WHERE session_id = %s AND approval_status IN ('approved', 'rejected')
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (session_id, limit)
            )
        else:
            cursor.execute(
                """
                SELECT id, timestamp, session_id, user_identity, tool_name,
                       tool_arguments, approval_status, approval_timestamp,
                       approver_identity, rejection_reason, result
                FROM hil_audit
                WHERE approval_status IN ('approved', 'rejected')
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,)
            )

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        history = [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "session_id": row["session_id"],
                "user_identity": row["user_identity"],
                "tool_name": row["tool_name"],
                "tool_arguments": row["tool_arguments"],
                "approval_status": row["approval_status"],
                "approval_timestamp": row["approval_timestamp"].isoformat() if row["approval_timestamp"] else None,
                "approver_identity": row["approver_identity"],
                "rejection_reason": row["rejection_reason"],
                "result": row["result"]
            }
            for row in results
        ]

        return {"history": history}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query history: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8090,
        log_level="info"
    )
