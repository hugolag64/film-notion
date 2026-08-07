# Library Sync and Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nettoyer la file Seerr, synchroniser les médias importés, moderniser la fiche film et améliorer la navigation par catégories.

**Architecture:** Le backend filtre et supprime les demandes Seerr disponibles, enrichit les imports Radarr/Sonarr avec TMDB et expose le résultat dans les contrats existants. Le frontend utilise une fenêtre de gestion des demandes, une fiche film sans infrastructure visible et des rails de catégories sans sidebar flottante.

**Tech Stack:** FastAPI, Pydantic, pytest, React, Tailwind, Vite, Radarr/Sonarr, Seerr et TMDB.

## Global Constraints

- Une demande disponible disparaît de la file active et de Seerr, mais le film Backstage est conservé.
- L’import serveur est idempotent et une panne TMDB ne bloque pas la création locale.
- Aucune mention de `HP ProDesk`, URL locale ou nom de machine ne doit apparaître dans la fiche film.
- Les changements existants sur les recommandations restent non indexés.

### Task 1: File Seerr et gestion des demandes

**Files:**
- Modify: `backend/api.py`, `backend/core/dashboard.py`, `backend/core/seerr.py`
- Modify: `proto-ui/src/components/DashboardHome.jsx`, `proto-ui/src/BackstagePrototype.jsx`
- Test: `tests/test_arr.py`, `tests/test_dashboard.py`, `tests/test_api.py`, `tests/test_dashboard_layout_contract.py`

- [ ] Écrire un test rouge vérifiant que les demandes disponibles sont supprimées de Seerr et absentes de `payload["requests"]`.
- [ ] Écrire un test rouge vérifiant la fenêtre de gestion avec date, statut et suppression par ligne.
- [ ] Implémenter le filtrage actif, la suppression best-effort et la fenêtre de gestion.
- [ ] Exécuter les tests ciblés puis la suite Python.

### Task 2: Synchronisation bidirectionnelle

**Files:**
- Modify: `backend/core/media_server.py`, `backend/api.py`
- Test: `tests/test_media_server.py`, `tests/test_api.py`

- [ ] Écrire un test rouge où Radarr expose un film absent localement et où l’import crée un média avec affiche TMDB.
- [ ] Implémenter l’enrichissement TMDB avec fallback sur le titre distant et rendre `sync_all()` idempotent.
- [ ] Déclencher l’import lors de la synchronisation serveur/dashboard sans bloquer si TMDB est indisponible.
- [ ] Exécuter les tests de synchronisation et vérifier qu’un second passage ne crée aucun doublon.

### Task 3: Fiche film et en-tête

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Test: `tests/test_dashboard_layout_contract.py`

- [ ] Écrire les assertions de contrat interdisant les mentions machine et exigeant `Lire`/`Demander ce film` ainsi qu’un favori dans la barre d’action.
- [ ] Remplacer le bandeau HP par une action film contextuelle et supprimer le bouton favori du footer redondant.
- [ ] Réserver davantage d’espace au centre de l’en-tête et réduire la recherche/utilitaires pour que Séries reste visible.
- [ ] Exécuter lint et build frontend.

### Task 4: Bibliothèque Netflix/catégories

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`, éventuellement `proto-ui/src/library.js`
- Test: `tests/test_dashboard_layout_contract.py`

- [ ] Écrire le contrat de disparition de la sidebar flottante et de présence des rails de catégories.
- [ ] Ajouter des puces de catégories sélectionnables et des rails horizontaux par genre sans casser recherche/tri.
- [ ] Vérifier les états vides, le mode sombre et la navigation clavier.
- [ ] Exécuter la suite frontend complète.

### Task 5: Vérification et publication

- [ ] Exécuter `pytest -q`, `npm run lint`, `npm run build` et `git diff --check`.
- [ ] Vérifier que seuls les fichiers du sprint sont indexés.
- [ ] Committer avec `feat: improve requests sync and library UX` puis pousser `origin main`.
