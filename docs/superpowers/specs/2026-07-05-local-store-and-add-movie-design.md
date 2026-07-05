# Remplacement de Notion par une base locale + ajout manuel de films

## Contexte

Backstage utilise aujourd'hui Notion comme unique source de vérité pour la
vidéothèque (247 films actuellement). `NotionService` (backend/core/notion.py)
lit/écrit via l'API REST Notion, et `EnrichmentProcessor` (backend/core/processor.py)
construit directement des payloads au format propriété Notion
(ex. `{"select": {"name": "..."}}`) pour les mises à jour. Cette forme de
payload est aussi décodée telle quelle par `backend/core/diff.py` pour
l'aperçu dry-run.

Objectif : remplacer complètement Notion par une base SQLite locale
(mêmes informations, mêmes flux d'enrichissement TMDB/OMDb), avec import des
247 films existants, et ajouter la possibilité de créer une fiche film
directement depuis l'interface.

## Décisions actées

- Remplacement total de Notion (pas de bascule config) — Notion ne reste
  utilisé que par un script de migration one-shot.
- Migration : les 247 films existants sont importés dans la base locale, en
  conservant leurs IDs Notion d'origine comme clé primaire locale (pour que
  `cache.json`, indexé par `media.id`, reste valide et qu'aucun film déjà
  traité ne soit reproposé à l'enrichissement après la bascule).
- Stockage : SQLite (fichier unique, `sqlite3` stdlib, pas de nouvelle
  dépendance).
- Formulaire d'ajout manuel : tous les champs du modèle `Media` (pas
  seulement le titre).

## Composants modifiés

### 1. `backend/core/store.py` (nouveau) — `MediaStore`

Table SQLite `media` miroir du modèle `Media` :

| colonne | type | notes |
|---|---|---|
| id | TEXT PK | uuid4 (ou id Notion importé) |
| title | TEXT NOT NULL | |
| type | TEXT | Film / Série |
| status | TEXT | |
| support | TEXT | |
| rating | TEXT | |
| release_date | TEXT | ISO `YYYY-MM-DD` |
| director | TEXT | |
| categories | TEXT | JSON list |
| synopsis | TEXT | |
| tags | TEXT | JSON list |
| review | TEXT | |
| tmdb_ok | INTEGER | 0/1 |
| cover_url | TEXT | |

Méthodes (toutes `async`, exécution DB via `asyncio.to_thread` pour ne pas
bloquer la boucle événementielle) :

- `init_schema()` — `CREATE TABLE IF NOT EXISTS`, appelé une fois au démarrage.
- `fetch_all() -> List[Media]`
- `fetch_one(media_id: str) -> Optional[Media]`
- `create(fields: Dict[str, Any]) -> Media` — utilise `fields["id"]` s'il est
  fourni (migration, pour conserver l'id Notion d'origine), sinon génère un
  nouvel `id` (uuid4) ; insère, retourne le `Media` créé.
- `update(media_id: str, fields: Dict[str, Any]) -> bool` — met à jour
  uniquement les colonnes présentes dans `fields`.

Une connexion sqlite3 courte (`with sqlite3.connect(path) as conn:`) est
ouverte par appel — volume et fréquence trop faibles pour justifier un pool
ou `aiosqlite`.

### 2. `backend/core/models.py`

Suppression des alias pydantic Notion (`alias="Nom"`, etc.) — non utilisés
par le mapping Notion existant (qui construit `Media` par nom d'attribut
Python) et trompeurs une fois Notion retiré du flux principal. Le champ `id`
n'est plus documenté comme "Notion Page ID" mais comme identifiant local.

### 3. `backend/core/processor.py`

- `self.notion: NotionService` → `self.store: MediaStore` (injecté au
  constructeur : `EnrichmentProcessor(store: MediaStore)`).
- `_prepare_updates` retourne désormais un dict de valeurs Python simples
  (ex. `{"director": "...", "categories": [...], "tmdb_ok": True}`) au lieu
  du format propriété Notion.
- `_update_notion` devient `_apply_updates(media_id, updates, cover_url)` :
  fusionne `cover_url` dans `updates` si présent, appelle
  `self.store.update(media_id, updates)`. L'étape Notion-only
  "append_image_block" (bloc image dans le corps de la page) disparaît :
  `cover_url` est une simple colonne déjà affichée via `media_poster`.
- `enrich_media_with_tmdb_id` / `_mark_processed_after_update` / `process_all`
  utilisent `self.store.fetch_one` / `self.store.fetch_all` à la place des
  méthodes `NotionService` équivalentes.

### 4. `backend/core/mapping.py`

Suppression de `Props`, `REQUIRED_PROPERTIES`, `validate_schema` (spécifiques
au schéma Notion, sans objet après la bascule). Ajout de `FIELD_LABELS: Dict[str, str]`
(nom de champ Python → libellé français affiché dans l'aperçu dry-run),
indépendant de toute notion de schéma. Conservés tels quels : `Values`,
`SERIES_TYPES` / `is_series`, `GENRE_TAG_RULES`.

### 5. `backend/core/diff.py`

`summarize_changes` travaille sur les valeurs Python simples produites par
`_prepare_updates` (plus le format `{"select": {...}}` Notion). Formatage par
type : liste → jointe par virgules, bool → "Oui"/"Non", date → `str(date)`,
sinon `str(valeur)`. Libellés de champ via `FIELD_LABELS`.

### 6. `backend/core/notion.py`

Conservé tel quel, mais n'est plus utilisé que par le script de migration
one-shot — plus importé par l'application en cours d'exécution. La méthode
`validate_schema_sync` est supprimée (dépendait de `validate_schema`,
supprimé de mapping.py).

### 7. `backend/config.py` / `main.py`

- `Config` : ajout de `DB_PATH = os.getenv("DB_PATH", "backstage.db")`.
  `NOTION_TOKEN` / `DATABASE_ID` restent lisibles (utilisés par le script de
  migration) mais ne sont plus requis par l'application.
- Suppression de `Config.check()` (son seul rôle était de vérifier
  `NOTION_TOKEN` / `DATABASE_ID`, devenus non-obligatoires) et de son appel
  dans `main.py`.
- `main.py` : suppression de la validation de schéma Notion au démarrage ;
  ajout de `MediaStore(Config.DB_PATH).init_schema()`.

### 8. `backend/core/scheduler.py`

`processor.notion.fetch_all_media()` → `processor.store.fetch_all()`.

### 9. Script de migration `scripts/migrate_from_notion.py` (nouveau)

Script one-shot exécuté manuellement une fois :

```
medias = await NotionService.fetch_all_media()
store = MediaStore(Config.DB_PATH)
store.init_schema()
for m in medias:
    await store.create(m.model_dump())   # fields inclut "id" -> conserve l'id Notion d'origine
```

`MediaStore.create` utilise l'`id` fourni dans `fields` s'il est présent (cas
de la migration), sinon en génère un nouveau (cas de l'ajout manuel depuis
l'interface).

Affiche un résumé (`Migré N films.`) en fin d'exécution.

### 10. Frontend

- `frontend/context.py` : `AppContext` gagne un champ `store: MediaStore`.
- `frontend/ui.py` : `main_page` instancie `store = MediaStore(Config.DB_PATH)`,
  passe `store` au constructeur d'`EnrichmentProcessor` et à `AppContext`.
  `reload()` appelle `store.fetch_all()` au lieu de `NotionService.fetch_all_media()`.
- `frontend/pages/dashboard.py` : nouveau bouton **"Ajouter un film"** à côté
  de "Lancer l'enrichissement" / "Prévisualiser". Ouvre un dialogue avec :
  titre (requis), type (select Film/Série), statut, support, note,
  date de sortie, réalisateur, catégories, synopsis, tags, avis, URL affiche
  (avec aperçu live via le composant `media_poster` existant). À la
  soumission : `await ctx.store.create(fields)` puis `await ctx.reload()`.
  Les champs manquants font naturellement réapparaître la fiche dans la
  liste "à traiter" pour un passage TMDB classique.

## Tests

`tests/test_mapping.py` et `tests/test_diff.py` sont réécrits pour les
nouvelles formes de valeurs simples (ils testent actuellement le format
payload Notion qui disparaît).

## Hors périmètre

- Suppression de film depuis l'interface (non demandé).
- Bascule configurable Notion/local (remplacement total décidé).
- Édition des champs d'une fiche existante depuis l'interface (hors demande
  initiale — seul l'ajout est demandé).
