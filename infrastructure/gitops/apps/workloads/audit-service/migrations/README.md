# HIL Audit Database Migrations

This directory contains SQL migrations for the `hil_audit` table in the `mlflow` database.

## Automatic Migrations

**Migrations are applied automatically** when the audit service starts. The `init_db.py` script runs all `.sql` files in this directory in alphanumeric order (001_*, 002_*, etc.).

No manual intervention is required on new cluster deployments.

## Manual Migration (Fallback)

If you need to apply migrations manually, use `psql` from the CloudNativePG cluster pod.

### Step 1: Get the CloudNativePG primary pod

```bash
PRIMARY_POD=$(oc get pod -n mlflow -l role=primary,cnpg.io/cluster=cnpg-mlflow -o jsonpath='{.items[0].metadata.name}')
echo "Primary pod: $PRIMARY_POD"
```

### Step 2: Apply migration

```bash
# Copy migration file to pod
oc cp 003_add_blast_radius.sql mlflow/$PRIMARY_POD:/tmp/migration.sql

# Execute migration
oc exec -n mlflow $PRIMARY_POD -- psql -d mlflow -f /tmp/migration.sql

# Verify column exists
oc exec -n mlflow $PRIMARY_POD -- psql -d mlflow -c "\d hil_audit"
```

### Step 3: Clean up

```bash
oc exec -n mlflow $PRIMARY_POD -- rm /tmp/migration.sql
```

## Migration History

- **001_create_hil_audit.sql** - Initial table creation (Milestone 2)
- **002_add_git_diff_summary.sql** - Add git_diff, summary, pr_url fields (Milestone 3)
- **003_add_blast_radius.sql** - Add blast_radius field for impact analysis (Milestone 4)
- **004_add_moderation_results.sql** - Add moderation_results field for Llama Guard (Milestone 4)
- **005_add_tool_call_trace.sql** - Add tool_call_trace field for MCP context (Milestone 4)
- **006_add_merge_failure_tracking.sql** - Add merge error tracking (Task #33)
- **007_add_reasoning_summary.sql** - Add reasoning_summary field for agent explanation (Task #40)

## Rollback

Migrations do not have automatic rollback. To rollback a migration:

```sql
-- Example: Remove blast_radius column
ALTER TABLE hil_audit DROP COLUMN IF EXISTS blast_radius;
```
