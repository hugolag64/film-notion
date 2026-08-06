# Liaison manuelle des comptes Backstage et Jellyfin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un administrateur d'associer, de modifier et de dissocier les comptes Backstage et Jellyfin avec une persistance SQLite sûre.

**Architecture:** Ajouter une colonne nullable et un index unique partiel à `users`, exposer une méthode dédiée dans `AuthStore`, puis ajouter un client Jellyfin administrateur qui ne retourne que `id`, `name` et `is_admin`. L'API vérifie les droits, l'existence du compte Jellyfin et les conflits avant d'enregistrer ; `AccountPanel` affiche ensuite un sélecteur par utilisateur.

**Tech Stack:** Python 3, FastAPI, SQLite, `httpx`, Pydantic, React 19, Vite, oxlint, pytest.

## Global Constraints

- L'identifiant Jellyfin est stocké comme une chaîne opaque dans `users.jellyfin_user_id`.
- Aucun mot de passe ni jeton Jellyfin par utilisateur n'est stocké ou envoyé au navigateur.
- Les endpoints de lecture et de modification sont réservés aux administrateurs.
- Un identifiant Jellyfin non nul ne peut être associé qu'à un seul compte Backstage.
- Une erreur Jellyfin ne doit jamais effacer une association existante.
- Cette phase ne change pas le lecteur vidéo ni la synchronisation de progression.
- Les fichiers `_backstage-backstage-1_logs.txt` et `stripe-x-a24.md` restent non suivis.

---

### Task 1: Étendre le modèle SQLite et `AuthStore`

**Files:**
- Modify: `backend/core/auth.py`
- Test: `tests/test_auth_migration.py`
- Test: `tests/test_auth_store.py`

**Interfaces:**
- `AuthUser` expose `jellyfin_user_id: str | None`.
- `AuthStore.list_users() -> list[AuthUser]` et `AuthStore.user_from_token(...)` renvoient ce champ.
- Ajouter `AuthStore.set_jellyfin_user_id(user_id: str, jellyfin_user_id: str | None) -> AuthUser`.
- Cette méthode lève `ValueError("user not found")` pour une cible inconnue et `ValueError("jellyfin user already linked")` pour un conflit.

- [ ] **Step 1: Écrire les tests de migration et de représentation utilisateur**

Ajouter des tests qui créent une ancienne table `users` sans `jellyfin_user_id`, exécutent `AuthStore.init_schema()`, puis vérifient :

```python
columns = {
    row[1]
    for row in sqlite3.connect(db_path).execute("PRAGMA table_info(users)")
}
assert "jellyfin_user_id" in columns

store = AuthStore(str(db_path))
user = store.create_user("Ophélie", "ophelie@example.com", "motdepasse")
assert user["jellyfin_user_id"] is None
```

Ajouter aussi un test de réexécution de `init_schema()` et un test montrant que la liste utilisateur conserve l'association.

- [ ] **Step 2: Lancer les tests ciblés pour confirmer l'échec**

Run: `py -m pytest -q tests/test_auth_migration.py tests/test_auth_store.py`

Expected: FAIL parce que la colonne et le champ de sortie n'existent pas encore.

- [ ] **Step 3: Implémenter la migration additive et la liaison transactionnelle**

Dans `init_schema()` :

```python
columns = {
    row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
}
if "jellyfin_user_id" not in columns:
    connection.execute("ALTER TABLE users ADD COLUMN jellyfin_user_id TEXT")
connection.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_jellyfin_user_id "
    "ON users(jellyfin_user_id) WHERE jellyfin_user_id IS NOT NULL"
)
```

Mettre à jour `_row_to_user`, les requêtes `INSERT` compatibles avec la colonne et ajouter `set_jellyfin_user_id()` dans une transaction `BEGIN IMMEDIATE`. Convertir une chaîne vide en `None`, laisser SQLite garantir l'unicité et convertir son `IntegrityError` en `ValueError("jellyfin user already linked")`.

- [ ] **Step 4: Vérifier les tests ciblés**

Run: `py -m pytest -q tests/test_auth_migration.py tests/test_auth_store.py`

Expected: PASS, y compris migration sur ancienne base, migration idempotente, association, changement, dissociation et conflit.

- [ ] **Step 5: Committer le livrable**

```bash
git add backend/core/auth.py tests/test_auth_migration.py tests/test_auth_store.py
git commit -m "feat: persist Jellyfin user links"
```

### Task 2: Ajouter la liste des utilisateurs au client Jellyfin

**Files:**
- Modify: `backend/core/jellyfin.py`
- Test: `tests/test_jellyfin.py`

**Interfaces:**
- Ajouter `JellyfinClient.list_users() -> list[dict[str, Any]]`.
- La méthode appelle `GET {base_url}/Users` avec `X-Emby-Token` et un timeout de 10 secondes.
- Chaque résultat renvoyé contient exactement `id`, `name` et `is_admin`.
- Les erreurs HTTP et les réponses JSON invalides sont propagées afin que l'API puisse répondre avec une erreur temporaire sans masquer l'indisponibilité.

- [ ] **Step 1: Écrire les tests HTTP du client**

Ajouter un faux client `httpx.AsyncClient` qui renvoie deux utilisateurs et vérifier :

```python
users = await JellyfinClient("http://jellyfin", "secret", client=fake).list_users()
assert users == [
    {"id": "jf-hugo", "name": "Hugo", "is_admin": True},
    {"id": "jf-ophelie", "name": "Ophélie", "is_admin": False},
]
assert request.url.path == "/Users"
assert request.headers["X-Emby-Token"] == "secret"
```

Ajouter un test de statut HTTP en erreur et un test de champ Jellyfin manquant pour vérifier que la méthode ne retourne jamais un résultat incomplet.

- [ ] **Step 2: Lancer les tests ciblés pour confirmer l'échec**

Run: `py -m pytest -q tests/test_jellyfin.py`

Expected: FAIL parce que `list_users()` n'existe pas encore.

- [ ] **Step 3: Implémenter `list_users()`**

Utiliser le client injecté comme dans les méthodes existantes, effectuer `raise_for_status()`, vérifier que la réponse contient une liste `Users`, puis réduire chaque entrée :

```python
return [
    {
        "id": str(item["Id"]),
        "name": str(item.get("Name") or item["Id"]),
        "is_admin": bool(item.get("Policy", {}).get("IsAdministrator", False)),
    }
    for item in payload["Users"]
]
```

Ne jamais inclure `Policy` complet, `Password`, `HashedPassword` ou un jeton dans le résultat.

- [ ] **Step 4: Vérifier le client Jellyfin**

Run: `py -m pytest -q tests/test_jellyfin.py`

Expected: PASS.

- [ ] **Step 5: Committer le livrable**

```bash
git add backend/core/jellyfin.py tests/test_jellyfin.py
git commit -m "feat: list Jellyfin users server-side"
```

### Task 3: Exposer les endpoints administrateur

**Files:**
- Modify: `backend/auth_api.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- Ajouter `JellyfinLinkRequest` avec `jellyfin_user_id: str | None`.
- Ajouter `GET /api/auth/jellyfin-users`, protégé par `require_admin`, qui renvoie `{"users": [...]}`.
- Ajouter `PUT /api/auth/users/{user_id}/jellyfin`, protégé par `require_admin`, qui renvoie `{"user": AuthUser}`.
- Ajouter une dépendance ou un helper `get_jellyfin_client() -> JellyfinClient | None` qui utilise `Config.JELLYFIN_URL` et `Config.JELLYFIN_API_KEY` sans exposer la clé.

- [ ] **Step 1: Écrire les tests d'API**

Couvrir :

```python
response = client.get("/api/auth/jellyfin-users", cookies=admin_cookie)
assert response.status_code == 200
assert response.json() == {
    "users": [{"id": "jf-ophelie", "name": "Ophélie", "is_admin": False}]
}

response = client.put(
    f"/api/auth/users/{backstage_user['id']}/jellyfin",
    json={"jellyfin_user_id": "jf-ophelie"},
    cookies=admin_cookie,
)
assert response.status_code == 200
assert response.json()["user"]["jellyfin_user_id"] == "jf-ophelie"
```

Ajouter les cas suivants : utilisateur non administrateur en `403`, Jellyfin non configuré en `503`, identifiant inconnu en `422`, utilisateur Backstage inconnu en `404`, doublon en `409`, dissociation avec `null` en `200`, et erreur Jellyfin en `503` sans modification de la liaison existante.

- [ ] **Step 2: Lancer les tests ciblés pour confirmer l'échec**

Run: `py -m pytest -q tests/test_auth_api.py`

Expected: FAIL parce que les routes et le modèle de requête n'existent pas encore.

- [ ] **Step 3: Implémenter les dépendances et routes**

Construire le client uniquement côté serveur. Pour une association non nulle, récupérer la liste Jellyfin avant d'écrire et refuser un identifiant absent. Pour une dissociation, écrire `NULL` directement afin qu'elle reste possible même si Jellyfin est temporairement arrêté.

Mapper les erreurs avec des réponses stables : `503` pour une configuration absente ou une erreur distante, `422` pour un identifiant Jellyfin inconnu, `404` pour un compte Backstage absent et `409` pour un conflit d'unicité.

- [ ] **Step 4: Vérifier l'API et la non-régression d'authentification**

Run: `py -m pytest -q tests/test_auth_api.py tests/test_auth_store.py tests/test_jellyfin.py`

Expected: PASS ; `GET /api/auth/me` et `GET /api/auth/users` contiennent le nouveau champ sans exposer de secret Jellyfin.

- [ ] **Step 5: Committer le livrable**

```bash
git add backend/auth_api.py tests/test_auth_api.py
git commit -m "feat: add admin Jellyfin account linking API"
```

### Task 4: Ajouter le sélecteur Jellyfin dans le panneau admin

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/AccountPanel.jsx`

**Interfaces:**
- Ajouter `fetchJellyfinUsers() -> Promise<Array<{id: string, name: string, is_admin: boolean}>>`.
- Ajouter `linkJellyfinUser(userId, jellyfinUserId) -> Promise<AuthUser>` qui envoie `null` pour dissocier.
- `AccountPanel` conserve les données Backstage déjà chargées si la liste Jellyfin échoue.

- [ ] **Step 1: Ajouter les fonctions client HTTP**

Dans `proto-ui/src/api.js`, réutiliser `authRequest` :

```javascript
export async function fetchJellyfinUsers() {
    return (await authRequest('/jellyfin-users')).users;
}

export async function linkJellyfinUser(userId, jellyfinUserId) {
    return (await authRequest(`/users/${encodeURIComponent(userId)}/jellyfin`, {
        method: 'PUT',
        body: JSON.stringify({jellyfin_user_id: jellyfinUserId || null}),
    })).user;
}
```

- [ ] **Step 2: Intégrer le chargement et l'état de liaison**

Dans `AccountPanel.jsx`, charger les utilisateurs Jellyfin uniquement pour un administrateur. Ajouter un état `jellyfinUsers`, un état `jellyfinLoading` et une table `jellyfinSaving` par compte Backstage. En cas d'erreur, afficher le message existant sans remplacer `users`.

- [ ] **Step 3: Ajouter le sélecteur par compte Backstage**

Pour chaque utilisateur, afficher un `<select>` dont la valeur est `target.jellyfin_user_id || ''`. Ajouter l'option `Non associé`, les comptes Jellyfin disponibles et une mention `déjà associé` pour les identifiants utilisés par un autre compte. Désactiver les options déjà prises et le sélecteur pendant sa sauvegarde.

À la sélection, appeler `linkJellyfinUser(target.id, value)`, puis rafraîchir les utilisateurs Backstage. En cas d'erreur, conserver la valeur affichée précédemment et afficher le détail fourni par l'API.

- [ ] **Step 4: Vérifier le lint et le build frontend**

Run: `npm --prefix proto-ui run lint`

Expected: PASS sans erreur oxlint.

Run: `npm --prefix proto-ui run build`

Expected: PASS ; le warning de taille de bundle existant est acceptable s'il reste inchangé.

- [ ] **Step 5: Committer le livrable**

```bash
git add proto-ui/src/api.js proto-ui/src/AccountPanel.jsx
git commit -m "feat: manage Jellyfin links in account panel"
```

### Task 5: Validation intégrée et déploiement

**Files:**
- Modify: `docs/backstage-authentication.md` pour documenter la procédure de liaison administrateur
- Test: `tests/test_auth_api.py`, `tests/test_auth_store.py`, `tests/test_jellyfin.py`

**Interfaces:**
- Aucun nouveau contrat ; cette tâche vérifie les contrats des tâches précédentes ensemble.

- [ ] **Step 1: Exécuter toute la suite backend**

Run: `py -m pytest -q`

Expected: tous les tests passent.

- [ ] **Step 2: Vérifier le compose**

Run: `docker compose config --quiet`

Expected: aucune sortie et code retour `0`.

- [ ] **Step 3: Effectuer la vérification manuelle locale**

Dans l'interface :

1. se connecter avec un compte administrateur ;
2. ouvrir Compte > Utilisateurs ;
3. vérifier que Hugo et Ophélie apparaissent dans les comptes Jellyfin ;
4. associer Ophélie à son compte Jellyfin ;
5. recharger le panneau et vérifier que l'association est conservée ;
6. tenter la même association sur un autre compte et vérifier le refus ;
7. dissocier Ophélie et vérifier le retour à `Non associé` ;
8. se connecter avec un compte utilisateur et vérifier que le sélecteur administrateur n'est pas visible.

- [ ] **Step 4: Vérifier la base persistante dans Docker**

Après déploiement, exécuter sur le serveur :

```bash
sudo docker exec backstage-backstage-1 python -c "import sqlite3; c=sqlite3.connect('/data/backstage.db'); print(c.execute('SELECT display_name, jellyfin_user_id FROM users').fetchall())"
```

Expected: le champ existe et l'association reste présente après un redéploiement du conteneur.

- [ ] **Step 5: Pousser après validation**

```bash
git push origin agent/backstage-docker-deployment
```

Le lecteur vidéo doit rester inchangé pendant cette livraison ; l'utilisation de `jellyfin_user_id` pour la progression fera l'objet d'un plan séparé.
