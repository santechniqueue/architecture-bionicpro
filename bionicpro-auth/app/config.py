from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "bionicpro-auth"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    frontend_url: str = "http://localhost:3000"
    reports_api_url: str = "http://reports-api:8001"

    keycloak_internal_base_url: str = "http://keycloak:8080"
    keycloak_public_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "reports-realm"
    keycloak_client_id: str = "bionicpro-auth"
    keycloak_client_secret: str = "change-me"

    session_cookie_name: str = "bp_session"
    session_cookie_secure: bool = True
    session_cookie_httponly: bool = True
    session_cookie_samesite: str = "lax"
    session_ttl_seconds: int = 1800

    auth_state_cookie_name: str = "bp_auth_state"
    auth_state_ttl_seconds: int = 300

    redis_url: str = "redis://redis:6379/0"
    redis_session_prefix: str = "bp:sessions:"
    refresh_token_encryption_key: str = Field(
        default="0123456789abcdef0123456789abcdef",
        description="32-byte key for AES-256, passed as raw string",
    )

    rotate_session_every_request: bool = True
    refresh_access_token_skew_seconds: int = 15

    database_url: str = (
        "postgresql+psycopg2://keycloak_user:keycloak_password@keycloak_db:5432/keycloak_db"
    )
    database_schema: str = "bionicpro_auth"

    yandex_idp_alias: str = "yandex"