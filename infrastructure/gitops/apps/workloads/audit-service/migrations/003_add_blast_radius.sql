-- HIL Audit Table Migration 003
-- This project was developed with assistance from AI tools.
--
-- Purpose: Add blast_radius field for impact analysis (Milestone 4)
-- Database: mlflow (reuses existing CloudNativePG cluster)

-- Add blast_radius column for promote_policy_version tool
-- Stored as JSONB for structured impact data (factory, robot_count, versions, etc.)
ALTER TABLE hil_audit
ADD COLUMN IF NOT EXISTS blast_radius JSONB;

-- Add index for blast_radius queries
CREATE INDEX IF NOT EXISTS idx_hil_audit_blast_radius ON hil_audit USING GIN (blast_radius) WHERE blast_radius IS NOT NULL;

-- Add comment
COMMENT ON COLUMN hil_audit.blast_radius IS 'Impact analysis for promote_policy_version actions: factory, robot count, version changes (Milestone 4)';
