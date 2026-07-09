# Filtres dans la bibliothèque

## Contexte

La bibliothèque (`frontend/pages/library.py`) permet déjà de rechercher par titre et de trier (Titre, Année, Note, Date d'ajout), avec état persistant dans `ctx.state.ui_state["library"]`. Il n'existe aucun moyen de restreindre la liste par genre, statut de visionnage ou support. Avec 248 films en base et des données riches (genres TMDB, statut "À regarder"/"Terminé"/"À revoir", support "Cinéma"/"NAS"/"À télécharger"), l'utilisateur veut pouvoir filtrer pour retrouver plus vite un sous-ensemble de sa collection.

Le champ `type` du modèle `Media` (Film/Série) n'est pas retenu comme dimension de filtre : toutes les entrées actuelles valent "Film", ce filtre serait donc inutile pour l'instant.

## Fonctionnalité

Un bouton **"Filtrer"** (icône `filter_list`) est ajouté dans la barre existante, à côté du select de tri. Il affiche un badge numérique indiquant le nombre de filtres actifs (somme des valeurs sélectionnées sur les 3 dimensions). Au clic, il ouvre un `ui.menu` contenant :

- **Genre** — `ui.select` multi-sélection, options = toutes les valeurs distinctes de `categories` présentes dans `ctx.state.all_medias`, triées alphabétiquement.
- **Statut** — `ui.select` multi-sélection, options = valeurs distinctes de `status` présentes dans les données, triées alphabétiquement.
- **Support** — `ui.select` multi-sélection, options = valeurs distinctes de `support` présentes dans les données, triées alphabétiquement.
- Bouton **"Réinitialiser"** qui vide les 3 sélections.

Les options sont dérivées dynamiquement des données (pas de liste statique codée en dur), pour rester correctes si de nouvelles valeurs de statut/support/genre apparaissent plus tard.

### Logique de filtrage

- Recherche par titre (substring, insensible à la casse) : inchangée.
- Pour chaque dimension (genre, statut, support) : si aucune valeur n'est sélectionnée, la dimension ne filtre rien. Si une ou plusieurs valeurs sont sélectionnées, un média passe si **au moins une** valeur sélectionnée correspond (logique OU intra-dimension). Pour le genre, un média passe si au moins un de ses `categories` est dans les genres sélectionnés.
- Entre les dimensions (recherche, genre, statut, support), la logique est **ET** : un média doit satisfaire toutes les dimensions actives pour apparaître dans le résultat.
- Le tri s'applique après filtrage, comme aujourd'hui.

### État et persistance

`get_library_state` initialise désormais :
```python
{"query": "", "sort": SORT_OPTIONS[0], "page": 1, "filters": {"genres": [], "statuses": [], "supports": []}}
```
Stocké dans `ctx.state.ui_state["library"]`, donc persistant entre les re-rendus de la page (même mécanisme que `query`/`sort`/`page`).

Changer un filtre réinitialise `page` à 1 (même comportement que changer la recherche ou le tri).

## Composants techniques

- `frontend/pages/library.py` :
  - `get_library_state` : ajout de la clé `filters` par défaut.
  - Nouvelle fonction `apply_filters(medias, filters) -> List[Media]` (pure, testable) qui applique la logique OU/ET décrite ci-dessus.
  - `filter_and_sort_medias` appelle `apply_filters` après le filtre de recherche texte et avant le tri (ou `render()` compose les deux appels — détail laissé à l'implémentation, du moment que le comportement combiné est testé).
  - Nouvelle fonction utilitaire pour dériver les options distinctes (genre/statut/support) à partir de `ctx.state.all_medias`, triées alphabétiquement.
  - UI : bouton "Filtrer" + `ui.menu` avec 3 `ui.select` multi-sélection et bouton de réinitialisation, câblés à `state["filters"]` et déclenchant `_refresh()`.
- `tests/test_library.py` : tests pour `apply_filters` (OU intra-dimension, ET inter-dimension, combinaison avec la recherche texte) et pour la valeur par défaut de `get_library_state`.

## Hors périmètre

- Filtre par type (Film/Série) — pas de valeur actuelle à filtrer.
- Sauvegarde des filtres favoris ou partage d'URL avec filtres encodés.
- Filtres sur la note (déjà couvert par le tri "Note").
