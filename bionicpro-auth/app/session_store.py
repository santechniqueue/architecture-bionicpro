import json
import time
import uuid

from redis import Redis

from app.config import Settings
from app.crypto import TokenCipher
from app.models import SessionData, TokenPayload, UserInfo


class SessionStore:
    def __init__(self, redis_client: Redis, settings: Settings, cipher: TokenCipher):
        self.redis = redis_client
        self.settings = settings
        self.cipher = cipher

    def _key(self, session_id: str) -> str:
        return f"{self.settings.redis_session_prefix}{session_id}"

    def create_session(self, user: UserInfo, token_payload: TokenPayload) -> SessionData:
        now = int(time.time())
        session_id = uuid.uuid4().hex

        refresh_token_expires_at = None
        if token_payload.refresh_expires_in:
            refresh_token_expires_at = now + int(token_payload.refresh_expires_in)

        session = SessionData(
            session_id=session_id,
            username=user.preferred_username or "unknown",
            email=user.email,
            roles=user.roles,
            access_token=token_payload.access_token,
            access_token_expires_at=now + int(token_payload.expires_in),
            refresh_token_encrypted=self.cipher.encrypt(token_payload.refresh_token),
            refresh_token_expires_at=refresh_token_expires_at,
            keycloak_session_state=token_payload.session_state,
            created_at=now,
            updated_at=now,
        )
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> SessionData | None:
        payload = self.redis.get(self._key(session_id))
        if not payload:
            return None
        data = json.loads(payload)
        return SessionData.model_validate(data)

    def save_session(self, session: SessionData) -> None:
        session.updated_at = int(time.time())
        self.redis.setex(
            self._key(session.session_id),
            self.settings.session_ttl_seconds,
            session.model_dump_json(),
        )

    def delete_session(self, session_id: str) -> None:
        self.redis.delete(self._key(session_id))

    def rotate_session_id(self, session: SessionData) -> SessionData:
        old_session_id = session.session_id
        session.session_id = uuid.uuid4().hex
        session.updated_at = int(time.time())
        self.save_session(session)
        self.delete_session(old_session_id)
        return session

    def get_refresh_token(self, session: SessionData) -> str:
        return self.cipher.decrypt(session.refresh_token_encrypted)

    def update_tokens(
        self,
        session: SessionData,
        access_token: str,
        expires_in: int,
        refresh_token: str | None,
        refresh_expires_in: int | None,
        session_state: str | None,
    ) -> SessionData:
        now = int(time.time())
        session.access_token = access_token
        session.access_token_expires_at = now + int(expires_in)

        if refresh_token:
            session.refresh_token_encrypted = self.cipher.encrypt(refresh_token)

        if refresh_expires_in:
            session.refresh_token_expires_at = now + int(refresh_expires_in)

        if session_state:
            session.keycloak_session_state = session_state

        self.save_session(session)
        return session