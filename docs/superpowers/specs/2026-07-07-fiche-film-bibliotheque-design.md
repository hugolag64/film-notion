# Fiche film enrichie (note, avis, réalisateur, synopsis) — Design

Date : 2026-07-07

## Contexte et motivation

Depuis l'ajout de la page Bibliothèque (`2026-07-06-navbar-ivoire-et-bibliotheque-design.md`), la grille affiche uniquement poster, titre, année et type via `media_card` (`frontend/components.py`). Le modèle `Media` (`backend/core/models.py`) contient pourtant déjà `director`, `synopsis`, `categories`, `rating` (note libre, ex. `"8/10"`) et `review` (avis personnel), tous capturés par le dialog "Ajouter un film" (`dashboard.py`) mais jamais affichés ni modifiables ensuite. `MediaStore.update()` existe côté backend mais n'est appelé par aucun code frontend.

Objectif : rendre visibles réalisateur, synopsis, genre, note et avis pour chaque film, et permettre de noter/commenter un film après coup sans passer par la base de données directement.

## Carte compacte (Dashboard + Bibliothèque)

`media_card` (`frontend/components.py`) s'enrichit de deux badges optionnels, ajoutés sous le badge année/type existant :
- **Note** : `⭐ {rating}` si `media.rating` est renseigné (badge absent sinon).
- **Genre** : première valeur de `media.categories` si la liste est non vide (badge absent sinon).

La carte devient cliquable sur les deux pages (Dashboard et Bibliothèque) : `media_card` gagne un paramètre `on_click` optionnel (callback sans argument), branché par l'appelant sur `open_media_detail_dialog(media, ctx)`. Le style `.bs-card:hover` existant suffit pour l'affordance visuelle ; ajout de `cursor: pointer` uniquement quand `on_click` est fourni.

## Fiche détaillée (dialog)

Nouvelle fonction `open_media_detail_dialog(media, ctx)` dans `frontend/components.py`, à côté de `media_card` :

- En-tête : poster (plus grand, `height="220px"`), titre, badge année/type.
- Bloc lecture seule : Réalisateur (`director`, `"—"` si vide), Genre/Catégories (`categories` affichées en chips, `"—"` si vide liste), Synopsis (`synopsis`, `"—"` si vide).
- Bloc édition :
  - `ui.input("Note /10")` pré-rempli avec `media.rating or ""` — même format texte libre que le dialog d'ajout, aucune validation de format côté client (cohérent avec l'existant).
  - `ui.textarea("Avis")` pré-rempli avec `media.review or ""`.
- Boutons : "Enregistrer" → `await ctx.store.update(media.id, {"rating": rating_input.value, "review": review_input.value})`, puis `await ctx.reload()`, `ui.notify("Film mis à jour", type="positive")`, fermeture du dialog ; "Fermer" (annule, aucune écriture).

## Hors scope

- Seuls `rating` et `review` sont éditables dans cette fiche — titre, réalisateur, type, statut, support, catégories, synopsis, tags, cover_url restent en lecture seule (pas de formulaire d'édition complet).
- Aucun changement de schéma DB : tous les champs utilisés existent déjà dans `Media`/`store.py`.
- Pas de validation de format pour la note (ex. forcer un nombre entre 0 et 10) — reste un champ texte libre comme dans le dialog d'ajout actuel.
- Le badge "genre" sur la carte compacte n'affiche que la première catégorie, pas la liste complète (place limitée sur la carte).
- Aucune suppression de film depuis cette fiche.
