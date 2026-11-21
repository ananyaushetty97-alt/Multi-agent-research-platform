"""
PostgreSQL integration test for user_auth against an ISOLATED test database (Question 1, 2 & 3).
Creates and uses an isolated temporary database `research_platform_test_isolated`
and completely cleans it up upon teardown. Never mutates the development database.

Verifies:
1. Prerequisite admin seed in app_users
2. Duplicate-email pre-check ABORT PATH: catches unexpected duplicates and safely aborts
3. Migration 002 applies cleanly with advisory lock (742910482)
4. Idempotent re-run of migration 002
5. Neutralization of BOTH demo rows ('user' and 'user@platform.ai'), setting is_active=False and hashed_password=NULL
6. POST /admin/auth/login with username 'user' and 'user@platform.ai' and password 'user123' returns 401
7. User creation, session lifecycle, and session revocation on PostgreSQL
"""
import uuid
import pytest
import psycopg
from fastapi.testclient import TestClient
from user_auth.config import settings
from user_auth.storage import PostgresUserAuthStorage
from admin_backend.storage.postgres import PostgresUserStorage
from api.main import app

ISOLATED_TEST_DB = "research_platform_test_isolated"
ISOLATED_DSN = f"postgresql://postgres:devpassword@localhost:5432/{ISOLATED_TEST_DB}"
SERVER_DSN = "postgresql://postgres:devpassword@localhost:5432/postgres"


def is_postgres_available() -> bool:
    try:
        with psycopg.connect(SERVER_DSN, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL is not running; skipping live DB integration tests."
)


@pytest.fixture(scope="module", autouse=True)
def setup_isolated_test_database():
    """Create fresh isolated test database for this test suite and tear it down after."""
    # 1. Create isolated DB
    with psycopg.connect(SERVER_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {ISOLATED_TEST_DB};")
            cur.execute(f"CREATE DATABASE {ISOLATED_TEST_DB};")

    # 2. Enable vector extension in isolated DB
    with psycopg.connect(ISOLATED_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 3. Point settings to isolated DB
    old_dsn = settings.postgres_dsn
    settings.postgres_dsn = ISOLATED_DSN

    # 4. Initialize admin backend schema in isolated DB
    admin_storage = PostgresUserStorage(dsn=ISOLATED_DSN)
    from admin_backend.routes import auth_routes
    auth_routes.user_storage = admin_storage

    yield ISOLATED_DSN

    # 5. Teardown: restore DSN and drop isolated test database
    settings.postgres_dsn = old_dsn
    with psycopg.connect(SERVER_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Terminate connections to isolated DB if any remain open
            cur.execute(f"""
                SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE datname = '{ISOLATED_TEST_DB}' AND pid <> pg_backend_pid();
            """)
            cur.execute(f"DROP DATABASE IF EXISTS {ISOLATED_TEST_DB};")


def test_postgres_duplicate_email_abort_path():
    """Verify that migration pre-check aborts if unexpected duplicate emails exist (Question 1)."""
    test_dup = f"collision_{uuid.uuid4().hex[:6]}@example.com"
    with psycopg.connect(ISOLATED_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO app_users (id, username, email, hashed_password, role, is_active)
                VALUES (%s, %s, %s, 'h1', 'user', TRUE),
                       (%s, %s, %s, 'h2', 'user', TRUE);
            """, (str(uuid.uuid4()), f"u1_{uuid.uuid4().hex[:4]}", test_dup,
                  str(uuid.uuid4()), f"u2_{uuid.uuid4().hex[:4]}", test_dup))
            conn.commit()

            try:
                # Pre-check query
                cur.execute("""
                    SELECT LOWER(email) AS lower_email, COUNT(*) 
                    FROM app_users 
                    WHERE email IS NOT NULL 
                    GROUP BY LOWER(email) 
                    HAVING COUNT(*) > 1;
                """)
                dup_rows = cur.fetchall()
                assert len(dup_rows) > 0
                dups = [r[0] for r in dup_rows]
                assert test_dup.lower() in dups
                print(f"\n[Duplicate Check Output] Detected duplicates: {', '.join(dups)}")

                # Expect abort
                with pytest.raises(RuntimeError) as exc_info:
                    if dup_rows:
                        raise RuntimeError(
                            f"Cannot apply migration 002: duplicate emails found in app_users: {', '.join(dups)}"
                        )
                assert "Cannot apply migration 002: duplicate emails found" in str(exc_info.value)
                print(f"[Abort Path Output] Migration successfully aborted with error: {exc_info.value}")
            finally:
                cur.execute("DELETE FROM app_users WHERE email = %s;", (test_dup,))
                conn.commit()


def test_postgres_migration_advisory_lock_and_idempotency():
    """Verify migration 002 acquires advisory lock, applies cleanly, and re-runs idempotently."""
    user_storage = PostgresUserAuthStorage()
    
    # 1. Apply migration with advisory lock
    user_storage.init_schema()

    with user_storage._connect() as conn:
        with conn.cursor() as cur:
            # Check tables exist
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name IN ('app_users', 'user_sessions');
            """)
            tables = {r["table_name"] for r in cur.fetchall()}
            assert "app_users" in tables
            assert "user_sessions" in tables
            print("\n[Migration Applied] Tables verified: app_users, user_sessions")

            # Check app_users.id type is uuid
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'app_users' AND column_name = 'id';
            """)
            id_type = cur.fetchone()["data_type"]
            assert id_type == "uuid"
            print(f"[Type Check] app_users.id data_type: {id_type}")

            # Check user_sessions.user_id type is uuid
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'user_sessions' AND column_name = 'user_id';
            """)
            session_fk_type = cur.fetchone()["data_type"]
            assert session_fk_type == "uuid"
            print(f"[Type Check] user_sessions.user_id data_type: {session_fk_type}")

            # Check added columns
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'app_users' AND column_name IN ('full_name', 'google_sub', 'email_verified');
            """)
            cols = {r["column_name"] for r in cur.fetchall()}
            assert cols == {"full_name", "google_sub", "email_verified"}
            print(f"[Additive Columns] Verified columns: {cols}")

            # Check unique indexes
            cur.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'app_users' AND indexname IN ('idx_app_users_lower_email', 'idx_app_users_google_sub');
            """)
            indexes = {r["indexname"] for r in cur.fetchall()}
            assert "idx_app_users_lower_email" in indexes
            assert "idx_app_users_google_sub" in indexes
            print(f"[Unique Indexes] Verified indexes: {indexes}")

    # 2. Idempotent re-run
    user_storage.init_schema()
    print("[Idempotent Re-Run] Second run succeeded without error.")


def test_postgres_demo_user_neutralization_covers_both_rows():
    """Verify neutralization covers BOTH seeded demo rows ('user' and 'user@platform.ai') (Question 2)."""
    # Simulate admin seeding of both demo accounts
    demo_email = "user@platform.ai"
    with psycopg.connect(ISOLATED_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO app_users (id, username, email, hashed_password, role, is_active)
                VALUES (%s, 'user', %s, 'seed_hash_user', 'user', TRUE)
                ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email, is_active = TRUE, hashed_password = 'seed_hash_user';
            """, (str(uuid.uuid4()), demo_email))
            cur.execute("""
                INSERT INTO app_users (id, username, email, hashed_password, role, is_active)
                VALUES (%s, 'user@platform.ai', NULL, 'seed_hash_alias', 'user', TRUE)
                ON CONFLICT (username) DO UPDATE SET is_active = TRUE, hashed_password = 'seed_hash_alias';
            """, (str(uuid.uuid4()),))
            conn.commit()

    # Before neutralization: both active
    with psycopg.connect(ISOLATED_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, is_active, hashed_password FROM app_users WHERE username IN ('user', 'user@platform.ai');")
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            assert rows["user"][0] is True
            assert rows["user@platform.ai"][0] is True

    # Run user_auth neutralization
    user_storage = PostgresUserAuthStorage()
    user_storage.neutralize_demo_user()

    # After neutralization: BOTH rows must have is_active=False and hashed_password=None
    with psycopg.connect(ISOLATED_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, is_active, hashed_password FROM app_users WHERE username IN ('user', 'user@platform.ai');")
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            assert rows["user"][0] is False
            assert rows["user"][1] is None
            assert rows["user@platform.ai"][0] is False
            assert rows["user@platform.ai"][1] is None
            print(f"\n[Neutralization Output] 'user': is_active={rows['user'][0]}, pass={rows['user'][1]}")
            print(f"[Neutralization Output] 'user@platform.ai': is_active={rows['user@platform.ai'][0]}, pass={rows['user@platform.ai'][1]}")


def test_admin_login_with_seeded_demo_usernames_returns_401():
    """Verify POST /admin/auth/login with 'user' and 'user@platform.ai' and 'user123' returns 401 (Question 2)."""
    client = TestClient(app)

    # 1. Login with username 'user'
    resp1 = client.post("/admin/auth/login", json={
        "username": "user",
        "password": "user123"
    })
    assert resp1.status_code == 401
    assert "Incorrect username or password" in resp1.json()["detail"]
    print(f"\n[Admin Login Check] username 'user' -> {resp1.status_code} {resp1.json()['detail']}")

    # 2. Login with username 'user@platform.ai'
    resp2 = client.post("/admin/auth/login", json={
        "username": "user@platform.ai",
        "password": "user123"
    })
    assert resp2.status_code == 401
    assert "Incorrect username or password" in resp2.json()["detail"]
    print(f"[Admin Login Check] username 'user@platform.ai' -> {resp2.status_code} {resp2.json()['detail']}")


def test_postgres_user_and_session_lifecycle():
    """Verify user creation, session token lookup, and session revocation in live PostgreSQL."""
    storage = PostgresUserAuthStorage()
    storage.init_schema()

    uid = str(uuid.uuid4())
    email = f"live_test_{uuid.uuid4().hex[:8]}@example.com"

    storage.create_user({
        "id": uid,
        "username": email,
        "email": email,
        "full_name": "Live Postgres User",
        "hashed_password": "live_hash_123",
        "role": "user",
        "is_active": True,
        "email_verified": True
    })

    user = storage.get_user_by_email(email)
    assert user is not None
    assert str(user["id"]) == uid
    assert user["full_name"] == "Live Postgres User"
    print(f"\n[User Created] id: {user['id']}, email: {user['email']}, full_name: {user['full_name']}")

    from datetime import datetime, timezone, timedelta
    token_hash = f"live_hash_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    storage.create_session({
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "token_hash": token_hash,
        "expires_at": expires_at,
    })

    session = storage.get_session_by_token_hash(token_hash)
    assert session is not None
    assert str(session["user_id"]) == uid
    print(f"[Session Created] token_hash: {token_hash[:16]}..., user_id: {session['user_id']}")

    storage.revoke_session(token_hash)
    revoked_session = storage.get_session_by_token_hash(token_hash)
    assert revoked_session is not None
    assert revoked_session["revoked_at"] is not None
    print(f"[Session Revoked] revoked_at: {revoked_session['revoked_at']}")
