-- ============================================================================
-- Migration: 002_user_auth_tables.sql
-- Description: Additive migration for Regular User Authentication & Sessions.
-- ============================================================================

BEGIN;

-- 1. Acquire transactional advisory lock to prevent concurrent worker migration races
-- Constant: 742910482 (matches settings.migration_advisory_lock_id in user_auth/config.py)
SELECT pg_advisory_xact_lock(742910482);

-- 2. Ensure prerequisite app_users table exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'app_users'
    ) THEN
        RAISE EXCEPTION 'Prerequisite table app_users does not exist. Initialize admin storage first.';
    END IF;
END $$;

-- 3. Drop NOT NULL on hashed_password early so demo neutralization and Google auth can store NULL
ALTER TABLE app_users ALTER COLUMN hashed_password DROP NOT NULL;

-- 4. Deterministically resolve known admin seed artifact on demo user accounts:
-- The admin backend seed seeds two demo rows: 'user' and 'user@platform.ai', both with email 'user@platform.ai'.
-- Null the secondary alias row's email and deactivate both demo rows before creating unique index.
UPDATE app_users 
SET email = NULL 
WHERE username = 'user@platform.ai' AND email = 'user@platform.ai';

UPDATE app_users 
SET is_active = FALSE, 
    hashed_password = NULL 
WHERE username IN ('user', 'user@platform.ai') OR email = 'user@platform.ai';

-- 5. Pre-check for unexpected duplicate emails before creating unique index
DO $$
DECLARE
    dup_emails TEXT;
BEGIN
    SELECT string_agg(lower_email, ', ')
    INTO dup_emails
    FROM (
        SELECT LOWER(email) AS lower_email
        FROM app_users
        WHERE email IS NOT NULL
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
    ) s;

    IF dup_emails IS NOT NULL THEN
        RAISE EXCEPTION 'Cannot apply migration 002: duplicate emails found in app_users: %. Migration aborted, no changes made.', dup_emails;
    END IF;
END $$;

-- 6. Additive columns on app_users
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100);
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255);
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;

-- 7. Add unique indexes on app_users
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_lower_email 
    ON app_users (LOWER(email)) 
    WHERE email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_google_sub 
    ON app_users (google_sub) 
    WHERE google_sub IS NOT NULL;

-- 8. Create user_sessions table with UUID user_id matching app_users.id
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

COMMIT;
