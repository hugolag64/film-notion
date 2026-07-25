# Assainissement de Backstage

## Objectif

Réduire Backstage à son produit actif : une médiathèque locale React/FastAPI/SQLite enrichie par TMDB et intégrée à Sonarr, Radarr et Jellyfin. Le code retiré reste versionné dans une archive structurée afin de pouvoir être consulté ou restauré sans alourdir le chemin d'exécution.

## Périmètre actif

- `main.py`, `backend/api.py`, `backend/config.py` et `backend/core/` nécessaires à SQLite, TMDB, HTTP, séries/épisodes et au serveur média.
- `proto-ui/`, construit dans `proto-ui/dist`, qui est l'unique interface servie par l'application.
- Les tests relatifs au périmètre actif, `README.md`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `restart_server.bat` et la documentation courante.

## Archive versionnée

Les éléments retirés du chemin actif sont déplacés sous `legacy/2026-07-cleanup/` :

| Destination | Contenu |
|---|---|
| `nicegui/` | ancien dossier `frontend/` et ses tests dédiés |
| `notion-enrichment/` | client Notion, processeur d'enrichissement, IA, OMDb, cache, diff, historique et leurs tests |
| `scripts/` | scripts de migration, inspection et diagnostic Notion/TMDB devenus inutiles |
| `docs/` | anciens plans et spécifications d'itérations terminées |
| `notes/` | `stripe-x-a24.md` |

Une courte note `legacy/2026-07-cleanup/README.md` explique que l'archive ne fait pas partie de l'exécution ni de la suite de tests.

## Nettoyage du produit actif

- Retirer le faux streaming : route `POST /medias/{id}/stream`, helper React `triggerStream`, URL synthétique HP ProDesk et modal simulant un lecteur. Seul le lien Jellyfin reste.
- Retirer les variables Notion, Anthropic et OMDb de `Config`, de `.env.example`, du README et des requirements.
- Simplifier le scheduler afin qu'il ne lance plus l'enrichissement historique ; conserver uniquement la synchronisation média-server optionnelle.
- Retirer les imports, tests et dépendances associés au code archivé.
- Garder TMDB : il est nécessaire à l'ajout, au rapprochement et à l'enrichissement minimal des films et séries.

## Contraintes de sécurité et de données

- Ne pas déplacer `.env`, `backstage.db`, les caches locaux ou les fichiers de dépendances installées.
- Ne jamais écrire de clé API dans un fichier suivi par Git.
- L'archive est déplacée avec l'historique Git de la branche ; aucun contenu utilisateur n'est supprimé.

## Vérification

- `python -m pytest -q` passe avec seulement les tests du produit actif.
- `npm run build` et `npm run lint` passent depuis `proto-ui/`.
- Démarrer `python main.py` sert l'interface React et expose les routes média-server sans import NiceGUI/Notion.
- Une recherche textuelle ne laisse aucune référence active à Notion, Anthropic, OMDb, `frontend`, `triggerStream`, `hp-prodesk.local` ou au faux endpoint de streaming.
