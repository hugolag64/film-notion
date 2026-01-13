import re
import unicodedata
from difflib import SequenceMatcher

def normalize_title(title: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", title.lower())
        if c.isalnum()
    )

def clean_search_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\(\d{4}\)", "", t)
    t = re.sub(r"\d{4}", "", t)
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"[:\-–]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def extract_year(title: str):
    m = re.search(r"(19|20)\d{2}", title)
    return m.group() if m else None

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()
