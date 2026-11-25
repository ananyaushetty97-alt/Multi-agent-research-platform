-- Migration 003: Server-side chat persistence and user monograph reviews
-- Applied: 2026-11-22
-- Rollback:
--   DROP TABLE IF EXISTS public.report_reviews CASCADE;
--   DROP TABLE IF EXISTS public.chat_messages CASCADE;
--   DROP TABLE IF EXISTS public.chat_sessions CASCADE;

BEGIN;

-- Advisory lock 742910483 for migration 003 concurrency control
SELECT pg_advisory_xact_lock(742910483);

-- Table 1: chat_sessions (Server-side user chat persistence)
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'New Research',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated 
    ON public.chat_sessions (user_id, updated_at DESC);

-- Table 2: chat_messages (Turns within a research chat session)
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    search_results JSONB DEFAULT '[]'::jsonb,
    score JSONB,
    intent VARCHAR(64),
    seconds FLOAT,
    cached BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created 
    ON public.chat_messages (session_id, created_at ASC);

-- Table 3: report_reviews (User feedback on synthesized monographs)
CREATE TABLE IF NOT EXISTS public.report_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
    session_id UUID REFERENCES public.chat_sessions(id) ON DELETE SET NULL,
    report_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255),
    relevance INT NOT NULL CHECK (relevance >= 1 AND relevance <= 10),
    accuracy INT NOT NULL CHECK (accuracy >= 1 AND accuracy <= 10),
    clarity INT NOT NULL CHECK (clarity >= 1 AND clarity <= 10),
    comment VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_report_reviews_user_report UNIQUE (user_id, report_id)
);

CREATE INDEX IF NOT EXISTS idx_report_reviews_user 
    ON public.report_reviews (user_id);
CREATE INDEX IF NOT EXISTS idx_report_reviews_created 
    ON public.report_reviews (created_at DESC);

COMMIT;
