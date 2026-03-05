from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_models import YandexProfile
from app.models import UserInfo


class YandexProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_from_userinfo(self, user: UserInfo) -> YandexProfile | None:
        if not user.is_yandex_user or not user.yandex_id:
            return None

        stmt = select(YandexProfile).where(YandexProfile.yandex_user_id == user.yandex_id)
        entity = self.db.execute(stmt).scalar_one_or_none()

        if entity is None:
            entity = YandexProfile(
                keycloak_username=user.preferred_username or "unknown",
                email=user.email,
                yandex_user_id=user.yandex_id,
            )
            self.db.add(entity)

        entity.keycloak_username = user.preferred_username or entity.keycloak_username
        entity.email = user.email
        entity.yandex_login = user.yandex_login
        entity.yandex_psuid = user.yandex_psuid
        entity.yandex_default_email = user.yandex_default_email
        entity.yandex_display_name = user.yandex_display_name
        entity.yandex_real_name = user.yandex_real_name
        entity.yandex_avatar_id = user.yandex_avatar_id
        entity.raw_claims = user.model_dump(exclude_none=True)

        return entity