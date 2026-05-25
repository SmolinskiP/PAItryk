from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.chats.schemas import ChatAudience, ChatSession, ChatSessionWithMessages
from app.llm.base import ChatMessage


class ChatStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    audience TEXT NOT NULL,
                    title TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chat_sessions_audience_archived
                    ON chat_sessions(audience, archived, updated_at);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                    ON chat_messages(session_id, created_at);
                """
            )

    def create_session(self, audience: ChatAudience, title: str = "Nowa rozmowa") -> ChatSession:
        now = self._now()
        session_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (id, audience, title, archived, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (session_id, audience, title, now, now),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> ChatSession:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._session_from_row(row)

    def get_with_messages(self, session_id: str) -> ChatSessionWithMessages:
        session = self.get_session(session_id)
        return ChatSessionWithMessages(
            **session.model_dump(),
            messages=self.get_messages(session_id),
        )

    def list_sessions(
        self,
        *,
        audience: ChatAudience | None,
        include_archived: bool,
        limit: int = 100,
    ) -> list[ChatSession]:
        clauses = []
        params: list[str | int] = []
        if audience is not None:
            clauses.append("audience = ?")
            params.append(audience)
        if not include_archived:
            clauses.append("archived = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM chat_sessions {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [ChatMessage(role=row["role"], content=row["content"]) for row in rows]

    def append_message(self, session_id: str, message: ChatMessage) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid4()), session_id, message.role, message.content, now),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )

    def set_title_from_first_user_message(self, session_id: str, content: str) -> None:
        title = content.strip().replace("\n", " ")
        if len(title) > 72:
            title = f"{title[:69]}..."
        if not title:
            return
        with self._connect() as conn:
            current = conn.execute(
                "SELECT title FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if current is None or current["title"] != "Nowa rozmowa":
                return
            conn.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))

    def archive_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET archived = 1, updated_at = ? WHERE id = ?",
                (self._now(), session_id),
            )

    def restore_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET archived = 0, updated_at = ? WHERE id = ?",
                (self._now(), session_id),
            )

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )

    def _session_from_row(self, row: sqlite3.Row) -> ChatSession:
        return ChatSession(
            id=row["id"],
            audience=row["audience"],
            title=row["title"],
            archived=bool(row["archived"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds")
