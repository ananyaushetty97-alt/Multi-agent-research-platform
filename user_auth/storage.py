import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid
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
    def list_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
    ) -> int:
        pass

    @abstractmethod
    def get_user_summary_stats(self) -> Dict[str, Any]:
        pass

    get_summary_stats = get_user_summary_stats

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

    # OTP Email Verification
    @abstractmethod
    def set_otp(
        self,
        user_id: str,
        email: str,
        otp_hash: str,
        token_hash: Optional[str],
        expires_at: datetime,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_otp_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_otp_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def increment_otp_attempts(self, email: str) -> int:
        pass

    @abstractmethod
    def delete_otp(self, email: str) -> None:
        pass

    # Password Reset
    @abstractmethod
    def create_password_reset(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_password_reset(self, token_hash: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def mark_password_reset_used(self, token_hash: str) -> None:
        pass

    # Activity Logs
    @abstractmethod
    def log_activity(
        self,
        user_id: Optional[str],
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def query_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        pass

    @abstractmethod
    def neutralize_demo_user(self) -> None:
        pass

    @abstractmethod
    def init_schema(self) -> None:
        pass


class PostgresUserAuthStorage(UserAuthStorageInterface):
    """
    Production PostgreSQL storage implementation querying users, activity_logs,
    otp_verifications, password_resets, and user_sessions.
    """
    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or settings.postgres_dsn
        self._lock = threading.Lock()
        self._schema_initialized = False

    def _connect(self):
        try:
            return psycopg.connect(self._dsn, connect_timeout=2, row_factory=dict_row)
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
                    # Run 004 migration logic to ensure users and tracking tables exist
                    conn.execute("SELECT pg_advisory_xact_lock(%s);", (settings.migration_advisory_lock_id,))
                    
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS public.users (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            name VARCHAR(100) NOT NULL,
                            email VARCHAR(255) NOT NULL,
                            password_hash VARCHAR(255),
                            auth_provider VARCHAR(50) NOT NULL DEFAULT 'email',
                            google_id VARCHAR(255),
                            email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                            status VARCHAR(20) NOT NULL DEFAULT 'active',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            last_login_at TIMESTAMPTZ
                        );
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email ON public.users (LOWER(email));
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON public.users (google_id) WHERE google_id IS NOT NULL;
                        CREATE INDEX IF NOT EXISTS idx_users_status ON public.users (status);
                        CREATE INDEX IF NOT EXISTS idx_users_created_at ON public.users (created_at DESC);

                        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS username VARCHAR(255);
                        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user';
                        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
                        ALTER TABLE public.users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);

                        DO $$
                        BEGIN
                            IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='app_users') THEN
                                ALTER TABLE public.app_users ALTER COLUMN hashed_password DROP NOT NULL;
                                ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100);
                                ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255);
                                ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
                                CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_lower_email ON public.app_users (LOWER(email));
                                CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_google_sub ON public.app_users (google_sub);
                            END IF;
                        END $$;

                        CREATE TABLE IF NOT EXISTS public.activity_logs (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
                            event_type VARCHAR(64) NOT NULL,
                            metadata JSONB DEFAULT '{}'::jsonb,
                            ip_address VARCHAR(45),
                            user_agent TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON public.activity_logs (user_id);
                        CREATE INDEX IF NOT EXISTS idx_activity_logs_event_type ON public.activity_logs (event_type);
                        CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON public.activity_logs (created_at DESC);

                        CREATE TABLE IF NOT EXISTS public.otp_verifications (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            email VARCHAR(255) NOT NULL,
                            otp_hash VARCHAR(64) NOT NULL,
                            token_hash VARCHAR(64) UNIQUE,
                            attempts INT NOT NULL DEFAULT 0,
                            expires_at TIMESTAMPTZ NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            last_sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_otp_email ON public.otp_verifications (email);

                        CREATE TABLE IF NOT EXISTS public.password_resets (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            token_hash VARCHAR(64) UNIQUE NOT NULL,
                            expires_at TIMESTAMPTZ NOT NULL,
                            used_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                        CREATE INDEX IF NOT EXISTS idx_password_resets_token_hash ON public.password_resets (token_hash);

                        CREATE TABLE IF NOT EXISTS public.user_sessions_v2 (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            token_hash VARCHAR(64) UNIQUE NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            expires_at TIMESTAMPTZ NOT NULL,
                            revoked_at TIMESTAMPTZ,
                            user_agent TEXT,
                            ip VARCHAR(45)
                        );
                        CREATE INDEX IF NOT EXISTS idx_user_sessions_v2_token_hash ON public.user_sessions_v2 (token_hash);
                        CREATE INDEX IF NOT EXISTS idx_user_sessions_v2_user_id ON public.user_sessions_v2 (user_id);
                    """)
                    conn.commit()

                if settings.neutralize_demo_users:
                    self.neutralize_demo_user()

                self._schema_initialized = True
                log.info("PostgreSQL user auth and tracking tables initialized.")
            except HTTPException:
                raise
            except Exception as e:
                log.warning(f"Could not initialize PostgreSQL user auth schema: {e}")

    def neutralize_demo_user(self) -> None:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('users', 'app_users');")
                existing = {r['table_name'] for r in cur.fetchall()}
                if 'users' in existing:
                    cur.execute("""
                        UPDATE public.users 
                        SET status = 'suspended', password_hash = NULL 
                        WHERE LOWER(email) = 'user@platform.ai';
                    """)
                if 'app_users' in existing:
                    try:
                        cur.execute("ALTER TABLE public.app_users ALTER COLUMN hashed_password DROP NOT NULL;")
                    except Exception:
                        pass
                    cur.execute("""
                        UPDATE public.app_users 
                        SET is_active = FALSE, hashed_password = NULL 
                        WHERE username IN ('user', 'user@platform.ai') OR email = 'user@platform.ai';
                    """)
                conn.commit()
        except Exception as e:
            log.warning(f"Failed to neutralize demo user in Postgres: {e}")

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        clean = (email or "").strip().lower()
        if not clean:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.users WHERE LOWER(email) = %s;", (clean,)).fetchone()
            if not row:
                # Fallback to app_users if present
                try:
                    row = conn.execute("SELECT * FROM public.app_users WHERE LOWER(email) = %s;", (clean,)).fetchone()
                    if row:
                        d = dict(row)
                        d["name"] = d.get("full_name") or d.get("username", "User")
                        d["password_hash"] = d.get("hashed_password")
                        d["google_id"] = d.get("google_sub")
                        d["status"] = "active" if d.get("is_active", True) else "suspended"
                        d["auth_provider"] = "google" if d.get("google_sub") else "email"
                        return d
                except Exception:
                    pass
                return None
            return dict(row)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.users WHERE id = %s;", (str(user_id),)).fetchone()
            if not row:
                try:
                    row = conn.execute("SELECT * FROM public.app_users WHERE id = %s;", (str(user_id),)).fetchone()
                    if row:
                        d = dict(row)
                        d["name"] = d.get("full_name") or d.get("username", "User")
                        d["password_hash"] = d.get("hashed_password")
                        d["google_id"] = d.get("google_sub")
                        d["status"] = "active" if d.get("is_active", True) else "suspended"
                        d["auth_provider"] = "google" if d.get("google_sub") else "email"
                        return d
                except Exception:
                    pass
                return None
            return dict(row)

    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.users WHERE google_id = %s;", (str(google_sub),)).fetchone()
            if not row:
                try:
                    row = conn.execute("SELECT * FROM public.app_users WHERE google_sub = %s;", (str(google_sub),)).fetchone()
                    if row:
                        d = dict(row)
                        d["name"] = d.get("full_name") or d.get("username", "User")
                        d["password_hash"] = d.get("hashed_password")
                        d["google_id"] = d.get("google_sub")
                        d["status"] = "active" if d.get("is_active", True) else "suspended"
                        d["auth_provider"] = "google"
                        return d
                except Exception:
                    pass
                return None
            return dict(row)

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            now = datetime.now(timezone.utc)
            uid = str(user_data.get("id") or uuid.uuid4())
            name_val = user_data.get("name") or user_data.get("full_name") or "User"
            email_val = user_data["email"].strip().lower()
            username_val = user_data.get("username") or email_val.split("@")[0]
            conn.execute(
                """
                INSERT INTO public.users (id, name, email, password_hash, auth_provider, google_id, email_verified, status, created_at, updated_at, username, full_name, role, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    uid,
                    name_val,
                    email_val,
                    user_data.get("password_hash") or user_data.get("hashed_password"),
                    user_data.get("auth_provider", "email"),
                    user_data.get("google_id") or user_data.get("google_sub"),
                    user_data.get("email_verified", False),
                    user_data.get("status", "active"),
                    user_data.get("created_at", now),
                    user_data.get("updated_at", now),
                    username_val,
                    name_val,
                    user_data.get("role", "user"),
                    user_data.get("is_active", True),
                )
            )
            conn.commit()
        return user_data

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not updates:
            return self.get_user_by_id(user_id) or {}

        valid_cols = {
            "name", "email", "password_hash", "auth_provider", "google_id",
            "email_verified", "status", "created_at", "updated_at", "last_login_at",
            "username", "full_name", "role", "is_active"
        }
        col_aliases = {
            "hashed_password": "password_hash",
            "google_sub": "google_id",
            "last_login": "last_login_at",
        }

        set_clauses = []
        params = []
        seen_cols = set()

        for k, v in updates.items():
            db_col = col_aliases.get(k, k)
            if db_col == "is_active":
                v = bool(v)
            if db_col in valid_cols and db_col not in seen_cols:
                seen_cols.add(db_col)
                set_clauses.append(f"{db_col} = %s")
                params.append(v)

        if not set_clauses:
            return self.get_user_by_id(user_id) or {}

        set_clauses.append("updated_at = now()")
        params.append(str(user_id))

        with self._connect() as conn:
            conn.execute(
                f"UPDATE public.users SET {', '.join(set_clauses)} WHERE id = %s;",
                params
            )
            conn.commit()
        return self.get_user_by_id(user_id) or {}

    def list_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> List[Dict[str, Any]]:
        where_clauses = []
        params = []
        if search:
            where_clauses.append("(LOWER(name) LIKE %s OR LOWER(email) LIKE %s)")
            s_param = f"%{search.strip().lower()}%"
            params.extend([s_param, s_param])
        if status:
            where_clauses.append("status = %s")
            params.append(status.strip().lower())
        if auth_provider:
            where_clauses.append("auth_provider = %s")
            params.append(auth_provider.strip().lower())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        allowed_sort = {"created_at", "last_login_at", "name", "email", "status"}
        order_col = sort_by if sort_by in allowed_sort else "created_at"
        order_dir = "ASC" if sort_dir.lower() == "asc" else "DESC"

        sql = f"""
            SELECT u.*,
                   (SELECT COUNT(*) FROM public.chat_sessions c WHERE c.user_id = u.id) AS total_conversations,
                   (SELECT COUNT(*) FROM public.chat_messages m JOIN public.chat_sessions cs ON m.session_id = cs.id WHERE cs.user_id = u.id) AS total_messages
            FROM public.users u
            {where_sql}
            ORDER BY u.{order_col} {order_dir}
            LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def count_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
    ) -> int:
        where_clauses = []
        params = []
        if search:
            where_clauses.append("(LOWER(name) LIKE %s OR LOWER(email) LIKE %s)")
            s_param = f"%{search.strip().lower()}%"
            params.extend([s_param, s_param])
        if status:
            where_clauses.append("status = %s")
            params.append(status.strip().lower())
        if auth_provider:
            where_clauses.append("auth_provider = %s")
            params.append(auth_provider.strip().lower())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT COUNT(*) AS cnt FROM public.users {where_sql};"

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return row["cnt"] if row else 0

    def get_user_summary_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) AS total_users,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS signups_today,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS signups_7d,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') AS signups_30d,
                    COUNT(*) FILTER (WHERE status = 'active') AS active_users,
                    COUNT(*) FILTER (WHERE status = 'suspended') AS suspended_users,
                    COUNT(*) FILTER (WHERE auth_provider = 'google' OR google_id IS NOT NULL) AS google_users,
                    COUNT(*) FILTER (WHERE auth_provider = 'email' AND google_id IS NULL) AS email_users,
                    (SELECT COUNT(*) FROM public.chat_sessions) AS total_conversations,
                    (SELECT COUNT(*) FROM public.chat_messages) AS total_messages
                FROM public.users;
            """).fetchone()
            return dict(row) if row else {}

    get_summary_stats = get_user_summary_stats

    def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO public.user_sessions_v2 (id, user_id, token_hash, created_at, expires_at, revoked_at, user_agent, ip)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    str(session_data["id"]),
                    str(session_data["user_id"]),
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
            try:
                row = conn.execute("SELECT * FROM public.user_sessions_v2 WHERE token_hash = %s;", (token_hash,)).fetchone()
                if row:
                    return dict(row)
            except Exception:
                pass
            try:
                row = conn.execute("SELECT * FROM public.user_sessions WHERE token_hash = %s;", (token_hash,)).fetchone()
                if row:
                    return dict(row)
            except Exception:
                pass
            return None

    def revoke_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            try:
                conn.execute("UPDATE public.user_sessions_v2 SET revoked_at = NOW() WHERE token_hash = %s;", (token_hash,))
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute("UPDATE public.user_sessions SET revoked_at = NOW() WHERE token_hash = %s;", (token_hash,))
                conn.commit()
            except Exception:
                pass

    def revoke_all_user_sessions(self, user_id: str) -> None:
        with self._connect() as conn:
            try:
                conn.execute("UPDATE public.user_sessions_v2 SET revoked_at = NOW() WHERE user_id = %s;", (str(user_id),))
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute("UPDATE public.user_sessions SET revoked_at = NOW() WHERE user_id = %s;", (str(user_id),))
                conn.commit()
            except Exception:
                pass

    def set_otp(
        self,
        user_id: str,
        email: str,
        otp_hash: str,
        token_hash: Optional[str],
        expires_at: datetime,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.execute("DELETE FROM public.otp_verifications WHERE LOWER(email) = %s;", (email.strip().lower(),))
            row = conn.execute(
                """
                INSERT INTO public.otp_verifications (user_id, email, otp_hash, token_hash, attempts, expires_at, created_at, last_sent_at)
                VALUES (%s, %s, %s, %s, 0, %s, now(), now())
                RETURNING *;
                """,
                (str(user_id), email.strip().lower(), otp_hash, token_hash, expires_at),
            ).fetchone()
            conn.commit()
            return dict(row) if row else {}

    def get_otp_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.otp_verifications WHERE LOWER(email) = %s;", (email.strip().lower(),)).fetchone()
            return dict(row) if row else None

    def get_otp_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.otp_verifications WHERE token_hash = %s;", (token_hash,)).fetchone()
            return dict(row) if row else None

    def increment_otp_attempts(self, email: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE public.otp_verifications
                SET attempts = attempts + 1
                WHERE LOWER(email) = %s
                RETURNING attempts;
                """,
                (email.strip().lower(),),
            ).fetchone()
            conn.commit()
            return row["attempts"] if row else 5

    def delete_otp(self, email: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM public.otp_verifications WHERE LOWER(email) = %s;", (email.strip().lower(),))
            conn.commit()

    def create_password_reset(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO public.password_resets (user_id, token_hash, expires_at, created_at)
                VALUES (%s, %s, %s, now())
                RETURNING *;
                """,
                (str(user_id), token_hash, expires_at),
            ).fetchone()
            conn.commit()
            return dict(row) if row else {}

    def get_password_reset(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM public.password_resets WHERE token_hash = %s;", (token_hash,)).fetchone()
            return dict(row) if row else None

    def mark_password_reset_used(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE public.password_resets SET used_at = now() WHERE token_hash = %s;", (token_hash,))
            conn.commit()

    def log_activity(
        self,
        user_id: Optional[str],
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            import json
            meta_json = json.dumps(metadata or {})
            row = conn.execute(
                """
                INSERT INTO public.activity_logs (user_id, event_type, metadata, ip_address, user_agent, created_at)
                VALUES (%s, %s, %s::jsonb, %s, %s, now())
                RETURNING *;
                """,
                (str(user_id) if user_id else None, event_type, meta_json, ip_address, user_agent),
            ).fetchone()
            conn.commit()
            return dict(row) if row else {}

    def query_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where_clauses = []
        params = []
        if user_id:
            where_clauses.append("a.user_id = %s")
            params.append(str(user_id))
        if event_type:
            where_clauses.append("a.event_type = %s")
            params.append(event_type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            SELECT a.*, u.email, u.name
            FROM public.activity_logs a
            LEFT JOIN public.users u ON a.user_id = u.id
            {where_sql}
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def count_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        where_clauses = []
        params = []
        if user_id:
            where_clauses.append("user_id = %s")
            params.append(str(user_id))
        if event_type:
            where_clauses.append("event_type = %s")
            params.append(event_type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT COUNT(*) AS cnt FROM public.activity_logs {where_sql};"

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return row["cnt"] if row else 0


class InMemoryUserAuthStorage(UserAuthStorageInterface):
    """
    In-memory thread-safe implementation strictly for tests & offline dev.
    Mirrors the PostgreSQL schema 1:1.
    """
    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}  # id -> dict
        self._sessions: Dict[str, Dict[str, Any]] = {}  # token_hash -> dict
        self._otps: Dict[str, Dict[str, Any]] = {}  # email -> dict
        self._resets: Dict[str, Dict[str, Any]] = {}  # token_hash -> dict
        self._activity_logs: List[Dict[str, Any]] = []
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
                    u["status"] = "suspended"
                    u["password_hash"] = None
                    u["hashed_password"] = None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        clean = (email or "").strip().lower()
        if not clean:
            return None
        with self._lock:
            for u in self._users.values():
                if (u.get("email") or "").strip().lower() == clean:
                    res = dict(u)
                    # normalize compatibility keys
                    res["full_name"] = res.get("full_name") or res.get("name")
                    res["hashed_password"] = res.get("hashed_password") or res.get("password_hash")
                    res["is_active"] = (res.get("status") == "active") if "status" in res else res.get("is_active", True)
                    return res
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            u = self._users.get(str(user_id))
            if not u:
                return None
            res = dict(u)
            res["full_name"] = res.get("full_name") or res.get("name")
            res["hashed_password"] = res.get("hashed_password") or res.get("password_hash")
            res["is_active"] = (res.get("status") == "active") if "status" in res else res.get("is_active", True)
            return res

    def get_user_by_google_sub(self, google_sub: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            for u in self._users.values():
                if u.get("google_sub") == google_sub or u.get("google_id") == google_sub:
                    res = dict(u)
                    res["full_name"] = res.get("full_name") or res.get("name")
                    res["hashed_password"] = res.get("hashed_password") or res.get("password_hash")
                    res["is_active"] = (res.get("status") == "active") if "status" in res else res.get("is_active", True)
                    return res
            return None

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        uid = str(user_data.get("id") or uuid.uuid4())
        email = (user_data.get("email") or "").strip().lower()
        username = (user_data.get("username") or email).strip().lower()

        with self._lock:
            if email:
                for u in self._users.values():
                    if (u.get("email") or "").strip().lower() == email:
                        raise ValueError(f"Duplicate email violates unique constraint: {email}")

            record = dict(user_data)
            record["id"] = uid
            record["name"] = record.get("name") or record.get("full_name") or "User"
            record["full_name"] = record["name"]
            record["username"] = username
            record["role"] = record.get("role", "user")
            record["password_hash"] = record.get("password_hash") or record.get("hashed_password")
            record["hashed_password"] = record["password_hash"]
            record["google_id"] = record.get("google_id") or record.get("google_sub")
            record["google_sub"] = record["google_id"]
            record["status"] = record.get("status", "active")
            record["is_active"] = (record["status"] == "active")
            record["auth_provider"] = record.get("auth_provider", "email")
            record["email_verified"] = record.get("email_verified", False)
            record["created_at"] = record.get("created_at", datetime.now(timezone.utc))
            record["updated_at"] = record.get("updated_at", record["created_at"])
            record["last_login_at"] = record.get("last_login_at") or record.get("last_login")
            record["last_login"] = record["last_login_at"]
            self._users[uid] = record
            return dict(record)

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        uid = str(user_id)
        with self._lock:
            if uid not in self._users:
                return {}
            u = self._users[uid]
            u.update(updates)
            if "name" in updates: u["full_name"] = updates["name"]
            if "full_name" in updates: u["name"] = updates["full_name"]
            if "password_hash" in updates: u["hashed_password"] = updates["password_hash"]
            if "hashed_password" in updates: u["password_hash"] = updates["hashed_password"]
            if "google_id" in updates: u["google_sub"] = updates["google_id"]
            if "google_sub" in updates: u["google_id"] = updates["google_sub"]
            if "last_login_at" in updates: u["last_login"] = updates["last_login_at"]
            if "last_login" in updates: u["last_login_at"] = updates["last_login"]
            if "status" in updates: u["is_active"] = (updates["status"] == "active")
            if "is_active" in updates: u["status"] = "active" if updates["is_active"] else "suspended"
            u["updated_at"] = datetime.now(timezone.utc)
            return dict(u)

    def list_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> List[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            res = list(self._users.values())
            if search:
                s = search.lower()
                res = [u for u in res if s in (u.get("name") or "").lower() or s in (u.get("email") or "").lower()]
            if status:
                res = [u for u in res if u.get("status", "active").lower() == status.lower()]
            if auth_provider:
                res = [u for u in res if u.get("auth_provider", "email").lower() == auth_provider.lower()]

            reverse = (sort_dir.lower() == "desc")
            res.sort(key=lambda u: str(u.get(sort_by) or ""), reverse=reverse)
            return [dict(u) for u in res[offset:offset + limit]]

    def count_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        auth_provider: Optional[str] = None,
    ) -> int:
        self._check_db()
        with self._lock:
            res = list(self._users.values())
            if search:
                s = search.lower()
                res = [u for u in res if s in (u.get("name") or "").lower() or s in (u.get("email") or "").lower()]
            if status:
                res = [u for u in res if u.get("status", "active").lower() == status.lower()]
            if auth_provider:
                res = [u for u in res if u.get("auth_provider", "email").lower() == auth_provider.lower()]
            return len(res)

    def get_user_summary_stats(self) -> Dict[str, Any]:
        self._check_db()
        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        with self._lock:
            users = list(self._users.values())
            total = len(users)
            signups_today = sum(1 for u in users if u.get("created_at") and u["created_at"] >= one_day_ago)
            signups_7d = sum(1 for u in users if u.get("created_at") and u["created_at"] >= seven_days_ago)
            signups_30d = sum(1 for u in users if u.get("created_at") and u["created_at"] >= thirty_days_ago)
            active = sum(1 for u in users if u.get("status", "active") == "active")
            suspended = sum(1 for u in users if u.get("status") == "suspended")
            google = sum(1 for u in users if u.get("auth_provider") == "google" or u.get("google_id") or u.get("google_sub"))
            email = sum(1 for u in users if u.get("auth_provider") == "email" and not u.get("google_id") and not u.get("google_sub"))

            return {
                "total_users": total,
                "signups_today": signups_today,
                "signups_7d": signups_7d,
                "signups_30d": signups_30d,
                "active_users": active,
                "suspended_users": suspended,
                "google_users": google,
                "email_users": email,
                "total_conversations": 0,
                "total_messages": 0,
            }

    get_summary_stats = get_user_summary_stats

    def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_db()
        thash = session_data["token_hash"]
        with self._lock:
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

    def set_otp(
        self,
        user_id: str,
        email: str,
        otp_hash: str,
        token_hash: Optional[str],
        expires_at: datetime,
    ) -> Dict[str, Any]:
        self._check_db()
        clean = email.strip().lower()
        now = datetime.now(timezone.utc)
        with self._lock:
            record = {
                "id": str(user_id),
                "user_id": str(user_id),
                "email": clean,
                "otp_hash": otp_hash,
                "token_hash": token_hash,
                "attempts": 0,
                "expires_at": expires_at,
                "created_at": now,
                "last_sent_at": now,
            }
            self._otps[clean] = record
            return dict(record)

    def get_otp_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        clean = email.strip().lower()
        with self._lock:
            otp = self._otps.get(clean)
            return dict(otp) if otp else None

    def get_otp_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            for o in self._otps.values():
                if o.get("token_hash") == token_hash:
                    return dict(o)
            return None

    def increment_otp_attempts(self, email: str) -> int:
        self._check_db()
        clean = email.strip().lower()
        with self._lock:
            if clean in self._otps:
                self._otps[clean]["attempts"] += 1
                return self._otps[clean]["attempts"]
            return 5

    def delete_otp(self, email: str) -> None:
        self._check_db()
        clean = email.strip().lower()
        with self._lock:
            self._otps.pop(clean, None)

    def create_password_reset(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        self._check_db()
        now = datetime.now(timezone.utc)
        with self._lock:
            record = {
                "id": str(user_id),
                "user_id": str(user_id),
                "token_hash": token_hash,
                "expires_at": expires_at,
                "used_at": None,
                "created_at": now,
            }
            self._resets[token_hash] = record
            return dict(record)

    def get_password_reset(self, token_hash: str) -> Optional[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            r = self._resets.get(token_hash)
            return dict(r) if r else None

    def mark_password_reset_used(self, token_hash: str) -> None:
        self._check_db()
        now = datetime.now(timezone.utc)
        with self._lock:
            if token_hash in self._resets:
                self._resets[token_hash]["used_at"] = now

    def log_activity(
        self,
        user_id: Optional[str],
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._check_db()
        now = datetime.now(timezone.utc)
        import uuid
        entry = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id) if user_id else None,
            "event_type": event_type,
            "metadata": metadata or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": now,
        }
        with self._lock:
            self._activity_logs.append(entry)
            return dict(entry)

    def query_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        self._check_db()
        with self._lock:
            res = list(self._activity_logs)
            if user_id:
                uid = str(user_id)
                res = [a for a in res if a.get("user_id") == uid]
            if event_type:
                res = [a for a in res if a.get("event_type") == event_type]
            res.sort(key=lambda a: a["created_at"], reverse=True)
            # attach user email / name if available
            out = []
            for a in res[offset:offset + limit]:
                d = dict(a)
                if d.get("user_id") and d["user_id"] in self._users:
                    u = self._users[d["user_id"]]
                    d["email"] = u.get("email")
                    d["name"] = u.get("name") or u.get("full_name")
                out.append(d)
            return out

    def count_activity_logs(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        self._check_db()
        with self._lock:
            res = self._activity_logs
            if user_id:
                uid = str(user_id)
                res = [a for a in res if a.get("user_id") == uid]
            if event_type:
                res = [a for a in res if a.get("event_type") == event_type]
            return len(res)

    def clear(self) -> None:
        with self._lock:
            self._users.clear()
            self._sessions.clear()
            self._otps.clear()
            self._resets.clear()
            self._activity_logs.clear()
            self.simulate_db_down = False


_storage_instance: Optional[UserAuthStorageInterface] = None


def get_user_auth_storage() -> UserAuthStorageInterface:
    global _storage_instance
    if _storage_instance is None:
        if settings.auth_storage_backend == "memory":
            _storage_instance = InMemoryUserAuthStorage()
        else:
            _storage_instance = PostgresUserAuthStorage()
            try:
                _storage_instance.init_schema()
            except Exception as e:
                log.warning(f"Deferred Postgres schema init: {e}")
    return _storage_instance


def set_user_auth_storage(storage: UserAuthStorageInterface) -> None:
    global _storage_instance
    _storage_instance = storage
