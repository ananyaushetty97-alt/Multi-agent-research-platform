-- ============================================================================
-- Migration: 004_user_auth_tracking_schema.sql
-- Description: Production-grade User Authentication, Activity Logs, and Isolated Data Schema
-- ============================================================================

BEGIN;

-- Advisory lock 742910484 for migration 004 concurrency control
SELECT pg_advisory_xact_lock(742910484);

-- 1. Main Users Table
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    auth_provider VARCHAR(50) NOT NULL DEFAULT 'email', -- 'email', 'google', 'both'
    google_id VARCHAR(255),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active', 'suspended'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email ON public.users (LOWER(email));
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON public.users (google_id) WHERE google_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_status ON public.users (status);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON public.users (created_at DESC);

-- Backward compatibility: If app_users existed, migrate any non-demo rows into users
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'app_users'
    ) THEN
        INSERT INTO public.users (id, name, email, password_hash, auth_provider, google_id, email_verified, status, created_at, updated_at)
        SELECT 
            id, 
            COALESCE(full_name, username, 'User') AS name, 
            LOWER(email) AS email, 
            hashed_password AS password_hash,
            CASE WHEN google_sub IS NOT NULL AND hashed_password IS NOT NULL THEN 'both'
                 WHEN google_sub IS NOT NULL THEN 'google'
                 ELSE 'email' END AS auth_provider,
            google_sub AS google_id,
            COALESCE(email_verified, FALSE),
            CASE WHEN is_active = FALSE THEN 'suspended' ELSE 'active' END AS status,
            created_at,
            created_at AS updated_at
        FROM public.app_users
        WHERE email IS NOT NULL 
          AND LOWER(email) NOT IN ('user@platform.ai', 'user')
          AND NOT EXISTS (SELECT 1 FROM public.users u WHERE LOWER(u.email) = LOWER(app_users.email));
    END IF;
END $$;

-- Neutralize old demo credentials in app_users if present
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'app_users'
    ) THEN
        UPDATE public.app_users 
        SET is_active = FALSE, hashed_password = NULL 
        WHERE username IN ('user', 'user@platform.ai') OR email = 'user@platform.ai';
    END IF;
END $$;

-- 2. Conversations Table (User-isolated chat sessions)
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'New Research',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON public.conversations (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON public.conversations (created_at DESC);

-- 3. Messages Table (Turns within a research conversation)
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL, -- 'user', 'assistant', 'report'
    content TEXT NOT NULL,
    search_results JSONB DEFAULT '[]'::jsonb,
    score JSONB,
    intent VARCHAR(64),
    seconds FLOAT,
    cached BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON public.messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON public.messages (created_at ASC);

-- 4. Activity Logs Table (System-wide tracking for user activity & admin inspection)
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

-- 5. OTP Email Verifications Table
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

CREATE INDEX IF NOT EXISTS idx_otp_user_id ON public.otp_verifications (user_id);
CREATE INDEX IF NOT EXISTS idx_otp_email ON public.otp_verifications (email);
CREATE INDEX IF NOT EXISTS idx_otp_expires_at ON public.otp_verifications (expires_at);

-- 6. Password Resets Table
CREATE TABLE IF NOT EXISTS public.password_resets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_password_resets_token_hash ON public.password_resets (token_hash);
CREATE INDEX IF NOT EXISTS idx_password_resets_user_id ON public.password_resets (user_id);

-- 7. User Sessions Table
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
CREATE INDEX IF NOT EXISTS idx_user_sessions_v2_expires_at ON public.user_sessions_v2 (expires_at);

COMMIT;
