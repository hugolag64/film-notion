"""Lecture des pages publiques de cine-reunion.com (Multiplexe Ciné Grand Sud).

Fonctions pures : elles reçoivent le HTML et renvoient des données, sans E/S.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Iterator, Optional

GRAND_SUD_PATH = "/programmation/multiplexe-cine-grand-sud-saint-pierre/"
UPCOMING_PATH = "/films/prochaines-sorties/"


@dataclass(frozen=True)
class Showtime:
    starts_at: datetime  # naïf, heure locale de La Réunion
    version: str
    booking_url: Optional[str]


@dataclass(frozen=True)
class ProgrammeFilm:
    site_id: int
    title: str
    url: str
    poster_url: Optional[str]
    showtimes: tuple[Showtime, ...]


@dataclass(frozen=True)
class FilmDetails:
    original_title: Optional[str]
    directors: tuple[str, ...]
    release_national: Optional[date]
    release_reunion: Optional[date]


@dataclass(frozen=True)
class UpcomingFilm:
    site_id: int
    title: str
    url: str
    poster_url: Optional[str]


# --- Petit arbre HTML -------------------------------------------------------

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


@dataclass
class _Node:
    tag: str
    attrs: dict
    parent: Optional["_Node"] = None
    children: list = field(default_factory=list)  # _Node ou str

    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def has_class(self, *names: str) -> bool:
        return set(names) <= self.classes()

    def iter(self) -> Iterator["_Node"]:
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.iter()

    def find_all(self, tag: str, *classes: str) -> list["_Node"]:
        return [n for n in self.iter() if n.tag == tag and n.has_class(*classes)]

    def find(self, tag: str, *classes: str) -> Optional["_Node"]:
        return next((n for n in self.iter() if n.tag == tag and n.has_class(*classes)), None)

    def text(self) -> str:
        parts = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return "".join(parts)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self._current = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v or "") for k, v in attrs}, self._current)
        self._current.children.append(node)
        if tag not in _VOID:
            self._current = node

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag, {k: (v or "") for k, v in attrs}, self._current)
        self._current.children.append(node)

    def handle_endtag(self, tag):
        node = self._current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self._current = node.parent

    def handle_data(self, data):
        self._current.children.append(data)


def _parse(html: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# --- Dates ------------------------------------------------------------------

_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}
_DATE_RE = re.compile(r"(\d{1,2})(?:er)?\s+([a-z]+)\s+(\d{4})")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def parse_french_date(text: str) -> Optional[date]:
    match = _DATE_RE.search(_fold(text or ""))
    if not match:
        return None
    month = _MONTHS.get(match.group(2))
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


# --- Pages ------------------------------------------------------------------

_FILM_HREF = re.compile(r"^/film/[^/]+/(\d+)/?$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _clean(text: str) -> str:
    return " ".join(text.split())


def _film_link(block: _Node) -> Optional[tuple[int, str]]:
    for a in block.find_all("a"):
        match = _FILM_HREF.match(a.attrs.get("href", ""))
        if match:
            return int(match.group(1)), a.attrs["href"]
    return None


def _poster(block: _Node) -> tuple[Optional[str], Optional[str]]:
    images = block.find("div", "movie__images")
    img = images.find("img") if images else None
    if img is None:
        return None, None
    title = _clean(img.attrs.get("alt", "")) or None
    return title, img.attrs.get("src") or None


def _showtimes(block: _Node) -> tuple[Showtime, ...]:
    result = []
    for group in block.find_all("div", "time-select__group"):
        place = group.find("p", "time-select__place")
        day = parse_french_date(place.text()) if place else None
        if day is None:
            continue
        for item in group.find_all("li", "time-select__item"):
            match = _TIME_RE.match(item.attrs.get("data-time", "").strip())
            if not match:
                continue
            spans = [_clean(c.text()) for c in item.children if isinstance(c, _Node) and c.tag == "span"]
            version = " ".join(s for s in spans if s)
            link = item.parent
            while link is not None and link.tag != "a":
                link = link.parent
            booking = link.attrs.get("href") or None if link is not None else None
            starts_at = datetime(day.year, day.month, day.day, int(match.group(1)), int(match.group(2)))
            result.append(Showtime(starts_at, version, booking))
    return tuple(result)


def parse_programme(html: str) -> list[ProgrammeFilm]:
    films = []
    for block in _parse(html).find_all("div", "movie", "movie--preview"):
        link = _film_link(block)
        if link is None:
            continue
        site_id, url = link
        title, poster = _poster(block)
        if not title:
            heading = block.find("a", "movie__title")
            title = _clean(heading.text()) if heading else ""
        if not title:
            continue
        films.append(ProgrammeFilm(site_id, title, url, poster, _showtimes(block)))
    return films


def parse_film_page(html: str) -> FilmDetails:
    values: dict[str, str] = {}
    for option in _parse(html).find_all("p", "movie__option"):
        label = option.find("strong")
        if label is None:
            continue
        key = _fold(_clean(label.text())).rstrip(" :")
        value_node = option.find("a")
        values[key] = _clean(value_node.text()) if value_node else ""
    directors = tuple(
        name.strip() for name in values.get("realisateur", "").split(",") if name.strip()
    )
    return FilmDetails(
        original_title=values.get("titre original") or None,
        directors=directors,
        release_national=parse_french_date(values.get("sortie nationale", "")),
        release_reunion=parse_french_date(values.get("sortie a la reunion", "")),
    )


def parse_upcoming(html: str) -> list[UpcomingFilm]:
    films = []
    for block in _parse(html).find_all("div", "movie", "movie--test"):
        link_node = block.find("a", "movie-beta__link")
        match = _FILM_HREF.match(link_node.attrs.get("href", "")) if link_node else None
        if not match:
            continue
        img = link_node.find("img")
        title = _clean(img.attrs.get("alt", "")) if img else ""
        if not title:
            continue
        films.append(UpcomingFilm(int(match.group(1)), title, link_node.attrs["href"],
                                  (img.attrs.get("src") or None) if img else None))
    return films
