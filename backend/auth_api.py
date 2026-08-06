"""Authentication and authorization routes for Backstage."""

import os
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.config import Config
from backend.core.auth import AuthStore, AuthUser


SESSION_COOKIE = "backstage_session"
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@dataclass(frozen=True)
class AuthContext:
    user: AuthUser
    session_id: str
    token: str


class SetupRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=12)
    password_confirmation: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_device: bool = False


class CreateUserRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=12)


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=3)
    role: str | None = None
    is_active: bool | None = None


def get_auth_store() -> AuthStore:
    return AuthStore(Config.DB_PATH)


def _cookie_secure() -> bool:
    return os.getenv("BACKSTAGE_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}


def _set_session_cookie(response: Response, token: str, remember_device: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60 if remember_device else None,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=_cookie_secure(), samesite="lax")


async def get_current_user(
    request: Request, store: AuthStore = Depends(get_auth_store)
) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    session = store.user_from_token(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    user, session_id = session
    return AuthContext(user=user, session_id=session_id, token=token)


async def require_admin(user: AuthContext = Depends(get_current_user)) -> AuthContext:
    if user.user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis")
    return user


def _handle_store_error(error: ValueError) -> HTTPException:
    message = str(error)
    if message in {"administrator already exists", "email already exists"}:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


@auth_router.get("/status")
async def auth_status(store: AuthStore = Depends(get_auth_store)):
    return {"setup_required": not any(user["role"] == "admin" for user in store.list_users())}


@auth_router.post("/setup")
async def setup_admin(
    payload: SetupRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
):
    if payload.password != payload.password_confirmation:
        raise HTTPException(status_code=422, detail="Les mots de passe ne correspondent pas")
    try:
        store.create_admin(payload.display_name, payload.email, payload.password)
        user, token, _ = store.authenticate(
            payload.email, payload.password, False, request.headers.get("user-agent")
        )
    except ValueError as error:
        raise _handle_store_error(error) from error
    _set_session_cookie(response, token, False)
    return {"user": user}


@auth_router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
):
    try:
        user, token, _ = store.authenticate(
            payload.email, payload.password, payload.remember_device,
            request.headers.get("user-agent"),
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Identifiants invalides") from error
    _set_session_cookie(response, token, payload.remember_device)
    return {"user": user}


@auth_router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, store: AuthStore = Depends(get_auth_store)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        store.revoke_token(token)
    _clear_session_cookie(response)


@auth_router.get("/me")
async def current_user(user: AuthContext = Depends(get_current_user)):
    return {"user": user.user}


@auth_router.get("/devices")
async def devices(user: AuthContext = Depends(get_current_user), store: AuthStore = Depends(get_auth_store)):
    return {"devices": store.list_sessions(user.user["id"], user.session_id)}


@auth_router.delete("/devices/{session_id}", status_code=204)
async def revoke_device(
    session_id: str,
    user: AuthContext = Depends(get_current_user),
    store: AuthStore = Depends(get_auth_store),
):
    store.revoke_session(user.user["id"], session_id)


@auth_router.post("/devices/revoke-others")
async def revoke_other_devices(
    user: AuthContext = Depends(get_current_user),
    store: AuthStore = Depends(get_auth_store),
):
    return {"revoked": store.revoke_other_sessions(user.user["id"], user.session_id)}


@auth_router.get("/users")
async def list_users(
    _: AuthContext = Depends(require_admin), store: AuthStore = Depends(get_auth_store)
):
    return {"users": store.list_users()}


@auth_router.post("/users")
async def create_user(
    payload: CreateUserRequest,
    _: AuthContext = Depends(require_admin),
    store: AuthStore = Depends(get_auth_store),
):
    try:
        user = store.create_user(payload.display_name, payload.email, payload.password)
    except ValueError as error:
        raise _handle_store_error(error) from error
    return {"user": user}


@auth_router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    _: AuthContext = Depends(require_admin),
    store: AuthStore = Depends(get_auth_store),
):
    try:
        user = store.update_user(user_id, payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise _handle_store_error(error) from error
    return {"user": user}
