# Retirer la reprise de lecture de l’accueil — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retirer le bloc « Reprendre la lecture » de la page catalogue tout en conservant la lecture dans la fiche du média.

**Architecture:** Ne modifier ni l’API Jellyfin ni le stockage de progression. Supprimer uniquement le rendu du résumé de lecture dans la vue catalogue et conserver les actions de lecture utilisées par la fiche détaillée.

**Tech Stack:** React, Vite, ESLint, build de production.

## Global Constraints

- Le résumé Jellyfin continue d’être synchronisé.
- « Reprendre la lecture » ne doit plus apparaître sur la page catalogue.
- Les contrôles de lecture dans la fiche film/série restent inchangés.

---

### Task 1: Retirer le résumé de lecture du catalogue

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx:869-1090`
- Test: validation par `npm run lint` et `npm run build`

**Interfaces:**
- Consumes: état existant `playbackSummary` utilisé par la fiche détaillée.
- Produces: catalogue sans bloc de résumé, fiche détaillée inchangée.

- [ ] **Step 1: Vérifier le rendu actuel**

Confirmer que le bloc catalogue est le rendu conditionnel autour du titre `Reprendre la lecture`, tandis que la fiche détaillée conserve ses propres boutons de lecture.

- [ ] **Step 2: Supprimer uniquement le bloc catalogue**

Retirer le JSX du bloc d’accueil contenant `Reprendre la lecture`, `PROCHAINS ÉPISODES` et les médias récemment terminés, sans supprimer les états, appels API ni handlers de lecture nécessaires à la fiche détaillée.

- [ ] **Step 3: Vérifier le code**

Run: `npm run lint`

Expected: succès sans erreur.

Run: `npm run build`

Expected: build Vite réussi.

- [ ] **Step 4: Contrôler le diff**

Run: `git diff --check`

Expected: aucune erreur d’espacement ou de formatage.
