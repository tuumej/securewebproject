"""인증 유틸리티 — 비밀번호 해싱, 세션 헬퍼, FastAPI 의존성."""
import hashlib
import secrets
import time

from fastapi import HTTPException
from starlette.requests import Request


def hash_password(password: str) -> str:
    """PBKDF2-SHA256으로 비밀번호를 해싱한다. 형식: salt:hex_digest"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """저장된 해시와 입력 비밀번호를 타이밍 안전하게 비교한다."""
    try:
        salt, dk_hex = stored.split(":", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return secrets.compare_digest(dk.hex(), dk_hex)


def get_session_timeout_minutes() -> int:
    """세션 타임아웃(분)을 AppSetting에서 읽는다. 기본 30분."""
    try:
        from app.services.app_settings import get_setting
        val = get_setting("session_timeout_minutes", "30")
        return max(1, int(val))
    except Exception:
        return 30


def check_session(request: Request) -> str | None:
    """세션 유효성을 검사하고 활성이면 last_activity를 갱신한다.

    - 로그인 안 됨 → None
    - 세션 만료 → 세션 클리어 후 None
    - 정상 → 사용자명 반환
    """
    username = request.session.get("username")
    if not username:
        return None

    last = request.session.get("last_activity", 0)
    timeout_sec = get_session_timeout_minutes() * 60
    now = time.time()

    if now - last > timeout_sec:
        request.session.clear()
        return None

    request.session["last_activity"] = now
    return username


def require_login_api(request: Request) -> str:
    """API 엔드포인트용 FastAPI 의존성 — 미로그인/만료 시 401을 반환한다."""
    user = check_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user
