-- HIL Audit Table Migration 002
-- This project was developed with assistance from AI tools.
--
-- Purpose: Add git_diff and summary fields for agent-opens-PR pattern (Milestone 3)
-- Database: mlflow (reuses existing CloudNativePG cluster)

-- Add git_diff and summary columns for promote_policy_version tool
ALTER TABLE hil_audit
ADD COLUMN IF NOT EXISTS git_diff TEXT,
ADD COLUMN IF NOT EXISTS summary TEXT,
ADD COLUMN IF NOT EXISTS pr_url TEXT;

-- Add indexes for PR URL queries
CREATE INDEX IF NOT EXISTS idx_hil_audit_pr_url ON hil_audit(pr_url) WHERE pr_url IS NOT NULL;

-- Add comment
COMMENT ON COLUMN hil_audit.git_diff IS 'Git diff preview for promote_policy_version actions (Milestone 3)';
COMMENT ON COLUMN hil_audit.summary IS 'Human-readable summary for promote_policy_version actions (Milestone 3)';
COMMENT ON COLUMN hil_audit.pr_url IS 'GitHub PR URL created after approval (Milestone 3)';
