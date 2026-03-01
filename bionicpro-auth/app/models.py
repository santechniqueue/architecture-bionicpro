from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class TokenPayload(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int | None = None
    token_type: str
    scope: str | None = None
    id_token: str | None = None
    session_state: str | None = None


class SessionData(BaseModel):
    session_id: str
    username: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)

    access_token: str
    access_token_expires_at: int

    refresh_token_encrypted: str
    refresh_token_expires_at: int | None = None

    keycloak_session_state: str | None = None

    created_at: int
    updated_at: int


class AuthStatePayload(BaseModel):
    state: str
    return_to: str


class UserInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sub: str | None = None
    preferred_username: str | None = None
    email: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    realm_access: dict[str, Any] | None = None

    yandex_id: str | None = None
    yandex_login: str | None = None
    yandex_psuid: str | None = None
    yandex_default_email: str | None = None
    yandex_display_name: str | None = None
    yandex_real_name: str | None = None
    yandex_avatar_id: str | None = None

    @property
    def roles(self) -> list[str]:
        if not self.realm_access:
            return []
        raw_roles = self.realm_access.get("roles")
        if isinstance(raw_roles, list):
            return [str(role) for role in raw_roles]
        return []

    @property
    def is_yandex_user(self) -> bool:
        return bool(self.yandex_id or self.yandex_login or self.yandex_psuid)