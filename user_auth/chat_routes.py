"""
API routes for user chats and report reviews.
Enforces strict user ownership, CSRF protection, and isolation.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from user_auth.dependencies import get_current_user, require_csrf_protection
from user_auth.models import UserResponse
from user_auth.chat_storage import get_chat_review_storage

router = APIRouter(tags=["User Chats & Reviews"])


class ChatCreateRequest(BaseModel):
    title: Optional[str] = Field("New Research", max_length=255)


class ChatRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ReviewCreateRequest(BaseModel):
    report_id: str = Field(..., min_length=1, max_length=255)
    relevance: int = Field(..., ge=1, le=10)
    accuracy: int = Field(..., ge=1, le=10)
    clarity: int = Field(..., ge=1, le=10)
    comment: Optional[str] = Field(None, max_length=1000)
    topic: Optional[str] = Field(None, max_length=255)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat Endpoints
# ---------------------------------------------------------------------------
@router.get("/chats", response_model=List[Dict[str, Any]])
def list_user_chats(
    user: UserResponse = Depends(get_current_user),
):
    """List all saved chat sessions for the authenticated user, newest first."""
    storage = get_chat_review_storage()
    return storage.list_chat_sessions(str(user.id))


@router.post(
    "/chats",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_protection)],
)
def create_user_chat(
    req: ChatCreateRequest,
    user: UserResponse = Depends(get_current_user),
):
    """Create a new chat session owned by the authenticated user."""
    storage = get_chat_review_storage()
    title = (req.title or "New Research").strip()
    return storage.create_chat_session(user_id=str(user.id), title=title)


@router.get("/chats/{chat_id}", response_model=Dict[str, Any])
def get_user_chat(
    chat_id: str,
    user: UserResponse = Depends(get_current_user),
):
    """Retrieve a specific chat session and all its messages. Enforces ownership."""
    storage = get_chat_review_storage()
    chat = storage.get_chat_session(user_id=str(user.id), session_id=chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or access denied",
        )
    return chat


@router.put(
    "/chats/{chat_id}",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_csrf_protection)],
)
def rename_user_chat(
    chat_id: str,
    req: ChatRenameRequest,
    user: UserResponse = Depends(get_current_user),
):
    """Rename a chat session owned by the authenticated user."""
    storage = get_chat_review_storage()
    updated = storage.rename_chat_session(
        user_id=str(user.id), session_id=chat_id, title=req.title.strip()
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or access denied",
        )
    return updated


@router.delete(
    "/chats/{chat_id}",
    response_model=Dict[str, str],
    dependencies=[Depends(require_csrf_protection)],
)
def delete_user_chat(
    chat_id: str,
    user: UserResponse = Depends(get_current_user),
):
    """Delete a chat session owned by the authenticated user."""
    storage = get_chat_review_storage()
    deleted = storage.delete_chat_session(user_id=str(user.id), session_id=chat_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or access denied",
        )
    return {"status": "deleted", "id": chat_id}


# ---------------------------------------------------------------------------
# Review Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/reviews",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf_protection)],
)
def create_or_update_review(
    req: ReviewCreateRequest,
    user: UserResponse = Depends(get_current_user),
):
    """
    Rate and review a research monograph (1-10 scores, optional <= 1000 char comment).
    One review per user per report via upsert.
    """
    storage = get_chat_review_storage()
    return storage.upsert_review(
        user_id=str(user.id),
        report_id=req.report_id.strip(),
        relevance=req.relevance,
        accuracy=req.accuracy,
        clarity=req.clarity,
        comment=req.comment.strip() if req.comment else None,
        topic=req.topic.strip() if req.topic else None,
        session_id=req.session_id,
    )


@router.get("/reviews/mine", response_model=List[Dict[str, Any]])
def list_my_reviews(
    user: UserResponse = Depends(get_current_user),
):
    """List all monograph reviews submitted by the authenticated user."""
    storage = get_chat_review_storage()
    return storage.list_user_reviews(str(user.id))


@router.get("/reviews/{report_id}", response_model=Dict[str, Any])
def get_report_review(
    report_id: str,
    user: UserResponse = Depends(get_current_user),
):
    """Get the authenticated user's review for a specific report."""
    storage = get_chat_review_storage()
    rev = storage.get_user_review(user_id=str(user.id), report_id=report_id)
    if not rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No review found for this report",
        )
    return rev
