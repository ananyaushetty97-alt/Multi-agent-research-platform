-- ============================================================================
-- Migration: 002_admin_google_auth.sql
-- Description: Expand admin_users table for Google OAuth allowlist authentication.
-- ============================================================================

-- 1. Add new columns
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255);
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);

-- 2. Make hashed_password and username nullable for Google-only admins
ALTER TABLE admin_users ALTER COLUMN hashed_password DROP NOT NULL;
ALTER TABLE admin_users ALTER COLUMN username DROP NOT NULL;

-- 3. Sync existing last_login to last_login_at if present
UPDATE admin_users SET last_login_at = last_login WHERE last_login_at IS NULL AND last_login IS NOT NULL;

-- 4. Disambiguate duplicate demo emails if needed so unique index can be created
UPDATE admin_users SET email = 'admin-alias@platform.ai' 
WHERE username = 'admin@platform.ai' AND email = 'admin@platform.ai';

-- 5. Normalize emails to lowercase
UPDATE admin_users SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL;

-- 6. Add unique index on lower(email) and index on google_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_users_email_lower ON admin_users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_admin_users_google_id ON admin_users (google_id);
