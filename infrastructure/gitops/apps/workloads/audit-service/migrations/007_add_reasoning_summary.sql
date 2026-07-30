-- Migration 007: Add reasoning_summary column
-- Captures the agent's explanation of WHY it's proposing an action

ALTER TABLE hil_audit
ADD COLUMN reasoning_summary TEXT;

COMMENT ON COLUMN hil_audit.reasoning_summary IS 'Agent''s human-readable explanation of why this action is proposed';
