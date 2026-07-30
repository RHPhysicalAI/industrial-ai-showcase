-- HIL Audit Table Migration 004
-- This project was developed with assistance from AI tools.
--
-- Purpose: Add moderation_results field for guardrails tracking (Milestone 4)
-- Database: mlflow (reuses existing CloudNativePG cluster)

-- Add moderation_results column
-- Stored as JSONB for structured moderation data (input/output checks, categories, latency)
ALTER TABLE hil_audit
ADD COLUMN IF NOT EXISTS moderation_results JSONB;

-- Add index for moderation_results queries
CREATE INDEX IF NOT EXISTS idx_hil_audit_moderation ON hil_audit USING GIN (moderation_results) WHERE moderation_results IS NOT NULL;

-- Add comment
COMMENT ON COLUMN hil_audit.moderation_results IS 'Input/output moderation results: safety checks, flagged categories, latency (Milestone 4)';
