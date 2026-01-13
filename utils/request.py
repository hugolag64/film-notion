import requests

def safe_get_json(url: str, timeout=10) -> dict:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {
            "_error": True,
            "_message": str(e),
            "_url": url
        }
