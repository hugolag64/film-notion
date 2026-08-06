# Backstage Authentication and Roles Implementation Plan

> **Pour les agents :** utiliser `superpowers:executing-plans` (ou `superpowers:subagent-driven-development`) pour exécuter ce plan tâche par tâche. Chaque étape utilise la syntaxe de suivi `[ ]`.

**Objectif :** ajouter la première installation, l’authentification par cookie, la mémorisation d’appareil pendant 30 jours, les sessions révocables et les rôles `admin`/`user` sans perdre le catalogue SQLite existant.

**Architecture :** un module `AuthStore` isolera les opérations SQLite liées aux comptes et sessions. Un routeur FastAPI `/api/auth` fournira l’installation, la connexion, la gestion des appareils et l’administration des utilisateurs. Le frontend React passera par un `AuthGate` qui bloque l’application principale tant que l’utilisateur n’est pas authentifié.

**Technologies :** Python 3.11, FastAPI, SQLite, `hashlib.scrypt`, cookies `HttpOnly`, React 19, Vite, pytest.

## Contraintes globales

- Ne jamais modifier ni supprimer les lignes existantes de `media`, `episode` ou `media_availability`.
- Ne jamais stocker de mot de passe, cookie brut ou jeton de session dans les logs, Git ou les variables Portainer.
- Le cookie de session reste inaccessible à JavaScript et utilise `SameSite=Lax`.
- Une session mémorisée expire après 30 jours ; une session normale expire après 24 heures au maximum.
- La configuration Docker actuelle doit continuer à utiliser `/srv/data/backstage/backstage.db`.
- Chaque étape de comportement commence par un test qui échoue, puis une implémentation minimale, puis une vérification complète.
- Les modifications locales existantes hors du périmètre de l’authentification ne doivent pas être incluses dans les commits.

---

### Tâche 1 : ajouter les tables d’authentification et les primitives de sécurité

**Fichiers :**
- Créer : `backend/core/auth.py`
- Modifier : `backend/core/store.py`
- Créer : `tests/test_auth_store.py`

**Interfaces produites :**

```python
class AuthUser(TypedDict):
    id: str
    display_name: str
    email: str
    role: Literal["admin", "user"]
    is_active: bool

class AuthStore:
    def __init__(self, db_path: str): ...
    def create_admin(self, display_name: str, email: str, password: str) -> AuthUser: ...
    def create_user(self, display_name: str, email: str, password: str) -> AuthUser: ...
    def authenticate(self, email: str, password: str, remember_device: bool, user_agent: str | None) -> tuple[AuthUser, str, datetime]: ...
    def user_from_token(self, token: str) -> tuple[AuthUser, str] | None: ...
    def revoke_token(self, token: str) -> bool: ...
    def list_sessions(self, user_id: str, current_session_id: str) -> list[dict[str, object]]: ...
    def revoke_session(self, user_id: str, session_id: str) -> bool: ...
    def revoke_other_sessions(self, user_id: str, current_session_id: str) -> int: ...
    def list_users(self) -> list[AuthUser]: ...
    def update_user(self, user_id: str, fields: dict[str, object]) -> AuthUser: ...
```

- [ ] **Étape 1 : écrire le test de migration additive.**

```python
def test_auth_schema_is_added_without_changing_media(tmp_path):
    db = tmp_path / "backstage.db"
    store = MediaStore(str(db))
    store.init_schema()
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO media (id, title, tmdb_ok) VALUES (?, ?, ?)",
            ("movie-1", "Dune", 1),
        )
    AuthStore(str(db)).init_schema()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT title FROM media WHERE id = 'movie-1'").fetchone() == ("Dune",)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"users", "auth_sessions"} <= tables
```

- [ ] **Étape 2 : exécuter le test et vérifier qu’il échoue parce que `AuthStore` n’existe pas.**

Run: `pytest tests/test_auth_store.py::test_auth_schema_is_added_without_changing_media -q`

- [ ] **Étape 3 : implémenter les tables `users` et `auth_sessions`.** Ajouter `AuthStore.init_schema()` avec les deux tables, les contraintes de rôle et les index de la spécification. Appeler cette initialisation depuis `main.py` après `MediaStore.init_schema()`.

- [ ] **Étape 4 : écrire les tests de hachage et de vérification des mots de passe.** Vérifier qu’un mot de passe valide est accepté, qu’un mot de passe différent est rejeté et que deux hachages du même mot de passe utilisent des sels différents.

- [ ] **Étape 5 : implémenter le format `scrypt$N=16384$r=8$p=1$<salt>$<digest>`.** Utiliser `secrets.token_bytes(16)`, `hashlib.scrypt`, une comparaison `hmac.compare_digest`, et ne jamais retourner le mot de passe ou le digest depuis l’API.

- [ ] **Étape 6 : écrire les tests de création d’admin, création d’utilisateur et protection du dernier admin.** Vérifier email insensible à la casse, doublon en `409` au niveau service, création des rôles attendus, refus de désactiver/démoter le dernier administrateur et révocation des sessions d’un utilisateur désactivé.

- [ ] **Étape 7 : implémenter les opérations `AuthStore`.** Stocker les dates en UTC ISO 8601, générer les identifiants avec `uuid.uuid4()`, générer les jetons avec `secrets.token_urlsafe(32)`, et ne stocker que le SHA-256 du jeton. Respecter les règles de 24 heures, 30 jours, sessions révoquées et nettoyage des sessions expirées.

- [ ] **Étape 8 : exécuter toute la suite backend.**

Run: `pytest -q`

- [ ] **Étape 9 : committer la persistance d’authentification.**

```bash
git add backend/core/auth.py backend/core/store.py main.py tests/test_auth_store.py
git commit -m "feat: add authentication persistence"
```

### Tâche 2 : exposer l’API d’authentification et les dépendances d’autorisation

**Fichiers :**
- Créer : `backend/auth_api.py`
- Modifier : `backend/api.py`
- Modifier : `main.py`
- Créer : `tests/test_auth_api.py`

**Interfaces produites :**

```python
auth_router: APIRouter
async def get_current_user(request: Request) -> AuthContext: ...
async def require_admin(user: AuthContext = Depends(get_current_user)) -> AuthContext: ...
```

- [ ] **Étape 1 : écrire les tests de routes.** Tester `GET /api/auth/status`, setup, login valide/invalide, `/me`, logout, expiration, révocation d’appareil, création d’utilisateur par un admin et refus d’accès d’un utilisateur normal.

- [ ] **Étape 2 : exécuter les tests et vérifier l’échec sur les routes absentes.**

Run: `pytest tests/test_auth_api.py -q`

- [ ] **Étape 3 : créer les modèles Pydantic et le routeur `/api/auth`.** Implémenter les réponses génériques pour les identifiants invalides, `409` pour setup déjà réalisé ou email dupliqué, et `403` pour un utilisateur inactif.

- [ ] **Étape 4 : implémenter la dépendance de session.** Lire le cookie `backstage_session`, retrouver le hash en base, vérifier expiration/révocation/utilisateur actif, puis exposer l’utilisateur et l’identifiant de session au handler.

- [ ] **Étape 5 : implémenter les cookies.** Utiliser `HttpOnly=True`, `SameSite="lax"`, `max_age=30*24*60*60` pour un appareil mémorisé, aucune expiration explicite pour une session normale, et `Secure` piloté par `BACKSTAGE_COOKIE_SECURE` avec `false` par défaut sur le serveur LAN.

- [ ] **Étape 6 : brancher le routeur et l’initialisation.** Inclure `auth_router` dans `main.py` sous `/api`, appeler `AuthStore.init_schema()` au démarrage, et retirer le CORS générique `allow_origins=["*"]` avec credentials afin de ne pas autoriser des credentials cross-origin.

- [ ] **Étape 7 : protéger les routes existantes.** Ajouter `Depends(get_current_user)` aux routes de catalogue, modification, lecture et statut ; ajouter `Depends(require_admin)` à l’import, la synchronisation et l’acquisition Radarr/Sonarr. Laisser `/health` public.

- [ ] **Étape 8 : exécuter les tests backend.**

Run: `pytest -q`

- [ ] **Étape 9 : committer l’API.**

```bash
git add backend/auth_api.py backend/api.py main.py tests/test_auth_api.py
git commit -m "feat: add authentication API"
```

### Tâche 3 : ajouter le client API et le garde d’authentification React

**Fichiers :**
- Créer : `proto-ui/src/AuthGate.jsx`
- Modifier : `proto-ui/src/App.jsx`
- Modifier : `proto-ui/src/api.js`
- Modifier : `proto-ui/src/App.css`

**Interfaces produites :**

```javascript
export async function fetchAuthStatus() {}
export async function fetchCurrentUser() {}
export async function setupAdmin(payload) {}
export async function login(payload) {}
export async function logout() {}
export async function fetchDevices() {}
export async function revokeDevice(sessionId) {}
export async function revokeOtherDevices() {}
export async function fetchUsers() {}
export async function createUser(payload) {}
export async function updateUser(userId, payload) {}
```

- [ ] **Étape 1 : écrire un test de build-facing contract.** Ajouter dans `proto-ui/src/api.js` des appels qui envoient `credentials: 'same-origin'`; vérifier par inspection/lint que toutes les fonctions d’authentification utilisent le même comportement.

- [ ] **Étape 2 : implémenter les fonctions API.** Centraliser le traitement des réponses JSON et des erreurs `401`, `403` et `409`; ne jamais lire le cookie depuis JavaScript.

- [ ] **Étape 3 : créer `AuthGate`.** Gérer explicitement les états `loading`, `setup`, `login`, `authenticated` et `error`. Après setup ou login, stocker uniquement le profil utilisateur en mémoire.

- [ ] **Étape 4 : créer les formulaires setup et login.** Le setup exige confirmation du mot de passe et 8 caractères minimum côté interface ; le serveur reste l’autorité de validation. Le login expose la case « Se souvenir de cet appareil ».

- [ ] **Étape 5 : intégrer `AuthGate` dans `App.jsx`.** Ne monter `BackstagePrototype` qu’après authentification, afin qu’il ne lance pas de requêtes médias anonymes. Fournir au composant principal le profil courant et une fonction de déconnexion.

- [ ] **Étape 6 : ajouter le style minimal.** Réutiliser les couleurs et variables existantes de `App.css`, avec une carte centrée, champs accessibles, labels explicites, messages d’erreur et états de chargement.

- [ ] **Étape 7 : vérifier lint et build.**

Run: `npm --prefix proto-ui run lint`

Run: `npm --prefix proto-ui run build`

- [ ] **Étape 8 : commit.**

```bash
git add proto-ui/src/AuthGate.jsx proto-ui/src/App.jsx proto-ui/src/api.js proto-ui/src/App.css
git commit -m "feat: add Backstage authentication gate"
```

### Tâche 4 : ajouter la gestion des appareils et des utilisateurs

**Fichiers :**
- Créer : `proto-ui/src/AccountPanel.jsx`
- Modifier : `proto-ui/src/BackstagePrototype.jsx`
- Modifier : `proto-ui/src/api.js`
- Modifier : `proto-ui/src/App.css`
- Modifier : `tests/test_auth_api.py`

- [ ] **Étape 1 : écrire les tests API d’isolation.** Vérifier qu’un utilisateur ne peut révoquer que ses propres sessions, que `revoke-others` conserve la session courante et qu’un admin peut créer ou désactiver un utilisateur.

- [ ] **Étape 2 : exécuter ces tests en échec.**

Run: `pytest tests/test_auth_api.py -k "device or user" -q`

- [ ] **Étape 3 : finaliser les endpoints appareils et utilisateurs.** Retourner uniquement les métadonnées sûres, empêcher la suppression/démotion du dernier admin, et révoquer immédiatement les sessions d’un utilisateur désactivé.

- [ ] **Étape 4 : créer `AccountPanel`.** Afficher l’utilisateur courant, déconnexion, liste des appareils, révocation d’un appareil, révocation des autres appareils, et pour un admin la liste des utilisateurs avec création et activation/désactivation.

- [ ] **Étape 5 : intégrer le panneau dans l’interface existante.** Ajouter un bouton de compte discret dans `BackstagePrototype` sans déplacer la logique catalogue ni modifier les données médias.

- [ ] **Étape 6 : vérifier le frontend.**

Run: `npm --prefix proto-ui run lint`

Run: `npm --prefix proto-ui run build`

- [ ] **Étape 7 : commit.**

```bash
git add backend/auth_api.py proto-ui/src/AccountPanel.jsx proto-ui/src/BackstagePrototype.jsx proto-ui/src/api.js proto-ui/src/App.css tests/test_auth_api.py
git commit -m "feat: add account and device management"
```

### Tâche 5 : vérifier la migration, le Docker et le déploiement Portainer

**Fichiers :**
- Modifier : `README.md`
- Créer : `docs/backstage-authentication.md`
- Créer : `tests/test_auth_migration.py`

- [ ] **Étape 1 : écrire le test de non-régression des données.** Créer une base temporaire avec 252 médias et 1091 épisodes représentatifs, initialiser l’authentification, puis vérifier les mêmes comptes de lignes et la lecture d’un média.

- [ ] **Étape 2 : exécuter le test et corriger uniquement les problèmes de migration.**

Run: `pytest tests/test_auth_migration.py -q`

- [ ] **Étape 3 : documenter l’installation serveur.** Décrire la première ouverture sur `http://192.168.1.5:8090`, la création du compte admin, la case de mémorisation, la révocation d’appareil, et la procédure de récupération de session sans toucher à la base média.

- [ ] **Étape 4 : construire l’image Docker localement si le daemon est disponible.**

Run: `docker compose build backstage`

- [ ] **Étape 5 : vérifier les tests et les builds avant déploiement.**

Run: `pytest -q`

Run: `npm --prefix proto-ui run lint`

Run: `npm --prefix proto-ui run build`

- [ ] **Étape 6 : commit documentation et migration.**

```bash
git add README.md docs/backstage-authentication.md tests/test_auth_migration.py
git commit -m "docs: document Backstage authentication setup"
```

- [ ] **Étape 7 : pousser la branche `agent/backstage-docker-deployment`, puis dans Portainer sélectionner la branche et cliquer sur `Pull and redeploy`.** Vérifier que `backstage-backstage-1` est `running`, que `/health` répond `{"status":"ok"}`, que le setup apparaît, puis que les films importés sont toujours présents après création de l’admin.

## Vérification finale

- [ ] `pytest -q` passe sans régression.
- [ ] `npm --prefix proto-ui run lint` passe.
- [ ] `npm --prefix proto-ui run build` passe.
- [ ] Une base fraîche demande la création du premier admin.
- [ ] Une seconde tentative de setup échoue.
- [ ] Un login normal et un login mémorisé fonctionnent.
- [ ] Un appareil révoqué ne peut plus utiliser l’API.
- [ ] Un utilisateur ne peut pas appeler une action admin.
- [ ] Le nombre de médias et d’épisodes reste inchangé après migration.
- [ ] Le déploiement Portainer conserve `/srv/data/backstage/backstage.db`.
