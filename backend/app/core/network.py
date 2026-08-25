import ipaddress
import re

from fastapi import Request

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
    candidates = [forwarded, request.client.host if request.client is not None else ""]
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return "0.0.0.0"


def summarize_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    prefix_length = 24 if address.version == 4 else 64
    return str(ipaddress.ip_network(f"{address}/{prefix_length}", strict=False))


def request_ip_prefix(request: Request) -> str:
    return summarize_ip(client_ip(request))


def summarize_user_agent(value: str | None) -> str:
    sanitized = _CONTROL_CHARACTERS.sub(" ", value or "")
    compact = " ".join(sanitized.split())
    browser = "Other browser"
    if "Edg/" in compact:
        browser = "Edge"
    elif "Firefox/" in compact:
        browser = "Firefox"
    elif "Chrome/" in compact or "CriOS/" in compact:
        browser = "Chrome"
    elif "Safari/" in compact:
        browser = "Safari"

    platform = "Other device"
    if "Windows" in compact:
        platform = "Windows"
    elif "Android" in compact:
        platform = "Android"
    elif "iPhone" in compact or "iPad" in compact:
        platform = "iOS"
    elif "Mac OS" in compact or "Macintosh" in compact:
        platform = "macOS"
    elif "Linux" in compact:
        platform = "Linux"
    return f"{browser} / {platform}"
