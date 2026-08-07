# Note utilisateurs TMDB dans la fiche film Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher la note moyenne des utilisateurs TMDB sur 10 à côté de la note personnelle dans la fiche film.

**Architecture:** Ajouter une route backend dédiée `GET /api/medias/{media_id}/tmdb-rating` qui utilise l’association TMDB existante sans modifier la base de données. Le frontend chargera cette note uniquement pour le film sélectionné et l’affichera dans le bloc de notation existant, avec des états de chargement et d’indisponibilité indépendants du reste de la fiche.

**Tech Stack:** FastAPI, Pydantic, SQLite existant, client TMDB Python, React 19, Vite, Tailwind CSS, pytest, oxlint.

## Global Constraints

- Afficher séparément la note personnelle sur 5 et la note TMDB sur 10.
- Ne pas ajouter Rotten Tomatoes ni de nouvelle dépendance graphique.
- Ne pas modifier le schéma SQLite ni persister la note TMDB.
- Ne charger une note TMDB que pour le film actuellement sélectionné.
- Une erreur TMDB ne doit pas fermer la fiche ni désactiver ses autres actions.
- Conserver les changements déjà présents dans le dépôt et ne committer que les fichiers de cette fonctionnalité.

---

## Cartographie des fichiers

- `backend/api.py` : route authentifiée qui vérifie le média, interroge TMDB et renvoie `{rating: float | null}`.
- `tests/test_api.py` : tests unitaires de la route avec un faux store et un faux client TMDB.
- `proto-ui/src/api.js` : fonction HTTP `fetchTMDBRating(mediaId)`.
- `proto-ui/src/BackstagePrototype.jsx` : état de chargement de la note et rendu du second indicateur dans le bloc `VOTRE NOTE`.

## Task 1: Ajouter la route backend de note TMDB

**Files:**
- Modify: `tests/test_api.py`
- Modify: `backend/api.py` autour des routes `/medias/{media_id}`

**Interfaces:**
- Consumes: `MediaStore.fetch_one(media_id)`, `TMDBClient.get_movie_details(tmdb_id)` et `Media.tmdb_id`.
- Produces: `async def get_tmdb_rating(media_id: str, store: MediaStore) -> dict[str, float | None]`, exposée par `GET /api/medias/{media_id}/tmdb-rating`.

- [ ] **Step 1: Écrire tous les tests rouges de la route**

Ajouter dans `tests/test_api.py` un faux store minimal et les quatre tests suivants. Importer `backend.api as api` dans le fichier si nécessaire ; le faux store peut réutiliser `FakeStore` existant.

```python
def test_tmdb_rating_is_null_when_media_has_no_tmdb_id(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=None)

    class UnexpectedTMDB:
        def __init__(self):
            raise AssertionError("TMDB ne doit pas être appelé sans tmdb_id")

    monkeypatch.setattr(api, "TMDBClient", UnexpectedTMDB)

    result = asyncio.run(api.get_tmdb_rating("1", store))

    assert result == {"rating": None}


def test_tmdb_rating_returns_vote_average(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            assert tmdb_id == 693134
            return {"vote_average": 8.24}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    result = asyncio.run(api.get_tmdb_rating("1", store))

    assert result == {"rating": 8.24}


def test_tmdb_rating_is_null_when_tmdb_has_no_vote_average(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            return {"vote_average": None}

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    assert asyncio.run(api.get_tmdb_rating("1", store)) == {"rating": None}


def test_tmdb_rating_is_null_when_tmdb_request_fails(monkeypatch):
    store = FakeStore()
    store.media = Media(id="1", title="Dune", type="Film", tmdb_id=693134)

    class FakeTMDB:
        async def get_movie_details(self, tmdb_id):
            raise RuntimeError("TMDB indisponible")

    monkeypatch.setattr(api, "TMDBClient", FakeTMDB)

    assert asyncio.run(api.get_tmdb_rating("1", store)) == {"rating": None}
```

- [ ] **Step 2: Ajouter le test de média introuvable**

Ajouter `import pytest` et `from fastapi import HTTPException` aux imports de `tests/test_api.py`, puis ajouter :

```python
def test_tmdb_rating_returns_404_for_unknown_media():
    class MissingStore:
        async def fetch_one(self, media_id):
            return None

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.get_tmdb_rating("missing", MissingStore()))

    assert error.value.status_code == 404
```

- [ ] **Step 3: Exécuter tous les tests et vérifier l’échec attendu**

Run: `pytest tests/test_api.py -k tmdb_rating -v`

Expected: FAIL parce que `get_tmdb_rating` n’existe pas encore, sans erreur de syntaxe dans les tests.

- [ ] **Step 4: Implémenter la route**

Dans `backend/api.py`, ajouter après `get_media` :

```python
@router.get("/medias/{media_id}/tmdb-rating")
async def get_tmdb_rating(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    if not media.tmdb_id:
        return {"rating": None}
    try:
        details = await TMDBClient().get_movie_details(media.tmdb_id)
    except Exception as error:
        logger.warning("Note TMDB indisponible pour le média %s : %s", media_id, error)
        return {"rating": None}
    raw_rating = details.get("vote_average") if details else None
    try:
        rating = float(raw_rating) if raw_rating is not None else None
    except (TypeError, ValueError):
        rating = None
    return {"rating": rating}
```

Réutiliser le logger déjà importé par `backend.api` et ne pas exposer les détails d’une exception TMDB au client.

- [ ] **Step 5: Exécuter les tests et vérifier le passage**

Run: `pytest tests/test_api.py -k tmdb_rating -v`

Expected: all five `tmdb_rating` tests PASS.

- [ ] **Step 6: Exécuter la suite API complète**

Run: `pytest tests/test_api.py -v`

Expected: all tests in `tests/test_api.py` PASS without warnings introduced by the new route.

- [ ] **Step 7: Committer la route backend et ses tests**

```bash
git add backend/api.py tests/test_api.py
git commit -m "feat(api): expose TMDB user rating for media"
```

## Task 2: Exposer la note dans le client API et la fiche film

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx` autour de `selectedMovie` et du bloc `VOTRE NOTE`

**Interfaces:**
- Consumes: `GET /api/medias/{media_id}/tmdb-rating` de Task 1.
- Produces: `fetchTMDBRating(mediaId): Promise<{rating: number | null}>` et un indicateur visuel dans la fiche sélectionnée.

- [ ] **Step 1: Ajouter le client HTTP**

Dans `proto-ui/src/api.js`, ajouter :

```javascript
export async function fetchTMDBRating(mediaId) {
    const response = await fetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/tmdb-rating`);
    if (!response.ok) throw new Error(`Failed to fetch TMDB rating: ${response.statusText}`);
    return response.json();
}
```

- [ ] **Step 2: Ajouter l’import et l’état local de la fiche**

Dans `proto-ui/src/BackstagePrototype.jsx`, importer `fetchTMDBRating` avec les autres fonctions API et ajouter près de `selectedMovie` :

```javascript
const [tmdbRating, setTMDBRating] = useState({mediaId: null, loading: false, rating: null});
```

Ajouter un `useEffect` dépendant uniquement de `selectedMovie?.id` pour éviter de relancer la requête quand la note personnelle met à jour l’objet film :

```javascript
useEffect(() => {
    if (!selectedMovie) {
        setTMDBRating({mediaId: null, loading: false, rating: null});
        return undefined;
    }

    let cancelled = false;
    const mediaId = selectedMovie.id;
    setTMDBRating({mediaId, loading: true, rating: null});
    fetchTMDBRating(mediaId)
        .then(({rating}) => {
            if (!cancelled) setTMDBRating({mediaId, loading: false, rating});
        })
        .catch(() => {
            if (!cancelled) setTMDBRating({mediaId, loading: false, rating: null});
        });

    return () => { cancelled = true; };
}, [selectedMovie?.id]);
```

Le garde `mediaId` sera utilisé au rendu afin qu’une réponse lente d’une ancienne fiche ne soit jamais affichée sur la nouvelle.

- [ ] **Step 3: Lancer le lint frontend avant le rendu**

Run: `npm run lint` from `proto-ui`

Expected: PASS; corriger uniquement les erreurs liées à l’import, à l’effet ou à l’état ajoutés.

- [ ] **Step 4: Ajouter l’indicateur TMDB dans le bloc de notation**

Remplacer le conteneur horizontal actuel du bloc `VOTRE NOTE` par un conteneur `flex flex-wrap` qui conserve exactement les étoiles et les actions de ta note, puis ajouter après celles-ci :

```jsx
<div className="h-10 w-px bg-black/10 dark:bg-white/10" aria-hidden="true" />
<div className="min-w-[140px] text-right">
    <div className={`text-[10px] font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'}`}>
        UTILISATEURS <span className="text-[#01b4e4]">TMDB</span>
    </div>
    <div className="mt-1 text-base font-bold font-mono text-[#01b4e4]" aria-live="polite">
        {tmdbRating.mediaId !== selectedMovie.id || tmdbRating.loading
            ? 'Chargement…'
            : typeof tmdbRating.rating === 'number'
                ? `${tmdbRating.rating.toFixed(1)} / 10`
                : 'Note indisponible'}
    </div>
</div>
```

Sur mobile, conserver `flex-wrap` et remplacer `text-right` par `text-left sm:text-right` si nécessaire pour éviter tout débordement. Le bloc TMDB ne doit contenir aucun bouton ni modifier `handleRate`.

- [ ] **Step 5: Vérifier le build frontend**

Run: `npm run build` from `proto-ui`

Expected: Vite produit le bundle de production sans erreur.

- [ ] **Step 6: Committer l’intégration frontend**

```bash
git add proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx
git commit -m "feat(ui): show TMDB rating on film detail"
```

## Task 3: Vérification complète et contrôle manuel

**Files:**
- Test: `tests/test_api.py`, suite backend complète et build `proto-ui`

**Interfaces:**
- Consumes: route et rendu final des Tasks 1 et 2.
- Produces: preuve que la nouvelle note n’introduit pas de régression dans la fiche ou les autres routes.

- [ ] **Step 1: Exécuter la suite backend complète**

Run: `pytest`

Expected: all existing and new backend tests PASS.

- [ ] **Step 2: Exécuter le lint frontend complet**

Run: `npm run lint` from `proto-ui`

Expected: PASS without new warnings.

- [ ] **Step 3: Exécuter le build frontend complet**

Run: `npm run build` from `proto-ui`

Expected: PASS.

- [ ] **Step 4: Vérifier manuellement une fiche avec une note TMDB**

Lancer l’interface, ouvrir un film avec un `tmdb_id` valide et vérifier que `UTILISATEURS TMDB` affiche une valeur comme `8,2 / 10`, pendant que la note personnelle reste interactive sur `5`.

- [ ] **Step 5: Vérifier manuellement une fiche sans association TMDB**

Ouvrir un film dont `tmdb_id` est absent et vérifier que seule la zone TMDB affiche `Note indisponible`, sans empêcher la fermeture, la notation, la lecture ou les changements de statut.

- [ ] **Step 6: Vérifier le comportement mobile et les réponses lentes**

À largeur mobile, vérifier qu’aucun débordement horizontal n’apparaît. Ouvrir rapidement deux fiches différentes et vérifier qu’une réponse tardive de la première ne remplace pas la note de la seconde.

- [ ] **Step 7: Contrôler le diff final et l’état du dépôt**

Run: `git diff HEAD~2 -- backend/api.py tests/test_api.py proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx`

Run: `git status --short`

Expected: seuls les fichiers de la fonctionnalité ont été commités par les tâches ; les changements préexistants du dépôt restent séparés et non réécrits.
