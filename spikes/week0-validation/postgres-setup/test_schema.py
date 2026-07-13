#!/usr/bin/env python3
"""
Postgres Schema Validation - Week 0 Day 3

Tests JSONB inserts/queries for agent_sessions and hil_audit tables.

Prerequisites:
1. Postgres pod running: oc get pod -n agentic-ops -l app=postgres
2. Port-forward active: oc port-forward svc/postgres 5432:5432 -n agentic-ops
3. Schema loaded: psql ... < schema.sql

Usage:
    pip install psycopg2-binary  # or use uv
    python test_schema.py

Expected output:
    ✅ All 6 tests passed
"""
# This project was developed with assistance from AI tools.

import json
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg2
    import psycopg2.extensions
    from psycopg2.extras import RealDictCursor, Json, register_uuid

    # Register UUID adapter
    register_uuid()
except ImportError:
    print("Error: psycopg2 not installed")
    print("Install with: pip install psycopg2-binary")
    print("Or with uv: uv pip install psycopg2-binary")
    exit(1)


# Connection string
CONN_STRING = "postgresql://agent:changeme123@localhost:5432/agentic_orchestrator"


def test_agent_session_insert() -> None:
    """Test 1: Insert agent session with JSONB state"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    session_id = uuid.uuid4()
    state = {
        "graph": "fleet_manager_agent",
        "checkpoint": {
            "messages": [
                {"role": "user", "content": "Show me robot status"},
                {"role": "assistant", "content": "I'll check the fleet API"},
            ],
            "next_step": "call_fleet_api",
        },
    }

    cur.execute(
        """
        INSERT INTO agent_sessions (session_id, operator_identity, state)
        VALUES (%s, %s, %s)
        RETURNING session_id, started_at
        """,
        (session_id, "CN=John Doe,OU=Engineering,O=Red Hat", Json(state)),
    )

    result = cur.fetchone()
    assert result["session_id"] == session_id
    print(f"✅ Test 1: Inserted agent session {session_id}")

    conn.commit()
    cur.close()
    conn.close()


def test_agent_session_query() -> None:
    """Test 2: Query JSONB state with PostgreSQL operators"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Find sessions where graph = "fleet_manager_agent"
    cur.execute(
        """
        SELECT session_id, operator_identity, state->>'graph' as graph_name
        FROM agent_sessions
        WHERE state->>'graph' = 'fleet_manager_agent'
        """
    )

    results = cur.fetchall()
    assert len(results) > 0, "Should find at least one fleet_manager_agent session"
    print(f"✅ Test 2: Found {len(results)} fleet manager sessions")

    cur.close()
    conn.close()


def test_audit_trail_append() -> None:
    """Test 3: Append to JSONB[] audit_trail array"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get a session ID
    cur.execute("SELECT session_id FROM agent_sessions LIMIT 1")
    session_id = cur.fetchone()["session_id"]

    # Append a tool call to audit_trail
    tool_call = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "mcp.fleet_status",
        "args": {"robot_id": "robot-001"},
        "result": {"status": "operational", "battery": 85},
    }

    cur.execute(
        """
        UPDATE agent_sessions
        SET audit_trail = audit_trail || %s::jsonb,
            updated_at = NOW()
        WHERE session_id = %s
        RETURNING array_length(audit_trail, 1) as trail_length
        """,
        (Json(tool_call), session_id),
    )

    result = cur.fetchone()
    assert result["trail_length"] >= 1
    print(f"✅ Test 3: Appended to audit trail (length={result['trail_length']})")

    conn.commit()
    cur.close()
    conn.close()


def test_hil_audit_insert() -> None:
    """Test 4: Insert HIL audit record with guardrails"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get a session ID
    cur.execute("SELECT session_id FROM agent_sessions LIMIT 1")
    session_id = cur.fetchone()["session_id"]

    action_id = uuid.uuid4()
    tool_call = {
        "tool": "mcp.update_robot_config",
        "args": {"robot_id": "robot-001", "speed_limit": 0.5},
    }
    guardrail_results = {
        "pii_scan": {"found_pii": False},
        "safety_check": {"risk_level": "low"},
        "scope_check": {"approved_namespace": True},
    }

    cur.execute(
        """
        INSERT INTO hil_audit (
            action_id, session_id, operator_identity,
            tool_call, classification, guardrail_results,
            decision, context_trail_hash
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING action_id, timestamp
        """,
        (
            action_id,
            session_id,
            "CN=John Doe,OU=Engineering,O=Red Hat",
            Json(tool_call),
            "state-modifying",
            Json(guardrail_results),
            "approved",
            "sha256:abc123def456",  # Mock hash
        ),
    )

    result = cur.fetchone()
    assert result["action_id"] == action_id
    print(f"✅ Test 4: Inserted HIL audit record {action_id}")

    conn.commit()
    cur.close()
    conn.close()


def test_hil_audit_query() -> None:
    """Test 5: Query HIL audit by classification and decision"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Find all approved state-modifying actions
    cur.execute(
        """
        SELECT action_id, tool_call->>'tool' as tool_name, decision
        FROM hil_audit
        WHERE classification = 'state-modifying'
          AND decision = 'approved'
        ORDER BY timestamp DESC
        """
    )

    results = cur.fetchall()
    assert len(results) > 0, "Should find at least one approved action"
    print(f"✅ Test 5: Found {len(results)} approved state-modifying actions")

    cur.close()
    conn.close()


def test_jsonb_deep_query() -> None:
    """Test 6: Deep JSONB path query (nested object access)"""
    conn = psycopg2.connect(CONN_STRING)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Query nested JSONB: state->'checkpoint'->'next_step'
    cur.execute(
        """
        SELECT session_id, state#>>'{checkpoint,next_step}' as next_step
        FROM agent_sessions
        WHERE state#>>'{checkpoint,next_step}' IS NOT NULL
        LIMIT 1
        """
    )

    result = cur.fetchone()
    if result:
        print(f"✅ Test 6: Deep JSONB query works (next_step={result['next_step']})")
    else:
        print("✅ Test 6: Deep JSONB query works (no matching records, but syntax is valid)")

    cur.close()
    conn.close()


def main():
    """Run all tests"""
    tests = [
        test_agent_session_insert,
        test_agent_session_query,
        test_audit_trail_append,
        test_hil_audit_insert,
        test_hil_audit_query,
        test_jsonb_deep_query,
    ]

    print("Starting Postgres schema validation...\n")

    try:
        for test in tests:
            test()

        print("\n" + "="*50)
        print("✅ All 6 tests passed!")
        print("="*50)
        print("\nPostgres schema is validated for Phase 3.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("\nTroubleshooting:")
        print("1. Is Postgres pod running? oc get pod -n agentic-ops -l app=postgres")
        print("2. Is port-forward active? oc port-forward svc/postgres 5432:5432 -n agentic-ops")
        print("3. Is schema loaded? psql ... < schema.sql")
        raise


if __name__ == "__main__":
    main()