# Bibliothèque : fix tri, suppression de film, correction d'image via TMDB

## Contexte

Trois demandes sur la page Bibliothèque :

1. **Bug** : le tri "Date d'ajout" (ajouté récemment) revient au tri par défaut ("Titre") dès qu'une action déclenche un rechargement (ex. enregistrer une note dans la fiche détail).
2. **Feature** : pouvoir supprimer un film de la bibliothèque.
3. **Feature** : pouvoir corriger l'affiche (et les métadonnées) d'un film quand TMDB a associé le mauvais résultat (ex. "Odyssée").

Plus deux améliorations UX ciblées identifiées en marge de ce travail.

## 1. Fix : persistance du tri/recherche/page

**Root cause** (confirmée par lecture du code, pas supposée) : `frontend/pages/library.py:59` recrée `state = {"query": "", "sort": SORT_OPTIONS[0], "page": 1}` en local à chaque appel de `render()`. Le bouton "Enregistrer" du dialogue de détail (`frontend/components.py:85-92`) appelle `ctx.reload()`, qui appelle `rerender()` (`frontend/ui.py:83-85`), qui appelle `render_section(active_section["key"])` (`frontend/ui.py:52`) → relance `library.render()` avec un `state` neuf. Le tri/recherche/page en cours sont donc perdus à chaque action qui recharge les données, pas seulement à la sauvegarde de note — aussi après suppression et correction TMDB (sections 2 et 3 ci-dessous).

**Fix** : ajouter un espace de stockable générique et persistant dans `AppState` (`frontend/context.py`), qui survit aux appels de `render_section()` car `state` (l'instance `AppState`) est créée une seule fois par session dans `main_page()` (`frontend/ui.py:39`) :

```python
# frontend/context.py
@dataclass
class AppState:
    ...
    ui_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
```

`library.render()` remplace son `state = {...}` local par :

```python
state = ctx.state.ui_state.setdefault("library", {"query": "", "sort": SORT_OPTIONS[0], "page": 1})
```

Générique et réutilisable par d'autres pages si besoin futur — pas de couplage entre `context.py` et les concepts propres à la bibliothèque.

## 2. Suppression d'un film

- `backend/core/store.py` : nouvelle méthode `delete(media_id)`, même pattern que `update()` :
  ```python
  def _delete_sync(self, media_id: str) -> bool:
      with sqlite3.connect(self.db_path) as conn:
          cursor = conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
          return cursor.rowcount > 0

  async def delete(self, media_id: str) -> bool:
      return await asyncio.to_thread(self._delete_sync, media_id)
  ```
- `frontend/components.py`, dans `open_media_detail_dialog` : bouton **"Supprimer"** (style outline/rouge, ex. `bs-outline-btn` avec une couleur d'alerte) à côté de "Fermer"/"Enregistrer".
- Au clic : ouvre un second `ui.dialog()` de confirmation : *"Supprimer définitivement « {titre} » ? Cette action est irréversible."* + boutons **Annuler** / **Confirmer la suppression**.
- Confirmer → `await ctx.store.delete(media.id)`, `ui.notify(f"« {titre} » supprimé.", type="positive")`, ferme les deux dialogues, `await ctx.reload()`.

## 3. Corriger l'image/métadonnées via TMDB

Le wizard (`frontend/pages/wizard.py`) a déjà l'outillage de recherche TMDB (`ctx.processor.search_candidates`) et d'application (`ctx.processor.enrich_media_with_tmdb_id`), mais ce dernier ne remplit que les champs **vides** (`backend/core/processor.py:266-315`, `_prepare_updates`) — il ne remplacerait pas une affiche/réalisateur/synopsis déjà en base, ce qui est justement le problème à corriger.

**Fix** : ajouter un paramètre `force: bool = False` à `_prepare_updates` et `enrich_media_with_tmdb_id` dans `backend/core/processor.py`. Quand `force=True`, chaque champ TMDB (réalisateur, synopsis, genres/tags, date de sortie, affiche) écrase la valeur existante au lieu de ne combler que les champs vides. Le wizard continue d'appeler sans `force` → comportement inchangé pour le flux d'enrichissement automatique/ambigu existant.

```python
# backend/core/processor.py
def _prepare_updates(self, media, tmdb_data, force: bool = False):
    ...
    if (not media.director or force) and tmdb_data:
        director = self.tmdb.get_director(tmdb_data)
        if director:
            updates["director"] = director
    # même schéma pour synopsis, categories, tags
    ...

async def enrich_media_with_tmdb_id(self, media_id, tmdb_id, force: bool = False):
    ...
    updates, poster_url = self._prepare_updates(media, tmdb_details, force=force)
    cover_todo = poster_url if (not media.cover_url or force) else None
    ...
```

**UI** (`frontend/components.py`, dans `open_media_detail_dialog`) : bouton **"Corriger via TMDB"** → ouvre un dialogue avec :
- un champ de recherche pré-rempli avec `media.title` + bouton "Rechercher"
- un spinner pendant l'appel réseau (`await ctx.processor.search_candidates(...)`)
- la liste des résultats (vignette `media_poster` + titre + année), cliquables — version simplifiée par rapport à la galerie du wizard (pas d'aperçu détaillé synopsis/tags/IMDb), car c'est une correction rapide et non une classification initiale

Clic sur un résultat → `await ctx.processor.enrich_media_with_tmdb_id(media.id, tmdb_id, force=True)` (la méthode déduit déjà `is_series` depuis `media.type` en interne, pas besoin de le repasser), `ui.notify(..., type="positive")`, ferme les deux dialogues, `await ctx.reload()`.

## 4. Améliorations UX incluses

- **Debounce sur la recherche bibliothèque** (`frontend/pages/library.py`, `_on_search`) : actuellement chaque frappe relance immédiatement filtre + tri + rendu de toute la grille. Ajout d'un debounce ~300ms (timer NiceGUI annulé/relancé à chaque frappe, pas de helper existant dans le repo pour ça).
- **Spinner pendant la recherche TMDB** dans le nouveau dialogue de correction (section 3), le temps de l'appel réseau.

## Fichiers concernés

- `frontend/context.py` — ajout `ui_state` à `AppState`
- `frontend/pages/library.py` — état persistant + debounce recherche
- `backend/core/store.py` — méthode `delete()`
- `backend/core/processor.py` — paramètre `force` sur `_prepare_updates` / `enrich_media_with_tmdb_id`
- `frontend/components.py` — boutons Supprimer/Corriger via TMDB + dialogues associés dans `open_media_detail_dialog`
- `tests/test_library.py` — tests de persistance d'état (ou nouveau test ciblé)
- nouveaux tests pour `store.delete()` et `processor._prepare_updates(..., force=True)`

## Vérification

- Tests unitaires : sort persistence (simuler deux appels successifs à `render()`-équivalent avec le même `AppState`), `store.delete()` (créer puis supprimer puis vérifier `fetch_one` retourne `None`), `_prepare_updates(force=True)` écrase des champs déjà remplis.
- Test manuel dans l'app : trier par "Date d'ajout" → noter un film → vérifier que le tri reste sur "Date d'ajout" après le reload. Supprimer un film → vérifier qu'il disparaît de la liste et de la base. Corriger l'image d'un film mal associé → vérifier que la nouvelle affiche et les métadonnées s'affichent.
