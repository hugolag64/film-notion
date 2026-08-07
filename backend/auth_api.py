"""Authentication and authorization routes for Backstage."""

import logging
import os
from dataclasses import dataclass
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from urllib.parse import quote

from backend.config import Config
from backend.core.auth import AuthStore, AuthUser
from backend.core.email import EmailSender
from backend.core.jellyfin import JellyfinClient
from backend.core.rate_limit import RateLimiter


SESSION_COOKIE = "backstage_session"
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)
LOGIN_RATE_LIMITER = RateLimiter(
    Config.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
    Config.AUTH_RATE_LIMIT_WINDOW_SEC,
    Config.AUTH_RATE_LIMIT_BLOCK_SEC,
)
RESET_RATE_LIMITER = RateLimiter(
    Config.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
    Config.AUTH_RATE_LIMIT_WINDOW_SEC,
    Config.AUTH_RATE_LIMIT_BLOCK_SEC,
)


@dataclass(frozen=True)
class AuthContext:
    user: AuthUser
    session_id: str
    token: str


class SetupRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    password_confirmation: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_device: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    password_confirmation: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
    password_confirmation: str


class CreateUserRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=3)
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class JellyfinLinkRequest(BaseModel):
    jellyfin_user_id: str | None = None


def get_auth_store() -> AuthStore:
    return AuthStore(Config.DB_PATH)


def get_jellyfin_client() -> JellyfinClient | None:
    if not Config.jellyfin_enabled():
        return None
    return JellyfinClient(
        Config.JELLYFIN_URL,
        Config.JELLYFIN_API_KEY,
        server_id=Config.JELLYFIN_SERVER_ID,
    )


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


def _rate_limit_key(request: Request, identity: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{identity.strip().casefold()}"


def _check_rate_limit(limiter: RateLimiter, key: str) -> None:
    decision = limiter.check(key)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Réessayez plus tard.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


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
    if message == "user not found":
        return HTTPException(status_code=404, detail=message)
    if message in {
        "administrator already exists",
        "email already exists",
        "last administrator cannot be removed",
        "jellyfin user already linked",
    }:
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
    rate_limit_key = _rate_limit_key(request, payload.email)
    _check_rate_limit(LOGIN_RATE_LIMITER, rate_limit_key)
    try:
        user, token, _ = store.authenticate(
            payload.email, payload.password, payload.remember_device,
            request.headers.get("user-agent"),
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Identifiants invalides") from error
    LOGIN_RATE_LIMITER.clear(rate_limit_key)
    _set_session_cookie(response, token, payload.remember_device)
    return {"user": user}


@auth_router.post("/change-password")
async def change_password(
    payload: PasswordChangeRequest,
    current: AuthContext = Depends(get_current_user),
    store: AuthStore = Depends(get_auth_store),
):
    if payload.new_password != payload.password_confirmation:
        raise HTTPException(status_code=422, detail="Les mots de passe ne correspondent pas")
    try:
        store.change_password(
            current.user["id"], payload.current_password, payload.new_password,
            current.session_id,
        )
    except ValueError as error:
        raise _handle_store_error(error) from error
    return {"message": "Mot de passe modifié"}


@auth_router.post("/forgot-password", status_code=202)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    store: AuthStore = Depends(get_auth_store),
):
    _check_rate_limit(RESET_RATE_LIMITER, _rate_limit_key(request, payload.email))
    reset = store.create_password_reset_token(payload.email)
    if reset is not None:
        token, _ = reset
        reset_url = (
            f"{Config.BACKSTAGE_PUBLIC_URL.rstrip('/')}/reset-password?token={quote(token, safe='')}"
        )
        try:
            EmailSender().send_password_reset(payload.email, reset_url)
        except Exception:
            logger.exception("Échec de l'envoi du lien de réinitialisation")
    return {"message": "Si un compte correspond, un e-mail vient d'être envoyé."}


@auth_router.post("/reset-password")
async def reset_password(
    payload: PasswordResetRequest,
    store: AuthStore = Depends(get_auth_store),
):
    if payload.new_password != payload.password_confirmation:
        raise HTTPException(status_code=422, detail="Les mots de passe ne correspondent pas")
    try:
        store.reset_password(payload.token, payload.new_password)
    except ValueError as error:
        if str(error) == "invalid or expired reset token":
            raise HTTPException(status_code=400, detail=str(error)) from error
        raise _handle_store_error(error) from error
    return {"message": "Mot de passe réinitialisé"}


@auth_router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, store: AuthStore = Depends(get_auth_store)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        store.revoke_token(token)
    _clear_session_cookie(response)


@auth_router.get("/me")
async def current_user(user: AuthContext = Depends(get_current_user)):
    return {"user": user.user}


async def _fetch_jellyfin_users(client: JellyfinClient | None) -> list[dict]:
    if client is None:
        raise HTTPException(status_code=503, detail="Jellyfin n'est pas configuré")
    try:
        return await client.list_users()
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Jellyfin users unavailable: %s", error)
        raise HTTPException(status_code=503, detail="Jellyfin est indisponible") from error


@auth_router.get("/jellyfin-users")
async def list_jellyfin_users(
    _: AuthContext = Depends(require_admin),
):
    return {"users": await _fetch_jellyfin_users(get_jellyfin_client())}


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


@auth_router.put("/users/{user_id}/jellyfin")
async def link_jellyfin_user(
    user_id: str,
    payload: JellyfinLinkRequest,
    _: AuthContext = Depends(require_admin),
    store: AuthStore = Depends(get_auth_store),
):
    jellyfin_user_id = payload.jellyfin_user_id.strip() if payload.jellyfin_user_id else None
    if jellyfin_user_id is not None:
        jellyfin_users = await _fetch_jellyfin_users(get_jellyfin_client())
        if not any(item["id"] == jellyfin_user_id for item in jellyfin_users):
            raise HTTPException(status_code=422, detail="Compte Jellyfin introuvable")
    try:
        user = store.set_jellyfin_user_id(user_id, jellyfin_user_id)
    except ValueError as error:
        raise _handle_store_error(error) from error
    return {"user": user}


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
        fields = payload.model_dump(exclude_unset=True)
        password = fields.pop("password", None)
        user = store.update_user(user_id, fields)
        if password is not None:
            store.set_password(user_id, password)
    except ValueError as error:
        raise _handle_store_error(error) from error
    return {"user": user}


@auth_router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    current: AuthContext = Depends(require_admin),
    store: AuthStore = Depends(get_auth_store),
):
    if user_id == current.user["id"]:
        raise HTTPException(status_code=400, detail="Impossible de supprimer son propre compte")
    try:
        store.delete_user(user_id)
    except ValueError as error:
        raise _handle_store_error(error) from error
