"""
Storage layer for server-side chat sessions, messages, and report reviews.
Supports both PostgreSQL (production) and thread-safe In-Memory (testing/offline).
"""

import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from user_auth.config import settings

log = logging.getLogger("user_auth.chat_storage")


class ChatReviewStorageInterface(ABC):
    @abstractmethod
    def create_chat_session(self, user_id: str, title: str = "New Research", session_id: Optional[str] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_chat_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def rename_chat_session(self, user_id: str, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_chat_session(self, user_id: str, session_id: str) -> bool:
        pass

    @abstractmethod
    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        search_results: Optional[List[Dict[str, Any]]] = None,
        score: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        seconds: Optional[float] = None,
        cached: bool = False,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def upsert_review(
        self,
        user_id: str,
        report_id: str,
        relevance: int,
        accuracy: int,
        clarity: int,
        comment: Optional[str] = None,
        topic: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_user_review(self, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_user_reviews(self, user_id: str) -> List[Dict[str, Any]]:
        pass


class InMemoryChatReviewStorage(ChatReviewStorageInterface):
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._messages: Dict[str, List[Dict[str, Any]]] = {}
        self._reviews: Dict[str, Dict[str, Any]] = {}  # key: f"{user_id}:{report_id}"
        self._lock = threading.Lock()

    def create_chat_session(self, user_id: str, title: str = "New Research", session_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            sid = session_id or str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()
            record = {
                "id": sid,
                "user_id": str(user_id),
                "title": title[:255],
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            self._sessions[sid] = record
            self._messages[sid] = []
            return dict(record)

    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            user_str = str(user_id)
            matched = [dict(s) for s in self._sessions.values() if s["user_id"] == user_str]
            matched.sort(key=lambda s: s["updated_at"], reverse=True)
            return matched

    def get_chat_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(str(session_id))
            if not s or s["user_id"] != str(user_id):
                return None
            res = dict(s)
            res["messages"] = [dict(m) for m in self._messages.get(str(session_id), [])]
            return res

    def rename_chat_session(self, user_id: str, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(str(session_id))
            if not s or s["user_id"] != str(user_id):
                return None
            s["title"] = title[:255]
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
            return dict(s)

    def delete_chat_session(self, user_id: str, session_id: str) -> bool:
        with self._lock:
            s = self._sessions.get(str(session_id))
            if not s or s["user_id"] != str(user_id):
                return False
            del self._sessions[str(session_id)]
            self._messages.pop(str(session_id), None)
            return True

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        search_results: Optional[List[Dict[str, Any]]] = None,
        score: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        seconds: Optional[float] = None,
        cached: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            sid = str(session_id)
            msg_id = str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()
            msg = {
                "id": msg_id,
                "session_id": sid,
                "role": role,
                "content": content,
                "search_results": search_results or [],
                "score": score,
                "intent": intent,
                "seconds": seconds,
                "cached": cached,
                "created_at": now_iso,
            }
            self._messages.setdefault(sid, []).append(msg)
            if sid in self._sessions:
                self._sessions[sid]["updated_at"] = now_iso
            return dict(msg)

    def upsert_review(
        self,
        user_id: str,
        report_id: str,
        relevance: int,
        accuracy: int,
        clarity: int,
        comment: Optional[str] = None,
        topic: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            key = f"{user_id}:{report_id}"
            now_iso = datetime.now(timezone.utc).isoformat()
            existing = self._reviews.get(key)
            rid = existing["id"] if existing else str(uuid.uuid4())
            record = {
                "id": rid,
                "user_id": str(user_id),
                "session_id": str(session_id) if session_id else None,
                "report_id": str(report_id),
                "topic": topic[:255] if topic else None,
                "relevance": relevance,
                "accuracy": accuracy,
                "clarity": clarity,
                "comment": comment[:1000] if comment else None,
                "created_at": existing["created_at"] if existing else now_iso,
                "updated_at": now_iso,
            }
            self._reviews[key] = record
            return dict(record)

    def get_user_review(self, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            key = f"{user_id}:{report_id}"
            rev = self._reviews.get(key)
            return dict(rev) if rev else None

    def list_user_reviews(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            user_str = str(user_id)
            matched = [dict(r) for r in self._reviews.values() if r["user_id"] == user_str]
            matched.sort(key=lambda r: r["created_at"], reverse=True)
            return matched


class PostgresChatReviewStorage(ChatReviewStorageInterface):
    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or settings.postgres_dsn

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=3, row_factory=dict_row)

    def create_chat_session(self, user_id: str, title: str = "New Research", session_id: Optional[str] = None) -> Dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO public.chat_sessions (id, user_id, title)
                VALUES (%s, %s, %s)
                RETURNING id, user_id, title, created_at, updated_at
                """,
                (sid, str(user_id), title[:255]),
            ).fetchone()
            conn.commit()
            res = dict(row)
            res["id"] = str(res["id"])
            res["user_id"] = str(res["user_id"])
            return res

    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM public.chat_sessions
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (str(user_id),),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["id"] = str(d["id"])
                d["user_id"] = str(d["user_id"])
                out.append(d)
            return out

    def get_chat_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            s_row = conn.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM public.chat_sessions
                WHERE id = %s AND user_id = %s
                """,
                (str(session_id), str(user_id)),
            ).fetchone()
            if not s_row:
                return None

            m_rows = conn.execute(
                """
                SELECT id, session_id, role, content, search_results, score, intent, seconds, cached, created_at
                FROM public.chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (str(session_id),),
            ).fetchall()

            res = dict(s_row)
            res["id"] = str(res["id"])
            res["user_id"] = str(res["user_id"])
            messages = []
            for m in m_rows:
                md = dict(m)
                md["id"] = str(md["id"])
                md["session_id"] = str(md["session_id"])
                messages.append(md)
            res["messages"] = messages
            return res

    def rename_chat_session(self, user_id: str, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE public.chat_sessions
                SET title = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                RETURNING id, user_id, title, created_at, updated_at
                """,
                (title[:255], str(session_id), str(user_id)),
            ).fetchone()
            conn.commit()
            if not row:
                return None
            res = dict(row)
            res["id"] = str(res["id"])
            res["user_id"] = str(res["user_id"])
            return res

    def delete_chat_session(self, user_id: str, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM public.chat_sessions
                WHERE id = %s AND user_id = %s
                """,
                (str(session_id), str(user_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        search_results: Optional[List[Dict[str, Any]]] = None,
        score: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        seconds: Optional[float] = None,
        cached: bool = False,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO public.chat_messages (id, session_id, role, content, search_results, score, intent, seconds, cached)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, session_id, role, content, search_results, score, intent, seconds, cached, created_at
                """,
                (
                    str(session_id),
                    role,
                    content,
                    json.dumps(search_results or []),
                    json.dumps(score) if score else None,
                    intent,
                    seconds,
                    cached,
                ),
            ).fetchone()
            conn.execute("UPDATE public.chat_sessions SET updated_at = now() WHERE id = %s", (str(session_id),))
            conn.commit()
            res = dict(row)
            res["id"] = str(res["id"])
            res["session_id"] = str(res["session_id"])
            return res

    def upsert_review(
        self,
        user_id: str,
        report_id: str,
        relevance: int,
        accuracy: int,
        clarity: int,
        comment: Optional[str] = None,
        topic: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO public.report_reviews (id, user_id, session_id, report_id, topic, relevance, accuracy, clarity, comment, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (user_id, report_id) DO UPDATE SET
                    relevance = EXCLUDED.relevance,
                    accuracy = EXCLUDED.accuracy,
                    clarity = EXCLUDED.clarity,
                    comment = EXCLUDED.comment,
                    topic = COALESCE(EXCLUDED.topic, report_reviews.topic),
                    session_id = COALESCE(EXCLUDED.session_id, report_reviews.session_id),
                    updated_at = now()
                RETURNING id, user_id, session_id, report_id, topic, relevance, accuracy, clarity, comment, created_at, updated_at
                """,
                (
                    str(user_id),
                    str(session_id) if session_id else None,
                    str(report_id),
                    topic[:255] if topic else None,
                    relevance,
                    accuracy,
                    clarity,
                    comment[:1000] if comment else None,
                ),
            ).fetchone()
            conn.commit()
            res = dict(row)
            res["id"] = str(res["id"])
            res["user_id"] = str(res["user_id"])
            if res.get("session_id"):
                res["session_id"] = str(res["session_id"])
            return res

    def get_user_review(self, user_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, session_id, report_id, topic, relevance, accuracy, clarity, comment, created_at, updated_at
                FROM public.report_reviews
                WHERE user_id = %s AND report_id = %s
                """,
                (str(user_id), str(report_id)),
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            res["id"] = str(res["id"])
            res["user_id"] = str(res["user_id"])
            if res.get("session_id"):
                res["session_id"] = str(res["session_id"])
            return res

    def list_user_reviews(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, session_id, report_id, topic, relevance, accuracy, clarity, comment, created_at, updated_at
                FROM public.report_reviews
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (str(user_id),),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["id"] = str(d["id"])
                d["user_id"] = str(d["user_id"])
                if d.get("session_id"):
                    d["session_id"] = str(d["session_id"])
                out.append(d)
            return out


_storage_instance: Optional[ChatReviewStorageInterface] = None


def get_chat_review_storage() -> ChatReviewStorageInterface:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    if settings.auth_storage_backend == "postgres":
        _storage_instance = PostgresChatReviewStorage()
    else:
        _storage_instance = InMemoryChatReviewStorage()
    return _storage_instance


def set_chat_review_storage(storage: Optional[ChatReviewStorageInterface]) -> None:
    global _storage_instance
    _storage_instance = storage
