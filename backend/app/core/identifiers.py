import secrets
import time
from uuid import UUID


def uuid7(*, timestamp_ms: int | None = None) -> UUID:
    """Generate an RFC 9562 UUIDv7 using the system CSPRNG."""
    resolved_timestamp = timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000
    if not 0 <= resolved_timestamp < 1 << 48:
        raise ValueError("timestamp_ms is outside the UUIDv7 48-bit range")

    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (resolved_timestamp << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return UUID(int=value)
