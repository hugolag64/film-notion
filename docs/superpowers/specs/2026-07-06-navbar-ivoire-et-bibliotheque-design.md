# Navbar ivoire + page Bibliothèque — Design

Date : 2026-07-06

## Contexte et motivation

Depuis la refonte graphique du 2026-07-05 (`2026-07-05-refonte-graphique-backstage-design.md`), le bandeau de navigation (`bs-topbar`) utilise un fond quasi noir (`var(--text)`, `#2b2420`). En usage réel, ce bandeau est jugé terne et devient illisible ("bandeau noir où on voit rien") notamment quand une fenêtre modale (ex. "Ajouter un film") s'ouvre par-dessus et l'assombrit encore via l'overlay de la dialog.

Par ailleurs, il n'existe aucun moyen de parcourir l'ensemble de la vidéothèque : le dashboard ("À traiter") n'affiche que les fiches incomplètes (`AppState.medias`, filtré par `_compute_todo`), jamais la collection complète (`AppState.all_medias`, déjà chargée en mémoire mais jamais rendue telle quelle).

Deux changements validés par mockups (comparaison visuelle A/B/C pour la nav, A/B pour la bibliothèque) :
1. Remplacer le bandeau sombre par un bandeau ivoire, cohérent avec le reste de l'app.
2. Ajouter un onglet "Bibliothèque" listant tous les films/séries, avec recherche et tri.

## Navbar ivoire

Dans `frontend/theme.py` :
- `.bs-topbar` : `background: var(--surface)` (blanc) au lieu de `var(--text)`, avec `border-bottom: 1px solid var(--border)` pour le détacher du contenu (remplace l'effet de bloc plein).
- `.bs-navlink` : couleur `var(--text-muted)` par défaut (au lieu de `var(--bg)` à opacité 0.75) ; `.bs-navlink.active` passe en `var(--accent)` (bordeaux), toujours souligné en `var(--accent-gold)`.
- Le logo "🎬 Backstage" (`bs-title`) reste en `var(--text)`, déjà lisible sur fond clair sans changement.

Aucun changement de structure dans `ui.py` : seule l'apparence CSS change, la logique de rendu des onglets (actif/inactif, disable pendant le wizard) reste identique.

## Page "Bibliothèque"

- Nouvelle entrée dans `SECTIONS` (`ui.py`) : `("library", "Bibliothèque")`, positionnée entre "À traiter" et "Statistiques".
- Nouveau module `frontend/pages/library.py`, ajouté à `PAGE_RENDERERS`.
- Source de données : `ctx.state.all_medias` (déjà peuplé par `reload()` dans `ui.py`, aucun nouvel appel au `MediaStore` nécessaire). Contrairement au dashboard, aucun filtrage "à traiter" n'est appliqué : tous les médias sont affichés.
- Contrôles en haut de page :
  - Champ de recherche (`ui.input`) filtrant par sous-chaîne insensible à la casse sur `title`, appliqué côté client à chaque frappe.
  - Sélecteur de tri (`ui.select`) : Titre (A→Z), Année (récent→ancien), Note (décroissante). Absence de valeur (année/note manquante) trié en dernier.
- Grille de résultats : la carte poster+titre+badge année/type (`dashboard._media_card`) est déplacée vers `frontend/components.py` sous le nom `media_card`, et importée par `dashboard.py` et `library.py`, pour éviter toute duplication.
- État vide : si aucun média ne correspond à la recherche, message centré "Aucun résultat." (même style que l'état vide du dashboard).

### Hors scope

- Pas de filtres facettés (type, support, catégorie) — uniquement recherche + tri, conformément au choix "sobre" validé.
- Pas de clic pour ouvrir une fiche détail/édition depuis la bibliothèque (simple consultation).
- Aucune modification du backend (`backend/core/*`, `MediaStore`) : `all_medias` est déjà chargé en mémoire côté frontend.
- Pas de pagination : la collection actuelle est petite, un rendu complet de la grille suffit.
- Aucun changement du contenu propre au wizard (`wizard.py`) — seul le bandeau partagé change d'apparence.
