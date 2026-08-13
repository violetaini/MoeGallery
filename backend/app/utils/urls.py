from urllib.parse import urlsplit


def normalize_http_url(value: str | None, *, max_length: int = 1000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"URL must not exceed {max_length} characters")
    if "\\" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("URL contains invalid characters")
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("URL is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https")
    if parsed.username or parsed.password or any(char.isspace() for char in parsed.netloc):
        raise ValueError("URL contains invalid authority information")
    return text
