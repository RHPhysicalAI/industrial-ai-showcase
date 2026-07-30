-- HIL Audit Table Migration
-- This project was developed with assistance from AI tools.
--
-- Purpose: Create audit trail table for Human-in-the-Loop (HIL) approval tracking
-- Database: mlflow (reuses existing CloudNativePG cluster)

-- Create hil_audit table
CREATE TABLE IF NOT EXISTS hil_audit (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now() NOT NULL,
    session_id TEXT NOT NULL,
    user_identity TEXT NOT NULL DEFAULT 'demo-operator',
    tool_name TEXT NOT NULL,
    tool_arguments JSONB NOT NULL,
    approval_status TEXT NOT NULL CHECK (approval_status IN ('pending', 'approved', 'rejected')),
    approval_timestamp TIMESTAMPTZ,
    approver_identity TEXT,
    rejection_reason TEXT,
    result JSONB,
    error TEXT
);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_hil_audit_session ON hil_audit(session_id);
CREATE INDEX IF NOT EXISTS idx_hil_audit_timestamp ON hil_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_hil_audit_status ON hil_audit(approval_status);

-- Add comment
COMMENT ON TABLE hil_audit IS 'Audit trail for Human-in-the-Loop approval decisions on state-modifying agentic actions (Phase 3 Milestone 2)';
