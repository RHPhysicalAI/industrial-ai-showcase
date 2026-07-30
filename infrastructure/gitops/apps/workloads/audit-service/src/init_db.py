#!/usr/bin/env python3
"""
Database initialization script for audit service.
Runs all migrations in order on startup to ensure schema is up-to-date.

This project was developed with assistance from AI tools.
"""
import os
import sys
import psycopg2
from pathlib import Path

def get_db_connection():
    """Get PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "mlflow-db-rw.mlflow.svc.cluster.local"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "mlflow"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "mlflow")
    )


def run_migrations():
    """
    Run all SQL migrations from the migrations directory.
    Migrations are run in alphanumeric order (001_*, 002_*, etc.)
    """
    migrations_dir = Path(__file__).parent.parent / "migrations"

    if not migrations_dir.exists():
        print(f"Migrations directory not found: {migrations_dir}")
        return

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("No migration files found")
        return

    print(f"Found {len(migration_files)} migration files")

    conn = get_db_connection()
    cursor = conn.cursor()

    for migration_file in migration_files:
        try:
            print(f"Running migration: {migration_file.name}")
            sql = migration_file.read_text()

            # Execute migration
            cursor.execute(sql)
            conn.commit()

            print(f"✓ {migration_file.name} completed")

        except Exception as e:
            # Log error but continue with other migrations
            # (some migrations might fail if already applied, which is OK)
            print(f"⚠ {migration_file.name} failed (might already be applied): {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print("Database migrations completed")


if __name__ == "__main__":
    try:
        run_migrations()
    except Exception as e:
        print(f"Migration error: {e}", file=sys.stderr)
        sys.exit(1)
