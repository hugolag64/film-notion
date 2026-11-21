import logging

from backend.core.log_redaction import SecretRedactionFilter, redact


def test_redacts_query_string_keys_and_mediabrowser_tokens():
    line = (
        'GET https://api.themoviedb.org/3/search/movie?api_key=tmdb123&query=dune '
        'Authorization: MediaBrowser Client="Backstage", Token="jelly456" X-Api-Key: seerr789'
    )
    cleaned = redact(line)
    for secret in ("tmdb123", "jelly456", "seerr789"):
        assert secret not in cleaned
    assert "query=dune" in cleaned and 'Client="Backstage"' in cleaned


def test_filter_masks_secrets_passed_as_log_arguments():
    record = logging.LogRecord("httpx", logging.WARNING, __file__, 1, "HTTP Request: %s", ("http://x/a?apikey=s3cret",), None)
    assert SecretRedactionFilter().filter(record) is True
    assert "s3cret" not in record.getMessage()
