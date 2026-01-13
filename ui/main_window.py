import customtkinter as ctk
import tkinter as tk
from datetime import datetime

# === CORE ===
from core.notion import (
    fetch_all_pages,
    get_movies_to_enrich,
    get_movies_without_tags,
    get_title,
    get_release_date,
    update_movie_page,
    add_poster_and_backdrop,
    compute_tags_from_categories,
)
from core.calendar import sync_future_releases
from core.tmdb import search_movie, score_movie

# === UI ===
from ui.chooser import ask_choice

# === UTILS ===
from utils.text import clean_search_title, extract_year
from utils.request import safe_get_json
from config import TMDB_API_KEY, notion


# ==================================================
# Helpers TMDB
# ==================================================

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
    """
    Sélection automatique si la correspondance est évidente
    """

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
        self.geometry("880x640")
        self.resizable(False, False)
        self.configure(bg="#181A20")

        self._build_ui()
        self.after(100, self.center_window)

        if auto_mode:
            self.after(300, self.run_update)

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 440
        y = (self.winfo_screenheight() // 2) - 320
        self.geometry(f"+{x}+{y}")

    # ==================================================
    # UI
    # ==================================================

    def _build_ui(self):
        self.main_card = ctk.CTkFrame(
            self,
            width=740,
            height=520,
            fg_color="#23242C",
            corner_radius=22
        )
        self.main_card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self.main_card,
            text="🎬 Assistant Notion & TMDB",
            font=("Segoe UI Semibold", 25)
        ).pack(pady=(22, 6))

        ctk.CTkButton(
            self.main_card,
            text="🚀 Lancer la mise à jour",
            command=self.run_update,
            width=320,
            height=42,
            font=("Segoe UI Bold", 16)
        ).pack(pady=(0, 16))

        self.progress = ctk.CTkProgressBar(self.main_card, width=440)
        self.progress.set(0)
        self.progress.pack(pady=(0, 14))

        self.log_box = tk.Text(
            self.main_card,
            height=34,
            width=92,
            bg="#1B1C24",
            fg="#E7E8EA",
            relief="flat",
            padx=16,
            pady=12
        )
        self.log_box.pack(padx=18)
        self.log_box.config(state="disabled")

    # ==================================================
    # Logs
    # ==================================================

    def log(self, msg, level="info"):
        icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, f"{icons[level]} {msg}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")
        self.update()

    # ==================================================
    # WORKFLOW
    # ==================================================

    def run_update(self):
        try:
            # --- Reset logs ---
            self.log_box.config(state="normal")
            self.log_box.delete(1.0, tk.END)
            self.log_box.config(state="disabled")

            pages = fetch_all_pages()

            # ===============================
            # A — ENRICHISSEMENT NORMAL
            # ===============================

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
                if not results:
                    self.log("⚠️ Aucun résultat TMDB", "warn")
                    continue

                results = sorted(
                    results,
                    key=lambda m: score_movie(m, title),
                    reverse=True
                )[:10]

                movie = auto_pick_movie(results, title)

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

                        txt = (
                            f"{m.get('title')} ({year})\n"
                            f"🎬 {director or 'Réalisateur inconnu'}\n"
                            f"⭐ {rating}/10 · {votes} votes\n\n"
                            f"{overview}"
                        )
                        options.append(txt)

                    choice = ask_choice(options=options, parent=self)
                    if choice <= 0:
                        self.log("⏭️ Ignoré", "info")
                        continue

                    movie = results[choice - 1]

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
            # B — 🏷️ RESYNC TAGS SAFE (NON DESTRUCTIF)
            # ===============================

            self.log("🏷️ Resync tags (safe)…")

            for page in pages:
                title = get_title(page)
                if not title:
                    continue

                # 🔒 Si tags déjà présents → on ne touche PAS
                tags_prop = (
                    page["properties"]
                    .get("Tags", {})
                    .get("multi_select", [])
                )
                if tags_prop:
                    continue

                categories = [
                    g["name"]
                    for g in page["properties"]
                    .get("Catégorie", {})
                    .get("multi_select", [])
                ]
                if not categories:
                    continue

                release = get_release_date(page)
                tags = compute_tags_from_categories(
                    categories,
                    release.year if release else None
                )
                if not tags:
                    continue

                notion.pages.update(
                    page_id=page["id"],
                    properties={
                        "Tags": {
                            "multi_select": [{"name": t} for t in tags]
                        }
                    }
                )

                self.log(f"🏷️ Tags ajoutés : {title}", "success")

            # ===============================
            # C — CALENDRIER
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

