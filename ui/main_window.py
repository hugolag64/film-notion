import customtkinter as ctk
import tkinter as tk
from datetime import datetime
import re
import unicodedata
from difflib import SequenceMatcher

# === CORE ===
from core.notion import (
    fetch_all_pages,
    get_movies_to_enrich,
    get_title,
    get_release_date,
    update_movie_page,
    add_poster_and_backdrop,
    compute_tags_from_categories,
)
from core.calendar import sync_future_releases
from core.tmdb import search_movie, score_movie
from core.tmdb_utils import (
    extract_tmdb_id_from_url,
    extract_imdb_id_from_url,
    get_movie_by_tmdb_id,
    get_tmdb_movie_from_imdb_id,
)

# === UI ===
from ui.chooser import ask_choice

# === UTILS ===
from utils.text import clean_search_title, extract_year
from utils.request import safe_get_json
from config import TMDB_API_KEY


# ==================================================
# Helpers TMDB — LOGIQUE MÉTIER
# ==================================================

def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def title_matches(notion_title: str, tmdb_title: str) -> bool:
    return (
        SequenceMatcher(
            None,
            normalize_title(notion_title),
            normalize_title(tmdb_title)
        ).ratio() >= 0.85
    )


def is_released_tmdb(movie: dict) -> bool:
    date_str = movie.get("release_date")
    if not date_str:
        return False
    try:
        release_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return release_date <= datetime.now().date()


def get_director(movie_id: int) -> str:
    url = (
        f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
        f"?api_key={TMDB_API_KEY}&language=fr-FR"
    )
    data = safe_get_json(url)
    for crew in data.get("crew", []):
        if crew.get("job") == "Director":
            return crew.get("name", "")
    return ""


def get_movie_genres(movie_id: int) -> list[str]:
    url = (
        f"https://api.themoviedb.org/3/movie/{movie_id}"
        f"?api_key={TMDB_API_KEY}&language=fr-FR"
    )
    data = safe_get_json(url)
    return [g["name"] for g in data.get("genres", [])]


def get_movie_poster_url(movie: dict) -> str | None:
    return (
        f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
        if movie.get("poster_path") else None
    )


def get_movie_backdrop_url(movie: dict) -> str | None:
    return (
        f"https://image.tmdb.org/t/p/w780{movie['backdrop_path']}"
        if movie.get("backdrop_path") else None
    )


def auto_pick_movie(results: list[dict], title: str) -> dict | None:
    if len(results) == 1:
        return results[0]

    scored = [(m, score_movie(m, title)) for m in results]
    scored.sort(key=lambda x: x[1], reverse=True)

    best, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0

    if best_score >= 0.85 and (best_score - second_score) >= 0.20:
        return best

    if best_score >= 0.75 and best.get("vote_count", 0) >= 2000:
        return best

    return None


# ==================================================
# Fenêtre principale
# ==================================================

class MovieUpdaterWindow(ctk.CTk):

    def __init__(self, auto_mode=False):
        super().__init__()

        self.auto_mode = auto_mode
        self.geometry("1000x720")
        self.resizable(True, True)
        self.configure(bg="#181A20")

        self._build_ui()
        self.after(100, self.center_window)

        if auto_mode:
            self.after(300, self.run_update)

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 500
        y = (self.winfo_screenheight() // 2) - 360
        self.geometry(f"+{x}+{y}")

    # ================= UI =================

    def _build_ui(self):
        # ✅ CARTE RESPONSIVE
        self.main_card = ctk.CTkFrame(
            self,
            fg_color="#23242C",
            corner_radius=22
        )
        self.main_card.pack(
            fill="both",
            expand=True,
            padx=40,
            pady=40
        )
        self.main_card.pack_propagate(False)

        ctk.CTkLabel(
            self.main_card,
            text="🎬 Assistant Notion & TMDB",
            font=("Segoe UI Semibold", 26)
        ).pack(pady=(26, 8))

        ctk.CTkButton(
            self.main_card,
            text="🚀 Lancer la mise à jour",
            command=self.run_update,
            width=340,
            height=44,
            font=("Segoe UI Bold", 16)
        ).pack(pady=(0, 18))

        self.progress = ctk.CTkProgressBar(self.main_card)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=40, pady=(0, 16))

        # ✅ LOG BOX GRANDE & LISIBLE
        self.log_box = tk.Text(
            self.main_card,
            bg="#1B1C24",
            fg="#E7E8EA",
            relief="flat",
            padx=16,
            pady=12,
            wrap="word",
            font=("Segoe UI", 16),  # 👈 TAILLE DU TEXTE
            spacing1=4,  # espace avant paragraphe
            spacing3=4  # espace après paragraphe
        )

        self.log_box.pack(
            fill="both",
            expand=True,
            padx=24,
            pady=(0, 24)
        )
        self.log_box.config(state="disabled")

    # ================= LOGS =================

    def log(self, msg, level="info"):
        icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, f"{icons[level]} {msg}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")
        self.update()

    def ask_manual_url(self) -> str | None:
        dialog = ctk.CTkInputDialog(
            title="Film non trouvé",
            text="Collez l’URL TMDB ou IMDb du film :"
        )
        url = dialog.get_input()
        return url.strip() if url else None

    # ================= WORKFLOW =================

    def run_update(self):
        try:
            # --- Reset logs ---
            self.log_box.config(state="normal")
            self.log_box.delete(1.0, tk.END)
            self.log_box.config(state="disabled")

            pages = fetch_all_pages()
            pages_to_enrich = get_movies_to_enrich(pages)

            self.log(f"🎯 Films à enrichir : {len(pages_to_enrich)}")
            total = max(len(pages_to_enrich), 1)
            self.progress.set(0)

            for idx, page in enumerate(pages_to_enrich, start=1):
                title = get_title(page)
                if not title:
                    continue

                self.log(f"🔍 Recherche TMDB : {title}")

                results = search_movie(
                    clean_search_title(title),
                    extract_year(title)
                )

                movie = None
                force_url = False

                # ===============================
                # A — Recherche TMDB
                # ===============================
                if results:
                    results = sorted(
                        results,
                        key=lambda m: score_movie(m, title),
                        reverse=True
                    )[:10]

                    candidate = auto_pick_movie(results, title)

                    if (
                            candidate
                            and is_released_tmdb(candidate)
                            and title_matches(title, candidate.get("title", ""))
                    ):
                        movie = candidate
                        self.log("🎯 Auto-pick validé (titre + date OK)", "info")

                    else:
                        self.log(
                            "🛑 Auto-pick bloqué → choix manuel requis",
                            "info"
                        )

                    # ===============================
                    # B — Choix manuel
                    # ===============================
                    if not movie:
                        options = []

                        for m in results:
                            year = (m.get("release_date") or "")[:4] or "?"
                            rating = m.get("vote_average", 0)
                            votes = m.get("vote_count", 0)

                            overview = (m.get("overview") or "").strip()
                            if len(overview) > 240:
                                overview = overview[:237].rsplit(" ", 1)[0] + "…"

                            director = get_director(m["id"])

                            options.append(
                                f"{m.get('title')} ({year})\n"
                                f"🎬 {director or 'Réalisateur inconnu'}\n"
                                f"⭐ {rating}/10 · {votes} votes\n\n"
                                f"{overview}"
                            )

                        choice = ask_choice(options=options, parent=self)

                        if choice == -1:
                            self.log("🔗 Saisie manuelle via URL demandée", "info")
                            force_url = True

                        elif choice == 0:
                            self.log("⏭️ Ignoré", "info")
                            continue

                        else:
                            movie = results[choice - 1]

                # ===============================
                # C — FALLBACK URL
                # ===============================
                if not movie:
                    if not force_url:
                        self.log("❌ Aucun résultat valide → URL requise", "warn")

                    url = self.ask_manual_url()
                    if not url:
                        self.log("⏭️ Ignoré (pas d’URL)", "info")
                        continue

                    tmdb_id = extract_tmdb_id_from_url(url)
                    imdb_id = extract_imdb_id_from_url(url)

                    if tmdb_id:
                        self.log(f"🔗 Import TMDB ID : {tmdb_id}")
                        movie = get_movie_by_tmdb_id(tmdb_id)

                    elif imdb_id:
                        self.log(f"🔗 Import IMDb ID : {imdb_id}")
                        movie = get_tmdb_movie_from_imdb_id(imdb_id)

                    else:
                        self.log("❌ URL non reconnue", "error")
                        continue

                if not movie:
                    self.log("❌ Impossible de récupérer le film", "error")
                    continue

                # ===============================
                # D — ENRICHISSEMENT NOTION
                # ===============================
                release = None
                if movie.get("release_date"):
                    try:
                        release = datetime.strptime(
                            movie["release_date"], "%Y-%m-%d"
                        )
                    except ValueError:
                        pass

                genres = get_movie_genres(movie["id"])
                tags = compute_tags_from_categories(
                    genres,
                    release.year if release else None
                )

                update_movie_page(
                    page_id=page["id"],
                    title=movie["title"],
                    synopsis=movie.get("overview", ""),
                    genres=genres,
                    tags=tags,
                    director=get_director(movie["id"]),
                    release_date=release,
                    support="Cinéma"
                    if release and release > datetime.now()
                    else "À télécharger"
                )

                add_poster_and_backdrop(
                    page["id"],
                    get_movie_poster_url(movie),
                    get_movie_backdrop_url(movie)
                )

                self.progress.set(idx / total)
                self.log(f"✅ {title} enrichi", "success")

            # ===============================
            # E — CALENDRIER
            # ===============================
            self.log("📅 Synchronisation calendrier…")
            sync_future_releases(
                pages,
                get_title,
                get_release_date,
                log=self.log
            )

            self.progress.set(1)
            self.log("🎉 Mise à jour terminée", "success")

        except Exception as e:
            self.log(f"❌ Erreur : {e}", "error")

