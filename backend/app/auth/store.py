from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

UserRole = Literal["user", "admin"]


@dataclass(frozen=True)
class StoredUser:
    username: str
    role: UserRole
    password_hash: str
    created_at: str
    updated_at: str


class UserStore:
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
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                """
            )

    def list_users(self) -> list[StoredUser]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, role, password_hash, created_at, updated_at
                FROM users
                ORDER BY role ASC, username ASC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_user(self, username: str) -> StoredUser | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, role, password_hash, created_at, updated_at
                FROM users
                WHERE username = ?
                """,
                (username.strip().lower(),),
            ).fetchone()
        return self._from_row(row) if row else None

    def upsert_user(self, username: str, password: str, role: UserRole) -> StoredUser:
        normalized = username.strip().lower()
        now = self._now()
        password_hash = hash_password(password)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (username, role, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    role = excluded.role,
                    password_hash = excluded.password_hash,
                    updated_at = excluded.updated_at
                """,
                (normalized, role, password_hash, now, now),
            )
        user = self.get_user(normalized)
        if user is None:
            raise RuntimeError("user was not persisted")
        return user

    def create_user(self, username: str, password: str, role: UserRole) -> StoredUser:
        normalized = self._normalize_username(username)
        if not password:
            raise ValueError("password is required")
        now = self._now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (username, role, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (normalized, role, hash_password(password), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("user already exists") from exc
        user = self.get_user(normalized)
        if user is None:
            raise RuntimeError("user was not persisted")
        return user

    def update_role(self, username: str, role: UserRole) -> StoredUser:
        normalized = self._normalize_username(username)
        current = self.get_user(normalized)
        if current is None:
            raise KeyError(normalized)
        if current.role == "admin" and role != "admin" and self.count_admins() <= 1:
            raise ValueError("cannot demote the last admin")

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE username = ?",
                (role, self._now(), normalized),
            )
        user = self.get_user(normalized)
        if user is None:
            raise RuntimeError("user was not persisted")
        return user

    def reset_password(self, username: str, password: str) -> StoredUser:
        normalized = self._normalize_username(username)
        if not password:
            raise ValueError("password is required")
        if self.get_user(normalized) is None:
            raise KeyError(normalized)

        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
                (hash_password(password), self._now(), normalized),
            )
        user = self.get_user(normalized)
        if user is None:
            raise RuntimeError("user was not persisted")
        return user

    def delete_user(self, username: str) -> None:
        normalized = self._normalize_username(username)
        current = self.get_user(normalized)
        if current is None:
            raise KeyError(normalized)
        if current.role == "admin" and self.count_admins() <= 1:
            raise ValueError("cannot delete the last admin")
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE username = ?", (normalized,))

    def count_admins(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = 'admin'"
            ).fetchone()
        return int(row["count"])

    def verify(self, username: str, password: str) -> StoredUser | None:
        user = self.get_user(username)
        if not user or not verify_password(password, user.password_hash):
            return None
        return user

    def _from_row(self, row: sqlite3.Row) -> StoredUser:
        return StoredUser(
            username=row["username"],
            role=row["role"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds")

    def _normalize_username(self, username: str) -> str:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("username is required")
        return normalized


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    rounds = 390_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_raw, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)
