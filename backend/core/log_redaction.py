"""Keep API keys and tokens out of the logs, whatever library writes them."""
import logging
import re

REDACTED = "<redacted>"

_PATTERNS = (
    # Query strings: ?api_key=…, &apikey=…, &token=…, &X-Emby-Token=…
    (re.compile(r"(?i)([?&](?:api_?key|access_token|token|x-emby-token)=)[^&\s\"']+"), rf"\1{REDACTED}"),
    # MediaBrowser / Emby authorization header values: Token="…"
    (re.compile(r'(?i)(\bToken=")[^"]*(")'), rf"\1{REDACTED}\2"),
    # Plain headers that may end up in a repr: X-Api-Key: …, X-Emby-Token: …
    (re.compile(r"(?i)((?:x-api-key|x-emby-token)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"), rf"\1{REDACTED}"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Rewrites each record's final message with secrets masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a broken format string must not drop the log line
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def install() -> None:
    """Attach the filter to every root handler and quiet per-request httpx logs."""
    redaction = SecretRedactionFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(existing, SecretRedactionFilter) for existing in handler.filters):
            handler.addFilter(redaction)
    # httpx logs every request URL at INFO, and TMDB takes its key in the query string.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
