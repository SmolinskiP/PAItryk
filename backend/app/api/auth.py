from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth.session import (
    AuthUser,
    PublicUser,
    clear_session_cookie,
    list_users,
    require_admin,
    require_user,
    set_session_cookie,
    verify_credentials,
)
from app.auth.store import StoredUser, UserRole

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user: AuthUser


class UsersResponse(BaseModel):
    users: list[PublicUser]


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: UserRole = "user"


class UserRoleRequest(BaseModel):
    role: UserRole


class PasswordResetRequest(BaseModel):
    password: str


def _public_user(user: StoredUser) -> PublicUser:
    return PublicUser(
        username=user.username,
        role=user.role,
        label="Administrator" if user.role == "admin" else "Użytkownik czata",
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request, response: Response) -> AuthResponse:
    user = verify_credentials(request, req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy login lub hasło",
        )
    set_session_cookie(response, user)
    return AuthResponse(user=user)


@router.post("/auth/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/auth/me", response_model=AuthResponse)
async def me(user: Annotated[AuthUser, Depends(require_user)]) -> AuthResponse:
    return AuthResponse(user=user)


@router.get("/auth/users", response_model=UsersResponse)
async def users(
    request: Request,
    _: Annotated[AuthUser, Depends(require_admin)],
) -> UsersResponse:
    return UsersResponse(users=list_users(request))


@router.post("/auth/users", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreateRequest,
    request: Request,
    _: Annotated[AuthUser, Depends(require_admin)],
) -> PublicUser:
    try:
        user = request.app.state.user_store.create_user(req.username, req.password, req.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _public_user(user)


@router.patch("/auth/users/{username}/role", response_model=PublicUser)
async def update_user_role(
    username: str,
    req: UserRoleRequest,
    request: Request,
    _: Annotated[AuthUser, Depends(require_admin)],
) -> PublicUser:
    try:
        user = request.app.state.user_store.update_role(username, req.role)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _public_user(user)


@router.post("/auth/users/{username}/password", response_model=PublicUser)
async def reset_user_password(
    username: str,
    req: PasswordResetRequest,
    request: Request,
    _: Annotated[AuthUser, Depends(require_admin)],
) -> PublicUser:
    try:
        user = request.app.state.user_store.reset_password(username, req.password)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _public_user(user)


@router.delete("/auth/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    username: str,
    request: Request,
    _: Annotated[AuthUser, Depends(require_admin)],
) -> None:
    try:
        request.app.state.user_store.delete_user(username)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
