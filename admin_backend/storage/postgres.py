"""
PostgreSQL storage implementations for admin backend.
Provides persistent storage with separate admin and user tables.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from admin_backend.config import settings
from admin_backend.models.audit import AuditLogEntry, AuditLogFilter, AuditAction
from admin_backend.models.auth import UserRecord, UserRole
from admin_backend.storage.interfaces import (
    UserStorageInterface,
    AuditStorageInterface,
)

log = logging.getLogger("admin_backend.storage.postgres")

# Separate table names for admin and user
ADMIN_USERS_TABLE = "admin_users"
USER_USERS_TABLE = "app_users"
AUDIT_LOGS_TABLE = "audit_logs"

# Table name constants
ADMIN_USERS_TABLE = "admin_users"
USER_USERS_TABLE = "app_users"
AUDIT_LOGS_TABLE = "audit_logs"

CREATE_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

-- Admin users table (for admin portal access)
CREATE TABLE IF NOT EXISTS {admin_users} (
    id UUID PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Application users table (for regular users)
CREATE TABLE IF NOT EXISTS {user_users} (
    id UUID PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Audit logs table
CREATE TABLE IF NOT EXISTS {audit_logs} (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    actor_username VARCHAR(100) NOT NULL,
    actor_role VARCHAR(20) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    details JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    client_ip VARCHAR(45)
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON {audit_logs} (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON {audit_logs} (actor_username);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON {audit_logs} (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON {audit_logs} (resource_type, resource_id);
""".format(
    admin_users=ADMIN_USERS_TABLE,
    user_users=USER_USERS_TABLE,
    audit_logs=AUDIT_LOGS_TABLE,
)


class PostgresUserStorage(UserStorageInterface):
    """PostgreSQL storage for users with separate admin and user tables."""

    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or settings.postgres_dsn
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self):
        conn = psycopg.connect(self._dsn, connect_timeout=2, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _init_schema(self):
        """Initialize database schema."""
        try:
            with self._connect() as conn:
                conn.execute(CREATE_TABLES_SQL)
                conn.commit()
            log.info("PostgreSQL admin schema initialized")
        except Exception as e:
            log.warning(f"Could not initialize PostgreSQL schema: {e}")

    def _get_table(self, role: str) -> str:
        """Get the appropriate table name based on role."""
        if role == "admin":
            return ADMIN_USERS_TABLE
        return USER_USERS_TABLE

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        if not username:
            return None
        key = username.strip().lower()
        try:
            with self._connect() as conn:
                # Check admin table first
                row = conn.execute(
                    f"SELECT * FROM {ADMIN_USERS_TABLE} WHERE LOWER(username) = %s OR LOWER(email) = %s",
                    (key, key)
                ).fetchone()
                if row:
                    row['role'] = 'admin'
                    return dict(row)

                # Then check user table
                row = conn.execute(
                    f"SELECT * FROM {USER_USERS_TABLE} WHERE LOWER(username) = %s OR LOWER(email) = %s",
                    (key, key)
                ).fetchone()
                if row:
                    row['role'] = 'user'
                    return dict(row)
        except Exception as e:
            log.warning(f"Postgres user lookup failed: {e}")
        return None

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                # Check admin table
                row = conn.execute(
                    f"SELECT * FROM {ADMIN_USERS_TABLE} WHERE id = %s",
                    (user_id,)
                ).fetchone()
                if row:
                    row['role'] = 'admin'
                    return dict(row)

                # Check user table
                row = conn.execute(
                    f"SELECT * FROM {USER_USERS_TABLE} WHERE id = %s",
                    (user_id,)
                ).fetchone()
                if row:
                    row['role'] = 'user'
                    return dict(row)
        except Exception as e:
            log.warning(f"Postgres user lookup by ID failed: {e}")
        return None

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        role = user_data.get("role", "user")
        table = self._get_table(role)
        try:
            with self._connect() as conn:
                conn.execute(
                    f"""
                    INSERT INTO {table} (id, username, email, hashed_password, role, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        email = EXCLUDED.email,
                        hashed_password = EXCLUDED.hashed_password,
                        role = EXCLUDED.role,
                        is_active = EXCLUDED.is_active
                    """,
                    (
                        user_data["id"],
                        user_data["username"],
                        user_data.get("email"),
                        user_data["hashed_password"],
                        user_data["role"],
                        user_data.get("is_active", True),
                        user_data.get("created_at", datetime.now(timezone.utc)),
                    )
                )
                conn.commit()
            log.info(f"Created/updated {role} user: {user_data['username']}")
        except Exception as e:
            log.warning(f"Postgres user creation failed: {e}")
        return user_data


class PostgresAuditStorage(AuditStorageInterface):
    """PostgreSQL storage for audit logs with persistence."""

    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or settings.postgres_dsn
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self):
        conn = psycopg.connect(self._dsn, connect_timeout=2, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _init_schema(self):
        """Initialize audit logs table."""
        try:
            with self._connect() as conn:
                conn.execute(CREATE_TABLES_SQL)
                conn.commit()
            log.info("PostgreSQL audit schema initialized")
        except Exception as e:
            log.warning(f"Could not initialize PostgreSQL audit schema: {e}")

    def append_audit_entry(self, entry: AuditLogEntry) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    f"""
                    INSERT INTO {AUDIT_LOGS_TABLE}
                    (id, timestamp, actor_username, actor_role, action, resource_type, resource_id, status, details, client_ip)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry.id,
                        entry.timestamp,
                        entry.actor_username,
                        entry.actor_role,
                        entry.action.value if hasattr(entry.action, 'value') else entry.action,
                        entry.resource_type,
                        entry.resource_id,
                        entry.status,
                        json.dumps(entry.details),
                        entry.client_ip,
                    )
                )
                conn.commit()
        except Exception as e:
            log.warning(f"Could not write audit log to PostgreSQL: {e}")

    def query_audit_entries(self, filter_opts: AuditLogFilter) -> List[AuditLogEntry]:
        try:
            with self._connect() as conn:
                sql = f"SELECT * FROM {AUDIT_LOGS_TABLE} WHERE 1=1"
                params = []

                if filter_opts.actor:
                    sql += " AND LOWER(actor_username) = LOWER(%s)"
                    params.append(filter_opts.actor)
                if filter_opts.action:
                    sql += " AND action = %s"
                    params.append(filter_opts.action.value if hasattr(filter_opts.action, 'value') else filter_opts.action)
                if filter_opts.resource_type:
                    sql += " AND resource_type = %s"
                    params.append(filter_opts.resource_type)
                if filter_opts.status:
                    sql += " AND status = %s"
                    params.append(filter_opts.status)

                sql += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
                params.extend([filter_opts.limit, filter_opts.offset])

                rows = conn.execute(sql, params).fetchall()

                entries = []
                for row in rows:
                    entries.append(AuditLogEntry(
                        id=row["id"],
                        timestamp=row["timestamp"].isoformat() if hasattr(row["timestamp"], 'isoformat') else str(row["timestamp"]),
                        actor_username=row["actor_username"],
                        actor_role=row["actor_role"],
                        action=AuditAction(row["action"]),
                        resource_type=row["resource_type"],
                        resource_id=row["resource_id"],
                        status=row["status"],
                        details=row["details"] if isinstance(row["details"], dict) else json.loads(row["details"]),
                        client_ip=row["client_ip"],
                    ))
                return entries
        except Exception as e:
            log.warning(f"Could not query audit logs from PostgreSQL: {e}")
            return []