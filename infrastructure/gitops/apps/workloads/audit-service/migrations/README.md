# HIL Audit Database Migrations

This directory contains SQL migrations for the `hil_audit` table in the `mlflow` database.

## Applying Migrations

Migrations must be applied manually via `psql` from the CloudNativePG cluster pod.

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

## Rollback

Migrations do not have automatic rollback. To rollback a migration:

```sql
-- Example: Remove blast_radius column
ALTER TABLE hil_audit DROP COLUMN IF EXISTS blast_radius;
```
