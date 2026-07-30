-- Migration: Add merge failure tracking to hil_audit table
-- Purpose: Store PR merge errors for troubleshooting and retry logic
-- Phase: 3 (Task #33 - PR merge failure handling)

ALTER TABLE hil_audit
ADD COLUMN IF NOT EXISTS merge_error JSONB;

-- Index for querying merge failures
CREATE INDEX IF NOT EXISTS idx_hil_audit_merge_error
ON hil_audit USING GIN (merge_error)
WHERE merge_error IS NOT NULL;

-- Comment explaining the structure
COMMENT ON COLUMN hil_audit.merge_error IS
'Details of PR merge failure: {error: str, error_type: "conflict"|"not_mergeable"|"checks_failed"|"unknown", status_code: int, timestamp: ISO datetime}';

-- Expand approval_status CHECK to include merge_failed
ALTER TABLE hil_audit DROP CONSTRAINT IF EXISTS hil_audit_approval_status_check;
ALTER TABLE hil_audit ADD CONSTRAINT hil_audit_approval_status_check
  CHECK (approval_status IN ('pending', 'approved', 'rejected', 'merge_failed'));
