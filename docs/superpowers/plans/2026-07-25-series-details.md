# Détails des séries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter les détails complets aux séries, synopsis d'épisode, titre original sélectionnable et badges de support exacts.

**Architecture:** Les données TMDB ajoutent titre original et synopsis d'épisode à SQLite. La fiche Série sépare Détails et Épisodes, tout en réutilisant les interactions de la fiche Film. Les badges n'utilisent que les supports réellement stockés.

**Tech Stack:** Python, SQLite, FastAPI, React, Vite, pytest.

## Global Constraints

- Les séries n'exposent pas le support Cinéma.
- Le titre original devient principal uniquement après action explicite.
- Les badges de support sont absents si aucun support n'est enregistré.

---

### Task 1: Données série enrichies

**Files:** `backend/core/models.py`, `backend/core/store.py`, `backend/api.py`, `tests/test_series.py`

- [ ] Écrire un test en échec prouvant que l'import TV conserve `original_name` et `overview` d'épisode.
- [ ] Exécuter `py -m pytest tests/test_series.py -v` et observer l'échec.
- [ ] Ajouter les champs, migrations et l'action API de promotion du titre original.
- [ ] Rejouer `py -m pytest tests/test_series.py -v` et obtenir PASS.

### Task 2: Fiche Série et badges exacts

**Files:** `proto-ui/src/BackstagePrototype.jsx`, `proto-ui/src/api.js`, `tests/test_theme.py`

- [ ] Écrire un test de régression en échec pour les onglets Détails/Épisodes et l'absence de badge par défaut.
- [ ] Exécuter le test ciblé et observer l'échec.
- [ ] Ajouter les onglets, synopsis d'épisode, action titre original et réutiliser les détails Film hors Cinéma.
- [ ] Filtrer les badges vides et ne jamais injecter `Serveur` comme valeur de repli.
- [ ] Exécuter `py -m pytest -q; Push-Location proto-ui; npm run build; Pop-Location` et obtenir PASS.
