# Backstage — Enrichisseur de vidéothèque Notion

Application web locale (NiceGUI) qui enrichit automatiquement une base de données
Notion de films à partir de l'API [TMDB](https://www.themoviedb.org/) :
réalisateur, synopsis, genres → catégories, tags, date de sortie, statut/support,
et affiche en couverture.

## Prérequis

- Python 3.10+
- Une intégration Notion (token) avec accès à la base films
- Une clé API TMDB (v3)

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Configuration

Crée un fichier `.env` à la racine :

```dotenv
NOTION_TOKEN=secret_xxx
DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TMDB_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optionnels
ANTHROPIC_API_KEY=sk-ant-...   # active l'onglet « Reco IA » (Claude)
OMDB_API_KEY=xxxxxxxx          # ajoute note IMDb + classification d'âge aux candidats
SYNC_INTERVAL_MIN=0            # >0 : synchronisation auto toutes les N minutes
BACKSTAGE_DEV=0               # 1 : recharge à chaud (dev)
```

## Fonctionnalités

- **Enrichissement automatique** concurrent (films **et séries**) + résolution manuelle des ambiguïtés (wizard avec affiches, réalisateur, synopsis, note IMDb).
- **Recherche manuelle libre** (titre + année) dans le wizard.
- **Dry-run** : prévisualiser les changements avant toute écriture Notion.
- **Statistiques** : taux d'enrichissement, top genres, répartition, **détection de doublons**.
- **Historique** des modifications (auto/manuel) dans `history.jsonl`.
- **Reco IA** (Claude) : suggestions à partir des films notés (si `ANTHROPIC_API_KEY`).
- **Sync auto** périodique optionnelle (`SYNC_INTERVAL_MIN`).

## Schéma Notion attendu

La base Notion doit contenir les propriétés suivantes (noms exacts) :

| Propriété        | Type Notion   | Rôle                                   |
|------------------|---------------|----------------------------------------|
| `Nom`            | Title         | Titre du film (clé de recherche TMDB)  |
| `Type`           | Select        | Film, Série…                           |
| `Statut`         | Select        | « À regarder », « Terminé »…           |
| `Support`        | Select        | « Cinéma », « À télécharger », « NAS »…|
| `Note /10`       | Select        | Note                                   |
| `Date de sortie` | Date          | Date de sortie                         |
| `Réalisateur`    | Rich text     | Réalisateur                            |
| `Catégorie`      | Multi-select  | Genres                                 |
| `Synopsis`       | Rich text     | Synopsis                               |
| `Tags`           | Multi-select  | Tags dérivés des genres                |
| `Avis`           | Rich text     | Avis personnel                         |
| `TMDB_OK`        | Checkbox      | Marque les fiches enrichies            |

> ⚠️ Les noms de propriétés sont codés en dur dans `backend/core/notion.py`.
> Un renommage côté Notion casse le mapping.

## Lancement

```bash
python main.py
```

Ouvre http://localhost:8080.

## Architecture

```
main.py              → bootstrap NiceGUI
backend/config.py    → variables d'environnement
backend/core/
  models.py          → modèle pydantic Media
  notion.py          → client Notion (httpx async)
  tmdb.py            → client TMDB (httpx async)
  processor.py       → matching + règles + orchestration
  cache_service.py   → cache « déjà traité » (avec hash de contenu)
frontend/ui.py       → vue NiceGUI (dashboard + wizard)
scripts/             → scripts de debug manuels
```
