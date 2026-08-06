# Unification administration et utilisateurs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regrouper toutes les fonctions de pilotage dans `Administration`, garder `GogBoss` personnel, et rendre la gestion des utilisateurs complète et cliquable dans un seul écran.

**Architecture:** Extraire un composant React `UserManagement` responsable de l’état, du rendu et des mutations utilisateurs. `AdminCenter` devient l’unique point de montage de ce composant et récupère les blocs de pilotage actuellement présents dans `AccountPanel`; `AccountPanel` conserve uniquement les données personnelles et de session.

**Tech Stack:** React 19, Vite, Tailwind CSS, API REST existante, pytest backend.

## Global Constraints

- Ne pas modifier les données persistantes ni le volume Docker.
- Conserver les endpoints d’authentification existants et leurs règles d’autorisation.
- Ne pas permettre à un administrateur de supprimer son propre compte.
- Préserver les fichiers non liés déjà présents dans l’arbre de travail.

---

### Task 1: Extraire la gestion des utilisateurs

**Files:**
- Create: `proto-ui/src/components/UserManagement.jsx`
- Modify: `proto-ui/src/AccountPanel.jsx`
- Modify: `proto-ui/src/components/AdminCenter.jsx`

**Interfaces:**
- `UserManagement({isDarkMode, currentUser, onError, onNotice})` charge `fetchUsers` et `fetchJellyfinUsers`.
- Le composant expose les actions de création, modification, association Jellyfin, mot de passe, rôle, activation et suppression.

- [ ] **Step 1: Add the regression test seam**

Vérifier d’abord que `npm run build` échoue si `AdminCenter` importe un composant absent, puis utiliser le build comme seam UI disponible dans ce dépôt sans framework de test React.

- [ ] **Step 2: Run the build and capture the expected failure**

Run: `npm --prefix proto-ui run build`

Expected: failure only while the new import is intentionally unresolved.

- [ ] **Step 3: Extract the existing CRUD behavior**

Déplacer de `AccountPanel.jsx` vers `UserManagement.jsx` les états `users`, `jellyfinUsers`, `newUser`, `adminPasswords`, les chargements et les handlers associés. Le rendu doit reprendre les contrôles existants mais sous forme de cartes cliquables avec un panneau d’édition visible.

- [ ] **Step 4: Mount the component in Administration**

Remplacer la liste statique de `AdminCenter` par `<UserManagement ... />`, et rendre la carte « Utilisateurs » de la vue d’ensemble actionnable avec `setSection('users')`.

- [ ] **Step 5: Run the build**

Run: `npm --prefix proto-ui run build`

Expected: exit code 0.

### Task 2: Séparer compte personnel et pilotage

**Files:**
- Modify: `proto-ui/src/AccountPanel.jsx`
- Modify: `proto-ui/src/components/AdminCenter.jsx`

**Interfaces:**
- `AccountPanel` affiche uniquement nom, mot de passe, notifications, appareils mémorisés et déconnexion.
- `AdminCenter` affiche tableau de bord, sauvegarde, stockage, demandes de conservation, nettoyage, utilisateurs, services et paramètres.

- [ ] **Step 1: Remove administrative blocks from AccountPanel**

Supprimer du panneau GogBoss le tableau de bord administrateur, les sauvegardes, le stockage, les demandes, l’aperçu de nettoyage et le rendu utilisateurs.

- [ ] **Step 2: Move administrative data loading to AdminCenter**

Conserver dans `AdminCenter` le chargement déjà existant et y ajouter les actions administratives retirées, avec les mêmes endpoints et messages d’erreur.

- [ ] **Step 3: Keep personal session controls in GogBoss**

Conserver uniquement les appareils mémorisés et les notifications liées à l’utilisateur connecté.

- [ ] **Step 4: Build and inspect the rendered labels**

Run: `npm --prefix proto-ui run build`

Expected: exit code 0, sans erreur ESLint/Oxlint bloquante.

### Task 3: Vérification fonctionnelle et publication

**Files:**
- Modify: none beyond Tasks 1-2.

**Interfaces:**
- Production UI: `Administration > Utilisateurs` doit permettre de cliquer un utilisateur et d’exécuter les actions autorisées.

- [ ] **Step 1: Run frontend checks**

Run: `npm --prefix proto-ui run build` and `npm --prefix proto-ui run lint`.

- [ ] **Step 2: Run targeted backend auth tests**

Run: `pytest -q tests/test_auth_api.py`.

- [ ] **Step 3: Inspect the diff and preserve unrelated files**

Run: `git status --short` and `git diff --check`; stage only the new spec/plan and implementation files.

- [ ] **Step 4: Commit and push**

Run: `git add -- docs/superpowers/plans/2026-08-06-unification-administration-utilisateurs.md proto-ui/src/AccountPanel.jsx proto-ui/src/components/AdminCenter.jsx proto-ui/src/components/UserManagement.jsx && git commit -m "feat: centralize administration controls" && git push origin main`.
