"""진단 대상 SSH 자격증명 암호화(app.core.crypto) 라운드트립 테스트."""
import pytest

from app.core.crypto import decrypt_secret, encrypt_secret


def test_roundtrip_password() -> None:
    plaintext = "sup3r-s3cret-passw0rd!"
    token = encrypt_secret(plaintext)
    assert token != plaintext
    assert decrypt_secret(token) == plaintext


def test_roundtrip_multiline_private_key() -> None:
    plaintext = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----\n"
    token = encrypt_secret(plaintext)
    assert decrypt_secret(token) == plaintext


def test_encrypt_is_nondeterministic() -> None:
    plaintext = "same-input"
    assert encrypt_secret(plaintext) != encrypt_secret(plaintext)


def test_decrypt_garbage_raises_value_error() -> None:
    with pytest.raises(ValueError):
        decrypt_secret("not-a-valid-fernet-token")
