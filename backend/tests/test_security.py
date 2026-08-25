from base64 import urlsafe_b64decode, urlsafe_b64encode

import pytest

from app.core.network import summarize_ip, summarize_user_agent
from app.core.security import (
    OutboxCipher,
    PasswordPolicyViolation,
    PepperedTokenHasher,
    get_password_manager,
    is_campus_email,
    normalize_email,
    normalize_login_identifier,
    random_urlsafe_token,
    sha256_hexdigest,
    validate_password,
)


@pytest.mark.parametrize(
    ("email", "accepted"),
    [
        ("student@connect.hkust-gz.edu.cn", True),
        (" Student@CONNECT.HKUST-GZ.EDU.CN ", True),
        ("student@hkust-gz.edu.cn", False),
        ("student@sub.connect.hkust-gz.edu.cn", False),
        ("student@connect.hkust-gz.edu.cn.example.org", False),
        ("student+connect.hkust-gz.edu.cn@example.org", False),
        ("@connect.hkust-gz.edu.cn", False),
    ],
)
def test_campus_email_matching_is_exact(email: str, accepted: bool) -> None:
    assert is_campus_email(email) is accepted


def test_email_normalization_trims_and_lowercases() -> None:
    assert normalize_email(" Student@CONNECT.HKUST-GZ.EDU.CN ") == "student@connect.hkust-gz.edu.cn"


@pytest.mark.parametrize(
    ("identifier", "normalized"),
    [
        (" Alice ", "alice@connect.hkust-gz.edu.cn"),
        (" Alice@CONNECT.HKUST-GZ.EDU.CN ", "alice@connect.hkust-gz.edu.cn"),
        ("legacy@hkust-gz.edu.cn", "legacy@hkust-gz.edu.cn"),
    ],
)
def test_login_identifier_normalizes_username_and_full_email(
    identifier: str, normalized: str
) -> None:
    assert normalize_login_identifier(identifier) == normalized


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short", "PASSWORD_TOO_SHORT"),
        ("password1234", "COMMON_PASSWORD"),
        ("student-unique-safe-password", "PASSWORD_TOO_SIMILAR"),
        ("20261234-is-not-safe", "PASSWORD_TOO_SIMILAR"),
    ],
)
def test_password_policy_rejects_weak_or_similar_values(password: str, reason: str) -> None:
    with pytest.raises(PasswordPolicyViolation, match=reason):
        validate_password(
            password,
            email="student@connect.hkust-gz.edu.cn",
            student_number="20261234",
        )


def test_argon2id_round_trip_and_wrong_password() -> None:
    manager = get_password_manager()
    encoded = manager.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert manager.verify(encoded, "correct horse battery staple").valid is True
    assert manager.verify(encoded, "wrong password").valid is False


def test_tokens_are_high_entropy_and_hashes_do_not_reveal_them() -> None:
    token = random_urlsafe_token()
    digest = sha256_hexdigest(token)

    assert len(token) >= 43
    assert len(digest) == 64
    assert token not in digest


def test_session_hasher_supports_previous_secret_rotation() -> None:
    previous = PepperedTokenHasher("p" * 32)
    rotating = PepperedTokenHasher("c" * 32, "p" * 32)
    token = random_urlsafe_token()

    assert previous.current_hash(token) in rotating.candidate_hashes(token)
    assert rotating.current_hash(token) != previous.current_hash(token)


def test_outbox_cipher_round_trip_and_tamper_detection() -> None:
    key = urlsafe_b64encode(b"k" * 32).decode("ascii")
    cipher = OutboxCipher(key)
    encrypted = cipher.encrypt({"token": "secret-token"})

    assert "secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == {"token": "secret-token"}
    tampered_bytes = bytearray(urlsafe_b64decode(encrypted.encode("ascii")))
    tampered_bytes[-1] ^= 1
    tampered = urlsafe_b64encode(tampered_bytes).decode("ascii")
    with pytest.raises(ValueError):
        cipher.decrypt(tampered)


def test_ip_and_user_agent_are_reduced_to_summaries() -> None:
    assert summarize_ip("192.168.1.99") == "192.168.1.0/24"
    assert summarize_ip("2001:db8::1234") == "2001:db8::/64"
    summary = summarize_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    )
    assert summary == "Chrome / Windows"
    assert "130.0" not in summary
