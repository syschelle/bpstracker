from app.security import (
    decrypt_secret,
    encrypt_secret,
    is_argon2id_hash,
    normalize_recovery_code,
    password_hash,
    verify_password,
)


def test_password_hash_uses_argon2id() -> None:
    hashed = password_hash('SehrSicher123!')
    assert is_argon2id_hash(hashed)
    assert verify_password('SehrSicher123!', hashed)
    assert not verify_password('falsch', hashed)


def test_secret_encryption_roundtrip() -> None:
    encrypted = encrypt_secret('TOPSECRET')
    assert encrypted != 'TOPSECRET'
    assert decrypt_secret(encrypted) == 'TOPSECRET'


def test_recovery_code_normalization() -> None:
    assert normalize_recovery_code('abcd-ef12 gh34') == 'ABCDEF12GH34'
