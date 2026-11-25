"""
Admin User Tracking and Monitoring Routes.
All endpoints are strictly protected by existing admin authentication (require_admin_role).
Normal users receive 403 Forbidden on all endpoints.
Data comes directly from the same database tables/storage regular users write to (single source of truth).
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.models.audit import AuditAction
from admin_backend.services.audit_service import audit_service
from user_auth.chat_storage import get_chat_review_storage
from user_auth.storage import get_user_auth_storage
from user_auth.models import UserStatusUpdateRequest
from agents.sanitizer import sanitize_report

log = logging.getLogger("admin_backend.user_tracking")

router = APIRouter(prefix="/tracking", tags=["Admin User Tracking"])


@router.get("/users")
def list_users(
    search: Optional[str] = Query(None, description="Search by user name or email"),
    status: Optional[str] = Query(None, description="Filter by status: 'active' or 'suspended'"),
    auth_provider: Optional[str] = Query(None, description="Filter by auth provider: 'email' or 'google'"),
    sort_by: str = Query("created_at", description="Sort column: created_at, last_login_at, name, email, status"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
) -> Dict[str, Any]:
    """
    List all regular users with full monitoring attributes:
    name, email, auth provider, verified status, status, signup date, last login,
    total conversations, and total messages. Supports search, filtering, and pagination.
    """
    storage = get_user_auth_storage()
    chat_store = get_chat_review_storage()

    users = storage.list_users(
        search=search,
        status=status,
        auth_provider=auth_provider,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_count = storage.count_users(
        search=search,
        status=status,
        auth_provider=auth_provider,
    )

    enriched = []
    for u in users:
        uid = str(u["id"])
        # Ensure conversation and message counts are present
        conv_count = u.get("total_conversations")
        if conv_count is None:
            conv_count = chat_store.count_user_conversations(uid)
        msg_count = u.get("total_messages")
        if msg_count is None:
            msg_count = chat_store.count_user_messages(uid)

        enriched.append({
            "id": uid,
            "name": u.get("name") or u.get("full_name") or "User",
            "email": u.get("email"),
            "auth_provider": u.get("auth_provider", "email"),
            "email_verified": bool(u.get("email_verified", False)),
            "status": u.get("status", "active"),
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
            "last_login_at": u.get("last_login_at"),
            "total_conversations": conv_count,
            "total_messages": msg_count,
        })

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "users": enriched,
    }


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: str,
    admin: AuthenticatedUser = Depends(require_admin_role),
) -> Dict[str, Any]:
    """
    Retrieve user detail: that user's full profile, all their conversations
    with full message history (read-only), and their activity timeline.
    """
    storage = get_user_auth_storage()
    chat_store = get_chat_review_storage()

    user = storage.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    uid = str(user["id"])
    conversations = chat_store.get_user_conversations_with_messages(uid)
    # Sanitize reports in conversations before presenting in admin dossier
    for c in conversations:
        for m in c.get("messages", []):
            if m.get("content") and m.get("role") in ("report", "new_research", "modify", "assistant"):
                m["content"] = sanitize_report(m["content"])
    activity_timeline = storage.query_activity_logs(user_id=uid, limit=100)

    # Log audit entry for viewing user data dossier
    audit_service.log_action(
        actor_username=admin.email or admin.username,
        actor_role="admin",
        action=AuditAction.USER_DATA_VIEW,
        resource_type="user_profile",
        resource_id=uid,
        status="success",
        details={"user_email": user.get("email"), "conversations_count": len(conversations)},
    )

    return {
        "profile": {
            "id": uid,
            "name": user.get("name") or user.get("full_name") or "User",
            "email": user.get("email"),
            "username": user.get("username"),
            "role": user.get("role", "user"),
            "auth_provider": user.get("auth_provider", "email"),
            "email_verified": bool(user.get("email_verified", False)),
            "status": user.get("status", "active"),
            "google_id": user.get("google_id") or user.get("google_sub"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "last_login_at": user.get("last_login_at"),
            "total_conversations": len(conversations),
            "total_messages": sum(len(c.get("messages", [])) for c in conversations),
        },
        "conversations": conversations,
        "activity_timeline": activity_timeline,
    }


@router.post("/users/{user_id}/status")
def update_user_status(
    user_id: str,
    req: UserStatusUpdateRequest,
    admin: AuthenticatedUser = Depends(require_admin_role),
) -> Dict[str, Any]:
    """
    Suspend or reactivate a user.
    Suspended users cannot log in.
    If suspended, revokes all current active sessions for that user immediately.
    """
    storage = get_user_auth_storage()
    user = storage.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_status = req.status.lower()
    storage.update_user(user_id, {
        "status": new_status,
        "is_active": (new_status == "active"),
    })

    if new_status == "suspended":
        # Invalidate any active sessions for the suspended user
        storage.revoke_all_user_sessions(user_id)

    # Log status change in user activity_logs
    storage.log_activity(
        user_id=user_id,
        event_type="account_status_changed",
        metadata={
            "old_status": user.get("status", "active"),
            "new_status": new_status,
            "changed_by": admin.username,
        },
    )

    # Log administrative action in admin audit_logs
    audit_action = AuditAction.USER_SUSPEND if new_status == "suspended" else AuditAction.USER_REACTIVATE
    audit_service.log_action(
        actor_username=admin.email or admin.username,
        actor_role="admin",
        action=audit_action,
        resource_type="user_account",
        resource_id=user_id,
        status="success",
        details={
            "old_status": user.get("status", "active"),
            "new_status": new_status,
            "user_email": user.get("email"),
        },
    )

    return {
        "id": user_id,
        "status": new_status,
        "message": f"User status successfully updated to {new_status}",
    }


@router.get("/activity")
def get_global_activity_feed(
    user_id: Optional[str] = Query(None, description="Filter by user id"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
) -> Dict[str, Any]:
    """
    Global activity feed across all users:
    recent logins, signups, failed logins, messages, and chats.
    """
    storage = get_user_auth_storage()
    logs = storage.query_activity_logs(
        user_id=user_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    total_count = storage.count_activity_logs(user_id=user_id, event_type=event_type)

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "activities": logs,
    }


@router.get("/stats")
def get_summary_stats(
    admin: AuthenticatedUser = Depends(require_admin_role),
) -> Dict[str, Any]:
    """
    System-wide summary metrics for administrators:
    total users, new signups (today/7d/30d), active users, suspended users,
    Google vs email signups, total conversations, and total messages.
    """
    storage = get_user_auth_storage()
    chat_store = get_chat_review_storage()

    stats = storage.get_user_summary_stats()
    stats["total_conversations"] = chat_store.get_total_conversations_count()
    stats["total_messages"] = chat_store.get_total_messages_count()

    return stats
