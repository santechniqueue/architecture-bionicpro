import secrets
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.dependencies import (
    get_current_session,
    get_keycloak_client,
    get_settings,
    get_store,
)
from app.keycloak_client import KeycloakClient
from app.models import SessionData
from app.session_store import SessionStore
from app.db import init_db, SessionLocal
from app.profile_repository import YandexProfileRepository

app = FastAPI(title="bionicpro-auth")

settings = Settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id", "Content-Disposition"],
)


def build_callback_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")

    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}/auth/callback"

    return str(request.url_for("auth_callback"))


def validate_return_to(value: str, fallback: str) -> str:
    try:
        parsed = urlparse(value)
        fallback_parsed = urlparse(fallback)
        if parsed.scheme in {"http", "https"} and parsed.netloc == fallback_parsed.netloc:
            return value
    except Exception:
        pass
    return fallback


def persist_yandex_profile(user) -> None:
    if not getattr(user, "is_yandex_user", False):
        return

    db = SessionLocal()
    try:
        YandexProfileRepository(db).upsert_from_userinfo(user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bionicpro-auth"}


@app.get("/auth/login")
async def login(
    request: Request,
    return_to: str | None = Query(default=None),
    cfg: Settings = Depends(get_settings),
    keycloak: KeycloakClient = Depends(get_keycloak_client),
):
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = keycloak.build_code_challenge(code_verifier)

    safe_return_to = validate_return_to(return_to or cfg.frontend_url, cfg.frontend_url)
    callback_url = build_callback_url(request)

    redirect = RedirectResponse(
        url=keycloak.build_authorization_url(
            callback_url,
            state,
            code_challenge,
        ),
        status_code=status.HTTP_302_FOUND,
    )

    redirect.set_cookie(
        key=cfg.auth_state_cookie_name,
        value=f"{state}|{safe_return_to}|{code_verifier}",
        max_age=cfg.auth_state_ttl_seconds,
        secure=cfg.session_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return redirect


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    cfg: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
    keycloak: KeycloakClient = Depends(get_keycloak_client),
):
    if error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": error,
                "error_description": error_description or "Authorization failed",
            },
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code or state",
        )

    state_cookie = request.cookies.get(cfg.auth_state_cookie_name)
    if not state_cookie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing auth state")

    parts = state_cookie.split("|", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auth state")

    expected_state, return_to, code_verifier = parts
    if state != expected_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auth state")

    callback_url = build_callback_url(request)
    token_payload = await keycloak.exchange_code(
        code=code,
        redirect_uri=callback_url,
        code_verifier=code_verifier,
    )

    try:
        user = keycloak.build_user_from_tokens(token_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Failed to build user profile from tokens",
                "error": str(exc),
            },
        ) from exc

    persist_yandex_profile(user)
    session = store.create_session(user=user, token_payload=token_payload)

    redirect = RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=cfg.session_cookie_name,
        value=session.session_id,
        max_age=cfg.session_ttl_seconds,
        secure=cfg.session_cookie_secure,
        httponly=cfg.session_cookie_httponly,
        samesite=cfg.session_cookie_samesite,
        path="/",
    )
    redirect.delete_cookie(cfg.auth_state_cookie_name, path="/")
    return redirect


@app.get("/auth/me")
async def me(
    request: Request,
    cfg: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
):
    session_id = request.cookies.get(cfg.session_cookie_name)
    if not session_id:
        return JSONResponse({"authenticated": False}, status_code=200)

    session = store.get_session(session_id)
    if not session:
        return JSONResponse({"authenticated": False}, status_code=200)

    return {
        "authenticated": True,
        "username": session.username,
        "email": session.email,
        "roles": session.roles,
    }


@app.post("/auth/logout")
async def logout(
    request: Request,
    cfg: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
    keycloak: KeycloakClient = Depends(get_keycloak_client),
):
    session_id = request.cookies.get(cfg.session_cookie_name)
    if session_id:
        session = store.get_session(session_id)
        if session:
            refresh_token = store.get_refresh_token(session)
            await keycloak.revoke(refresh_token)
            store.delete_session(session_id)

    response = JSONResponse({"ok": True})
    response.delete_cookie(cfg.session_cookie_name, path="/")
    return response


@app.get("/reports")
async def proxy_reports(
    request: Request,
    response: Response,
    session: SessionData = Depends(get_current_session),
    cfg: Settings = Depends(get_settings),
):
    headers = {
        "Authorization": f"Bearer {session.access_token}",
        "Accept": "application/json,text/plain,*/*",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        upstream = await client.get(f"{cfg.reports_api_url}/reports", headers=headers)

    content_type = upstream.headers.get("content-type", "application/json")

    proxied = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=content_type,
    )

    disposition = upstream.headers.get("content-disposition")
    if disposition:
        proxied.headers["Content-Disposition"] = disposition

    rotated_cookie = response.headers.get("set-cookie")
    if rotated_cookie:
        proxied.headers.append("set-cookie", rotated_cookie)

    rotated_session = response.headers.get("X-Session-Id")
    if rotated_session:
        proxied.headers["X-Session-Id"] = rotated_session

    return proxied