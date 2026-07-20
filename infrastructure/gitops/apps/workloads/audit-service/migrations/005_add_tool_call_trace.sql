-- Migration: Add tool_call_trace column to hil_audit table
-- Purpose: Store the sequence of read-only MCP tool calls the agent made before requesting approval
-- Phase: 3 (Milestone 4 - Context Trail)

ALTER TABLE hil_audit
ADD COLUMN IF NOT EXISTS tool_call_trace JSONB;

-- Index for querying traces
CREATE INDEX IF NOT EXISTS idx_hil_audit_tool_trace
ON hil_audit USING GIN (tool_call_trace)
WHERE tool_call_trace IS NOT NULL;

-- Comment explaining the structure
COMMENT ON COLUMN hil_audit.tool_call_trace IS
'Array of read-only tool calls executed before this approval request. Each entry: {tool_name, arguments, response_summary, timestamp_ms, duration_ms}. Shows agent reasoning chain.';
