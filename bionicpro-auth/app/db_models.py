from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Settings
from app.db import Base

settings = Settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class YandexProfile(Base):
    __tablename__ = "yandex_profiles"
    __table_args__ = (
        UniqueConstraint("yandex_user_id", name="uq_yandex_profiles_yandex_user_id"),
        {"schema": settings.database_schema},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keycloak_username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    yandex_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    yandex_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_psuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_default_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_real_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_avatar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raw_claims: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )