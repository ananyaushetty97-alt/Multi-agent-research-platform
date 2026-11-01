-- ============================================================================
-- Migration: 001_admin_tables.sql
-- Description: PostgreSQL schema for Admin Backend persistence.
-- STATUS: UNEXECUTED (Prepared for future migration review).
-- Do NOT execute this migration without prior deployment authorization.
-- ============================================================================

-- 1. Admin Users & RBAC
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username);
CREATE INDEX IF NOT EXISTS idx_admin_users_role ON admin_users(role);

-- 2. Audit Trail
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_username VARCHAR(50) NOT NULL,
    actor_role VARCHAR(20) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    client_ip VARCHAR(45)
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_timestamp ON admin_audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit_logs(actor_username);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit_logs(action);

-- 3. Request Traces
CREATE TABLE IF NOT EXISTS admin_request_traces (
    request_id UUID PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    topic_preview VARCHAR(255) NOT NULL,
    intent VARCHAR(50),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    cache_status VARCHAR(20) DEFAULT 'miss',
    sources_count INT DEFAULT 0,
    overall_score NUMERIC(3,1),
    outcome VARCHAR(20) NOT NULL DEFAULT 'success',
    error_category VARCHAR(50),
    provider VARCHAR(50),
    model VARCHAR(100),
    fallback_used BOOLEAN DEFAULT FALSE,
    rate_limited_429 BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_admin_traces_started ON admin_request_traces(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_traces_session ON admin_request_traces(session_id);
CREATE INDEX IF NOT EXISTS idx_admin_traces_outcome ON admin_request_traces(outcome);

-- 4. Agent Step Traces
CREATE TABLE IF NOT EXISTS admin_agent_steps (
    step_id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES admin_request_traces(request_id) ON DELETE CASCADE,
    step_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    summary_excerpt VARCHAR(255),
    details JSONB DEFAULT '{}'::jsonb,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_admin_steps_req ON admin_agent_steps(request_id);

-- 5. Safety & Blocked Events
CREATE TABLE IF NOT EXISTS admin_safety_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID,
    session_id VARCHAR(100),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    check_type VARCHAR(30) NOT NULL,
    reason TEXT NOT NULL,
    excerpt VARCHAR(255) NOT NULL,
    outcome VARCHAR(20) NOT NULL DEFAULT 'blocked',
    details JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_admin_safety_time ON admin_safety_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_admin_safety_type ON admin_safety_events(check_type);

-- 6. Human Review Scores
CREATE TABLE IF NOT EXISTS admin_human_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID,
    topic TEXT NOT NULL,
    reviewer_username VARCHAR(50) NOT NULL,
    review_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    relevance INT NOT NULL CHECK (relevance BETWEEN 1 AND 10),
    accuracy INT NOT NULL CHECK (accuracy BETWEEN 1 AND 10),
    clarity INT NOT NULL CHECK (clarity BETWEEN 1 AND 10),
    overall NUMERIC(3,1) NOT NULL CHECK (overall BETWEEN 1.0 AND 10.0),
    feedback_notes TEXT,
    flagged_for_rerun BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_admin_human_reviews_time ON admin_human_reviews(review_timestamp DESC);
