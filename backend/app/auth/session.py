import base64
import hashlib
import hmac
import json
import time
from typing import Annotated, Literal

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import settings

UserRole = Literal["user", "admin"]
SESSION_COOKIE = "paitryk_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14


class AuthUser(BaseModel):
    username: str
    role: UserRole


class PublicUser(AuthUser):
    label: str


def list_users(request: Request) -> list[PublicUser]:
    users = request.app.state.user_store.list_users()
    return [
        PublicUser(
            username=user.username,
            role=user.role,
            label="Administrator" if user.role == "admin" else "Użytkownik czata",
        )
        for user in users
    ]


def verify_credentials(request: Request, username: str, password: str) -> AuthUser | None:
    user = request.app.state.user_store.verify(username, password)
    if not user:
        return None
    return AuthUser(username=user.username, role=user.role)


def set_session_cookie(response: Response, user: AuthUser) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _encode_session(user),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")


def require_user(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> AuthUser:
    user = _decode_session(session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wymagane logowanie",
        )
    return user


def require_admin(user: Annotated[AuthUser, Depends(require_user)]) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wymagane uprawnienia admina",
        )
    return user


def _encode_session(user: AuthUser) -> str:
    payload = {
        "username": user.username,
        "role": user.role,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_b64(signature)}"


def _decode_session(token: str | None) -> AuthUser | None:
    if not token or "." not in token:
        return None
    body, signature = token.split(".", 1)
    expected = _b64(
        hmac.new(
            settings.session_secret.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return AuthUser(username=payload["username"], role=payload["role"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}")
