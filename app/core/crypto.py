"""자격증명 암호화 — settings.secret_key로부터 Fernet 키를 유도한다.

진단(diagnosis) 기능에서 등록한 SSH 비밀번호/개인키를 DB에 평문으로 저장하지 않기
위해 사용한다. SECRET_KEY가 바뀌면 기존에 암호화된 값은 복호화할 수 없다.
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache
def _get_fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """평문을 암호화해 저장 가능한 문자열로 반환한다."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """암호화된 문자열을 평문으로 복호화한다. SECRET_KEY 불일치 시 ValueError."""
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("자격증명 복호화 실패 (SECRET_KEY 불일치 가능)") from exc
