import time

from fastapi import Depends, HTTPException, Request, Response, status
from redis import Redis

from app.config import Settings
from app.crypto import TokenCipher
from app.keycloak_client import KeycloakClient
from app.models import SessionData
from app.session_store import SessionStore


def get_settings() -> Settings:
    return Settings()


def get_redis(settings: Settings = Depends(get_settings)) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_cipher(settings: Settings = Depends(get_settings)) -> TokenCipher:
    return TokenCipher(settings.refresh_token_encryption_key)


def get_store(
    redis_client: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    cipher: TokenCipher = Depends(get_cipher),
) -> SessionStore:
    return SessionStore(redis_client=redis_client, settings=settings, cipher=cipher)


def get_keycloak_client(settings: Settings = Depends(get_settings)) -> KeycloakClient:
    return KeycloakClient(settings)


async def get_current_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    store: SessionStore = Depends(get_store),
    keycloak: KeycloakClient = Depends(get_keycloak_client),
) -> SessionData:
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No session")

    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    now = int(time.time())
    must_refresh = session.access_token_expires_at <= (
        now + settings.refresh_access_token_skew_seconds
    )

    if must_refresh:
        refresh_token = store.get_refresh_token(session)
        try:
            refreshed = await keycloak.refresh(refresh_token)
        except Exception as exc:
            store.delete_session(session.session_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired",
            ) from exc

        store.update_tokens(
            session=session,
            access_token=refreshed.access_token,
            expires_in=refreshed.expires_in,
            refresh_token=refreshed.refresh_token,
            refresh_expires_in=refreshed.refresh_expires_in,
            session_state=refreshed.session_state,
        )

    if settings.rotate_session_every_request:
        session = store.rotate_session_id(session)
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session.session_id,
            max_age=settings.session_ttl_seconds,
            secure=settings.session_cookie_secure,
            httponly=settings.session_cookie_httponly,
            samesite=settings.session_cookie_samesite,
            path="/",
        )
        response.headers["X-Session-Id"] = session.session_id

    return session