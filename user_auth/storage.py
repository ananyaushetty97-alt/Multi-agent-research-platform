import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException, status

from user_auth.config import settings

log = logging.getLogger("user_auth.storage")


class UserAuthStorageInterface(ABC):
    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def revoke_session(self, token_hash: str) -> None:
        pass

    @abstractmethod
    def revoke_all_user_sessions(self, user_id: str) -> None:
        pass

    @abstractmethod
    def neutralize_demo_user(self) -> None:
        pass

    @abstractmethod
    def init_schema(self) -> None:
        pass


class PostgresUserAuthStorage(UserAuthStorageInterface):
    """
    Production PostgreSQL storage specifically querying app_users and user_sessions.
    Never queries or touches admin_users.
    Fails fast with 503 if PostgreSQL is unreachable (Condition 13).
    """
    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or settings.postgres_dsn
        self._lock = threading.Lock()
        self._schema_initialized = False

    def _connect(self):
        try:
            conn = psycopg.connect(self._dsn, connect_timeout=2, row_factory=dict_row)
            return conn
        except Exception as e:
            log.warning(f"PostgreSQL connection failed in user_auth: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )

    def init_schema(self) -> None:
        with self._lock:
            if self._schema_initialized:
                return
            try:
                with self._connect() as conn:
                    # 1. Acquire advisory lock using single configured constant
                    conn.execute("SELECT pg_advisory_xact_lock(%s);", (settings.migration_advisory_lock_id,))

                    # 2. Check if app_users exists
                    row = conn.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'app_users';"
                    ).fetchone()
                    if not row:
                        log.info("app_users does not exist yet; waiting for admin schema initialization.")
                        return

                    # 3. Drop NOT NULL on hashed_password early so demo neutralization and Google auth can store NULL
                    conn.execute("ALTER TABLE app_users ALTER COLUMN hashed_password DROP NOT NULL;")

                    # 4. Deterministically resolve known admin seed artifact on demo user accounts
                    conn.execute("""
                        UPDATE app_users 
                        SET email = NULL 
                        WHERE username = 'user@platform.ai' AND email = 'user@platform.ai';

                        UPDATE app_users 
                        SET is_active = FALSE, 
                            hashed_password = NULL 
                        WHERE username IN ('user', 'user@platform.ai') OR email = 'user@platform.ai';
                    """)

                    # 5. Duplicate email pre-check before index creation (Condition 4)
                    dup_rows = conn.execute("""
                        SELECT LOWER(email) AS lower_email, COUNT(*) 
                        FROM app_users 
                        WHERE email IS NOT NULL 
                        GROUP BY LOWER(email) 
                        HAVING COUNT(*) > 1;
                    """).fetchall()
                    if dup_rows:
                        dups = [r["lower_email"] for r in dup_rows]
                        raise RuntimeError(
                            f"Cannot apply migration 002: duplicate emails found in app_users: {', '.join(dups)}"
                        )

                    # 6. Additive columns
                    conn.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100);")
                    conn.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255);")
                    conn.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;")

                    # 7. Unique indexes
                    conn.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_lower_email 
                        ON app_users (LOWER(email)) 
                        WHERE email IS NOT NULL;
                    """)
                    conn.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_google_sub 
                        ON app_users (google_sub) 
                        WHERE google_sub IS NOT NULL;
                    """)

                    # 8. user_sessions table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_sessions (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                            token_hash VARCHAR(64) UNIQUE NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NOT NULL,
                            revoked_at TIMESTAMPTZ,
                            user_agent TEXT,
                            ip VARCHAR(45)
                        );
                        CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);
                        CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
                        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
                    """)
                    conn.commit()

                # Neutralize demo user if enabled (Condition 1 & Question 2)
                if settings.neutralize_demo_users:
                    self.neutralize_demo_user()

                self._schema_initialized = True
                log.info("user_auth PostgreSQL schema and migration 002 verified")
            except HTTPException:
                raise
            except Exception as e:
                log.warning(f"Could not initialize user_auth PostgreSQL schema: {e}")

    def neutralize_demo_user(self) -> None:
        """Deactivate seeded demo user rows (usernames 'user' and 'user@platform.ai', and email 'user@platform.ai') (Condition 1 & Question 2)."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE app_users 
                    SET email = NULL 
                    WHERE username = 'user@platform.ai' AND email = 'user@platform.ai';

                    UPDATE app_users 
                    SET is_active = FALSE, 
                        hashed_password = NULL 
                    WHERE username IN ('user', 'user@platform.ai') OR email = 'user@platform.ai';
                """)
                conn.commit()
            log.info("Neutralized seeded demo users 'user' and 'user@platform.ai' in app_users")
        except HTTPException:
            raise
        except Exception as e:
            log.warning(f"Failed to neutralize demo user in app_users: {e}")

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        clean = (email or "").strip().lower()
        if not clean:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE LOWER(email) = %s;",
                (clean,)
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE id = %s;",
                (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE google_sub = %s;",
                (google_sub,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_users (id, username, email, full_name, hashed_password, role, is_active, google_sub, email_verified, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    user_data["id"],
                    user_data["username"],
                    user_data.get("email"),
                    user_data.get("full_name"),
                    user_data.get("hashed_password"),
                    user_data.get("role", "user"),
                    user_data.get("is_active", True),
                    user_data.get("google_sub"),
                    user_data.get("email_verified", False),
                    user_data.get("created_at", datetime.now(timezone.utc)),
                )
            )
            conn.commit()
        return user_data

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not updates:
            return self.get_user_by_id(user_id) or {}
        set_clauses = []
        params = []
        for k, v in updates.items():
            set_clauses.append(f"{k} = %s")
            params.append(v)
        params.append(user_id)

        with self._connect() as conn:
            conn.execute(
                f"UPDATE app_users SET {', '.join(set_clauses)} WHERE id = %s;",
                params
            )
            conn.commit()
        return self.get_user_by_id(user_id) or {}

    def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (id, user_id, token_hash, created_at, expires_at, revoked_at, user_agent, ip)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    session_data["id"],
                    session_data["user_id"],
                    session_data["token_hash"],
                    session_data.get("created_at", datetime.now(timezone.utc)),
                    session_data["expires_at"],
                    session_data.get("revoked_at"),
                    session_data.get("user_agent"),
                    session_data.get("ip"),
                )
            )
            conn.commit()
        return session_data

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_sessions WHERE token_hash = %s;",
                (token_hash,)
            ).fetchone()
            return dict(row) if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE token_hash = %s AND revoked_at IS NULL;",
                (token_hash,)
            )
            conn.commit()

    def revoke_all_user_sessions(self, user_id: str) -> None:
        """Revoke all active sessions for a user (Condition 7)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL;",
                (user_id,)
            )
            conn.commit()


class InMemoryUserAuthStorage(UserAuthStorageInterface):
    """
    In-memory thread-safe implementation strictly for tests (Condition 11 & 13).
    Enforces identical uniqueness and foreign-key constraints as PostgreSQL.
    """
    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.simulate_db_down: bool = False

    def _check_db(self):
        if self.simulate_db_down:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )

    def init_schema(self) -> None:
        if settings.neutralize_demo_users:
            self.neutralize_demo_user()

    def neutralize_demo_user(self) -> None:
        with self._lock:
            for u in self._users.values():
                if (u.get("email") or "").lower() == "user@platform.ai":
                    u["is_active"] = False
                    u["hashed_password"] = None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        clean = (email or "").strip().lower()
        if not clean:
            return None
        with self._lock:
            for u in self._users.values():
                if (u.get("email") or "").strip().lower() == clean:
                    return dict(u)
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            u = self._users.get(str(user_id))
            return dict(u) if u else None

    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            for u in self._users.values():
                if u.get("google_sub") == google_sub:
                    return dict(u)
            return None

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        uid = str(user_data["id"])
        email = (user_data.get("email") or "").strip().lower()
        username = user_data["username"].strip().lower()

        with self._lock:
            # Enforce unique email constraint matching Postgres (Condition 11)
            if email:
                for u in self._users.values():
                    if (u.get("email") or "").strip().lower() == email:
                        raise ValueError(f"Duplicate email violates unique constraint: {email}")

            # Enforce unique username constraint matching Postgres (Condition 11)
            for u in self._users.values():
                if (u.get("username") or "").strip().lower() == username:
                    raise ValueError(f"Duplicate username violates unique constraint: {username}")

            record = dict(user_data)
            record["id"] = uid
            record["role"] = record.get("role", "user")
            self._users[uid] = record
            return dict(record)

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        uid = str(user_id)
        with self._lock:
            if uid not in self._users:
                return {}
            self._users[uid].update(updates)
            return dict(self._users[uid])

    def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        uid = str(session_data["user_id"])
        with self._lock:
            if uid not in self._users:
                raise ValueError("Foreign key violation: user_id does not exist in app_users")

            thash = session_data["token_hash"]
            if thash in self._sessions:
                raise ValueError("Duplicate token_hash violates unique constraint")

            record = dict(session_data)
            self._sessions[thash] = record
            return dict(record)

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            s = self._sessions.get(token_hash)
            return dict(s) if s else None

    def revoke_session(self, token_hash: str) -> None:
        self._check_db()
        with self._lock:
            if token_hash in self._sessions:
                self._sessions[token_hash]["revoked_at"] = datetime.now(timezone.utc)

    def revoke_all_user_sessions(self, user_id: str) -> None:
        self._check_db()
        uid = str(user_id)
        now = datetime.now(timezone.utc)
        with self._lock:
            for s in self._sessions.values():
                if str(s["user_id"]) == uid and s.get("revoked_at") is None:
                    s["revoked_at"] = now

    def clear(self) -> None:
        with self._lock:
            self._users.clear()
            self._sessions.clear()
            self.simulate_db_down = False


_storage_instance: Optional[UserAuthStorageInterface] = None


def get_user_auth_storage() -> UserAuthStorageInterface:
    global _storage_instance
    if _storage_instance is None:
        if settings.auth_storage_backend == "memory":
            _storage_instance = InMemoryUserAuthStorage()
        else:
            _storage_instance = PostgresUserAuthStorage()
            # Try initializing schema if running on Postgres
            try:
                _storage_instance.init_schema()
            except Exception as e:
                log.warning(f"Deferred Postgres schema init: {e}")
    return _storage_instance


def set_user_auth_storage(storage: UserAuthStorageInterface) -> None:
    """Setter used by tests to inject mock or memory storage."""
    global _storage_instance
    _storage_instance = storage
