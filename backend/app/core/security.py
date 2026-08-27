import hashlib
import hmac
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MIN_PASSWORD_LENGTH = 8

COMMON_PASSWORDS = frozenset(
    {
        "12345678",
        "123456789012",
        "1234567890ab",
        "administrator",
        "changeme12345",
        "hkustgz123456",
        "letmein123456",
        "password",
        "password1234",
        "qwerty12",
        "qwerty123456",
        "welcome12345",
    }
)


class PasswordPolicyViolation(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class PasswordVerification:
    valid: bool
    needs_rehash: bool = False


class PasswordManager:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=2,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> PasswordVerification:
        try:
            valid = self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return PasswordVerification(valid=False)
        return PasswordVerification(
            valid=valid,
            needs_rehash=valid and self._hasher.check_needs_rehash(password_hash),
        )

    def consume_dummy_verification(self, password: str) -> None:
        self.verify(self._dummy_hash, password)


@lru_cache
def get_password_manager() -> PasswordManager:
    return PasswordManager()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_login_identifier(value: str, *, domain: str = "connect.hkust-gz.edu.cn") -> str:
    normalized = normalize_email(value)
    return normalized if "@" in normalized else f"{normalized}@{domain}"


def is_campus_email(value: str, *, domain: str = "connect.hkust-gz.edu.cn") -> bool:
    normalized = normalize_email(value)
    local, separator, email_domain = normalized.rpartition("@")
    return bool(local and separator and email_domain == domain and "@" not in local)


def _identifier_fragment(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def validate_password(password: str, *, email: str, student_number: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyViolation("PASSWORD_TOO_SHORT")
    if len(password) > 128:
        raise PasswordPolicyViolation("PASSWORD_TOO_LONG")

    normalized_password = password.casefold().strip()
    compact_password = _identifier_fragment(password)
    if normalized_password in COMMON_PASSWORDS:
        raise PasswordPolicyViolation("COMMON_PASSWORD")

    email_local = normalize_email(email).partition("@")[0]
    protected_fragments = {
        _identifier_fragment(email_local),
        _identifier_fragment(student_number),
    }
    if any(
        fragment and len(fragment) >= 4 and fragment in compact_password
        for fragment in protected_fragments
    ):
        raise PasswordPolicyViolation("PASSWORD_TOO_SIMILAR")


def random_urlsafe_token(byte_length: int = 32) -> str:
    return urlsafe_b64encode(secrets.token_bytes(byte_length)).rstrip(b"=").decode("ascii")


def sha256_hexdigest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PepperedTokenHasher:
    def __init__(self, current_secret: str, previous_secret: str | None = None) -> None:
        self._current_secret = current_secret.encode("utf-8")
        self._previous_secret = (
            previous_secret.encode("utf-8") if previous_secret is not None else None
        )

    def current_hash(self, token: str) -> str:
        return hmac.new(self._current_secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def candidate_hashes(self, token: str) -> tuple[str, ...]:
        current = self.current_hash(token)
        if self._previous_secret is None:
            return (current,)
        previous = hmac.new(
            self._previous_secret,
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return (current, previous)


def tokens_match(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


class OutboxCipher:
    _AAD = b"pnx-outbox-secret-v1"

    def __init__(self, encoded_key: str) -> None:
        self._cipher = AESGCM(urlsafe_b64decode(encoded_key.encode("ascii")))

    def encrypt(self, payload: dict[str, Any]) -> str:
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ciphertext = self._cipher.encrypt(nonce, plaintext, self._AAD)
        encoded = urlsafe_b64encode(nonce + ciphertext).rstrip(b"=").decode("ascii")
        return f"v1.{encoded}"

    def decrypt(self, value: str) -> dict[str, Any]:
        version, separator, encoded = value.partition(".")
        if version != "v1" or not separator:
            raise ValueError("unsupported outbox ciphertext version")
        padded = encoded + "=" * (-len(encoded) % 4)
        combined = urlsafe_b64decode(padded.encode("ascii"))
        if len(combined) <= 12:
            raise ValueError("invalid outbox ciphertext")
        try:
            plaintext = self._cipher.decrypt(combined[:12], combined[12:], self._AAD)
        except InvalidTag as exc:
            raise ValueError("invalid outbox ciphertext authentication tag") from exc
        decoded = json.loads(plaintext)
        if not isinstance(decoded, dict):
            raise ValueError("invalid outbox secret payload")
        return decoded
