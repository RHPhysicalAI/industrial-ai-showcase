-- Agent State Schema for Phase 3
-- This project was developed with assistance from AI tools.

-- Drop tables if they exist (for testing)
DROP TABLE IF EXISTS hil_audit CASCADE;
DROP TABLE IF EXISTS agent_sessions CASCADE;

-- Agent sessions table
-- Stores LangGraph agent session state
CREATE TABLE agent_sessions (
  session_id UUID PRIMARY KEY,
  operator_identity TEXT NOT NULL,  -- OAuth sub or CAC/PIV DN
  started_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  state JSONB NOT NULL,  -- LangGraph checkpointer state (opaque blob)
  audit_trail JSONB[] NOT NULL DEFAULT '{}'  -- Array of tool calls + results
);

-- Index for querying sessions by operator
CREATE INDEX idx_agent_sessions_operator ON agent_sessions(operator_identity);

-- Index for querying recent sessions
CREATE INDEX idx_agent_sessions_updated ON agent_sessions(updated_at DESC);

-- HIL audit trail table
-- Immutable record of all human-in-the-loop approvals/rejections
CREATE TABLE hil_audit (
  action_id UUID PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
  session_id UUID REFERENCES agent_sessions(session_id),
  operator_identity TEXT NOT NULL,  -- CAC/PIV cert DN or OAuth sub
  tool_call JSONB NOT NULL,  -- Full tool call details
  classification TEXT NOT NULL CHECK (classification IN ('read-only', 'state-modifying')),
  guardrail_results JSONB NOT NULL,  -- PII scan, safety checks, etc.
  decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
  rejection_reason TEXT,  -- Required if decision='rejected'
  pr_url TEXT,  -- GitHub PR URL if agent-opens-PR pattern
  context_trail_hash TEXT NOT NULL  -- SHA256 of MCP trace for integrity
);

-- Index for audit queries by operator
CREATE INDEX idx_hil_audit_operator ON hil_audit(operator_identity);

-- Index for audit queries by timestamp
CREATE INDEX idx_hil_audit_timestamp ON hil_audit(timestamp DESC);

-- Index for finding approved/rejected actions
CREATE INDEX idx_hil_audit_decision ON hil_audit(decision);

-- Add comments for documentation
COMMENT ON TABLE agent_sessions IS 'LangGraph agent session state with JSONB audit trail';
COMMENT ON TABLE hil_audit IS 'Immutable human-in-the-loop approval audit log';

COMMENT ON COLUMN agent_sessions.state IS 'LangGraph checkpointer state - opaque JSONB blob';
COMMENT ON COLUMN agent_sessions.audit_trail IS 'Array of tool calls and results for this session';
COMMENT ON COLUMN hil_audit.context_trail_hash IS 'SHA256 hash of MCP trace for tamper detection';

-- Schema loaded successfully
-- Use psql to view schema: \dt, \d agent_sessions, \d hil_audit