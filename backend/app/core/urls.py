from urllib.parse import urlsplit, urlunsplit


def normalize_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("URL 必须是无内嵌凭证的 http 或 https 地址")
    return urlunsplit(parsed)
