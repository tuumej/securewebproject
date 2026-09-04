"""앱 설정 DB 접근 헬퍼. DB 값이 없으면 env fallback."""
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.settings import AppSetting


def get_setting(key: str, default: str = "") -> str:
    """DB에서 설정값을 읽는다. 없으면 default 반환."""
    db = SessionLocal()
    try:
        row = db.get(AppSetting, key)
        return row.value if row else default
    finally:
        db.close()


def set_setting(db: Session, key: str, value: str) -> None:
    """DB에 설정값을 upsert한다."""
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def get_telegram_config() -> tuple[str, str]:
    """(bot_token, chat_id) 반환. DB 우선, 없으면 env fallback."""
    from app.core.config import settings
    token = get_setting("telegram_bot_token") or settings.telegram_bot_token
    chat_id = get_setting("telegram_chat_id") or settings.telegram_chat_id
    return token, chat_id
