# Audit technique Backstage — 6 août 2026

> **Addendum du 6 août — contexte d'hébergement confirmé par le développeur**
> Serveur domestique, Ubuntu + Docker/Portainer. Voir la **section 0** ci-dessous : requalification des sévérités de l'axe sécurité et deux constats nouveaux (`BACKSTAGE_PUBLIC_URL` absent, identifiants V1 dormants dans `.env`).

---

## 0. Requalification après confirmation du contexte d'hébergement

**Hypothèse retenue** : accès depuis le réseau local uniquement (à confirmer, voir 0.3).

### 0.1 Sévérités revues à la baisse

Le modèle de menace n'est plus « Internet » mais « les appareils du réseau domestique » : téléphones des invités, télévision connectée, objets connectés, tout appareil compromis sur le LAN. C'est un périmètre bien plus réduit, mais **pas nul** — un LAN domestique n'est pas un environnement de confiance.

| Réf. | Constat | Avant | Après | Justification |
|---|---|---|---|---|
| S2a | Cookie sans `Secure` | Élevée | **Faible** | Sans TLS il n'y a de toute façon rien à protéger ; le jour où un reverse-proxy TLS est ajouté, ça redevient **Élevée**. À traiter *en même temps* que le TLS, pas avant. |
| S3 | Pas de limitation sur `/login` | Élevée | **Moyenne** | Le brute-force depuis Internet disparaît. **Le déni de service reste entier** : `authenticate` est synchrone dans une coroutine, donc n'importe quel appareil du LAN peut figer le serveur en boucle. C'est ce volet-là qui justifie encore la correction. |
| S5 | Pas de limitation sur `/forgot-password` | Élevée | **Moyenne** | Plus de mail-bombing externe. Restent le gel du serveur 1-3 s par appel (P6) et l'épuisement du quota Gmail. |
| S4 | Énumération de comptes par timing | Moyenne | **Faible** | Énumérer 2-4 comptes connus depuis le LAN n'apporte rien à un attaquant. |
| S16 | Conteneur en root | Faible | **Faible** | Inchangé. |

**Ce qui ne change pas** : S8 (catalogue modifiable par tout compte), S9 (épisodes globaux), S14 (clés étrangères inactives), S18 (aucune journalisation). Ces quatre points concernent les utilisateurs **légitimes** du foyer et l'intégrité des données — l'exposition réseau n'y change rien.

**Ce qui monte en priorité relative** : R1 (sauvegardes sur le même volume). Sur un serveur domestique sans redondance ni supervision matérielle, la panne de SSD est le scénario de perte le plus probable — plus que n'importe quelle attaque.

### 0.2 Deux constats nouveaux

#### N1. `BACKSTAGE_PUBLIC_URL` n'est défini nulle part dans le dépôt
**[V]** Absent du `.env` local. **[V]** Présent dans `docker-compose.yml`, mais avec le repli `${BACKSTAGE_PUBLIC_URL:-http://localhost:8090}`.

Si la variable n'est pas définie côté Portainer, `forgot_password` (`auth_api.py:211-213`) construit le lien de réinitialisation ainsi :

```
http://localhost:8090/reset-password?token=…
```

**Ce lien est inutilisable depuis n'importe quel appareil autre que le serveur lui-même.** La récupération de mot de passe par e-mail serait donc cassée en production, sans aucune erreur visible : l'API répond 202, le mail part, et le lien ne mène nulle part.

Aggravant : `SMTP_USERNAME`, `SMTP_PASSWORD` et `SMTP_FROM` sont eux aussi absents du `.env` local. Si c'est également le cas dans Portainer, `EmailSender` lève `RuntimeError("SMTP non configuré")`, l'exception est **attrapée et seulement journalisée** (`auth_api.py:216-217`), et l'utilisateur reçoit malgré tout *« Si un compte correspond, un e-mail vient d'être envoyé »*. Aucun signal d'échec.

> Sévérité **Élevée** — Effort **S**
> **Vérification** : dans Portainer, stack Backstage → Environment variables → contrôler `BACKSTAGE_PUBLIC_URL` et les trois `SMTP_*`.
> **Correction** : définir `BACKSTAGE_PUBLIC_URL` sur l'URL réellement utilisée depuis les appareils du foyer (ex. `http://192.168.x.x:8090`), et exposer l'état de la configuration SMTP dans le centre d'administration plutôt que de la découvrir dans les logs.

#### N2. Identifiants V1 dormants dans `.env`
**[V]** Le `.env` local contient encore `NOTION_TOKEN`, `DATABASE_ID`, `GOOGLE_CALENDAR_CREDENTIALS` et `GOOGLE_CALENDAR_ID` — **renseignés**, alors qu'aucun code V2 ne les lit (`config.py` ne les référence pas, et `tests/test_config.py` assert explicitement leur absence).

Ce sont des identifiants **actifs** vers une base Notion et un agenda Google, conservés dans un fichier en clair pour un usage qui n'existe plus. Le fichier n'est ni commité ni copié dans l'image — le risque n'est donc pas l'exposition, c'est la **persistance de droits inutiles** : un jeton Notion oublié reste valide des années et donne accès à la base d'origine.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : révoquer le jeton d'intégration Notion et les identifiants Google Calendar côté fournisseur (les supprimer du fichier ne les invalide pas), puis nettoyer le `.env`. À faire une fois, définitivement.

### 0.3 Exposition réseau — confirmée

**[Confirmé par le développeur]** Accès distant **via VPN** (Tailscale / WireGuard), aucune exposition directe sur Internet.

C'est la configuration recommandée : du point de vue sécurité, elle équivaut au LAN strict, avec l'accès hors domicile en plus. **La requalification 0.1 s'applique donc intégralement**, et l'axe sécurité cesse d'être un sujet prioritaire — la surface d'attaque se réduit aux appareils déjà authentifiés sur le tailnet.

Trois conséquences pratiques :

1. **N1 devient plus contraignant, pas moins.** Le lien de réinitialisation doit être joignable **depuis le VPN**, donc ni `localhost:8090` (défaut actuel) ni forcément l'IP LAN `192.168.x.x` — qui ne résout pas depuis un téléphone en 4G connecté au tailnet. La bonne valeur est le nom MagicDNS ou l'IP du tailnet, par exemple :
   ```
   BACKSTAGE_PUBLIC_URL=http://prodesk.<votre-tailnet>.ts.net:8090
   ```
2. **La limitation de débit (S3, S5) descend en priorité basse** en tant que mesure de sécurité. Elle reste justifiée pour un motif de **robustesse** : `authenticate` et l'envoi SMTP sont synchrones dans la boucle d'événements (P6), donc un client qui insiste fige le serveur pour tout le foyer. Corriger P6 (`asyncio.to_thread`) traite ce volet et rend la limitation de débit optionnelle.
3. **Le cookie `Secure` (S2a) reste sans objet tant qu'il n'y a pas de TLS** — mais Tailscale sait délivrer des certificats valides (`tailscale serve`). Si cette option est activée un jour, passer `BACKSTAGE_COOKIE_SECURE=1` dans le même mouvement. Pas avant : le cookie serait alors rejeté sur HTTP et plus personne ne pourrait se connecter.

**Conclusion de l'axe sécurité** : plus aucun point critique. Les quatre constats qui restent à traiter (S8, S9, S14, S18) relèvent de l'**intégrité des données entre utilisateurs légitimes**, pas de la protection contre un attaquant externe.


**Périmètre audité** : code source complet (`backend/`, `proto-ui/src/`, `tests/`, `main.py`), configuration de déploiement (`Dockerfile`, `docker-compose.yml`, `.gitignore`, `.dockerignore`), historique git (branches locales et distantes), base de données réelle (`backstage.db`), et exécution de la suite `pytest`.

**Convention de marquage**
- **[V]** fait vérifié dans le code, la base, git ou l'exécution des tests
- **[D]** déduction probable à partir d'éléments vérifiés
- **[?]** point nécessitant une confirmation du développeur

---

## 1. Résumé exécutif

Le code applicatif est de bonne qualité : aucune injection SQL, hachage de mots de passe conforme (scrypt), autorisations correctement scopées sur les routes sensibles, et une suite de 186 tests dont 178 passent — la couverture de l'authentification, des quotas de location et des règles de conservation est réelle, pas cosmétique.

Le problème n'est pas le code, c'est **la chaîne qui le mène en production**. La branche déployée est 17 commits en retard sur `main` : tout le mode « Choisir un film » n'est pas en ligne alors que la documentation le déclare livré. Le `docker-compose.yml` n'injecte pas `GEMINI_API_KEY` ni les variables `RECOMMENDATION_*` ni `RADARR_DEFAULT_*` : même à jour, ces fonctionnalités resteraient silencieusement désactivées. Les logs du conteneur montrent une boucle de crash sur un module qui existait en local mais pas dans le dépôt. Trois symptômes, une seule cause : rien ne vérifie qu'une image construite depuis un checkout propre démarre.

Le second risque est la sauvegarde : `BACKUP_DIR` et `DB_PATH` pointent vers le même volume. Une panne de SSD emporte la base et ses sauvegardes ensemble. La base fait 1,2 Mo — un export chiffré quotidien hors-site coûte une heure de travail.

Côté performance, trois points structurels : `GET /medias` fait 253 requêtes SQLite pour 252 films, la base est en `journal_mode=delete` (pas WAL), et le scheduler relance une synchronisation complète toutes les 60 secondes (~750 requêtes HTTP/minute vers Radarr et Jellyfin). Enfin, le mode « Choisir un film » puise dans un pool de 20 films populaires TMDB fixe : la répétition ressentie est structurelle, pas algorithmique.

---

## 2. Constats par axe

### Axe 1 — Sécurité

#### S1. Hachage de mot de passe — conforme, aucune action
**[V]** `backend/core/auth.py:28-57`. scrypt N=2¹⁴, r=8, p=1, sel aléatoire de 16 octets, paramètres encodés dans le hash (donc migrables), comparaison à temps constant via `hmac.compare_digest`. C'est exactement ce qu'il faut. **Rien à changer.**

#### S2. Sessions et cookie « appareil mémorisé »
**[V]** Jetons `secrets.token_urlsafe(32)` (256 bits), stockés en SHA-256 en base — un vol de la base ne donne pas les jetons actifs. Expiration 24 h / 30 jours, révocation individuelle et globale, purge automatique. Le changement et la réinitialisation de mot de passe révoquent bien les autres sessions.

| # | Constat | Sévérité | Effort |
|---|---|---|---|
| S2a | **[V]** `_cookie_secure()` lit `BACKSTAGE_COOKIE_SECURE`, absent de `docker-compose.yml` → le cookie de session n'a **jamais** l'attribut `Secure` en production. Dès qu'un reverse-proxy TLS est placé devant, le cookie 30 jours peut fuiter sur une connexion HTTP. | Élevée | S |
| S2b | **[V]** Pas de rotation du jeton après authentification. Impact limité (le jeton est généré à la connexion, pas repris d'une session anonyme). | Faible | S |
| S2c | **[V]** Pas de jeton CSRF, mais `SameSite=Lax` + **aucune route mutante en GET** (27 routes GET recensées, toutes en lecture). La protection est suffisante. **Rien à faire.** | — | — |

**Recommandation S2a** : ajouter `BACKSTAGE_COOKIE_SECURE: "${BACKSTAGE_COOKIE_SECURE:-0}"` au compose et le passer à `1` le jour où du TLS est en place.

#### S3. Absence de limitation de débit sur `/login` — et blocage de la boucle d'événements
**[V]** `backend/auth_api.py:167-182`. Aucun compteur de tentatives, aucun verrouillage. Pire : `store.authenticate()` est **synchrone, appelé directement depuis une coroutine `async`**, sans `asyncio.to_thread`. Chaque tentative gèle donc tout le serveur pendant la durée du scrypt (~50-80 ms). Un brute-force n'est pas seulement une attaque sur les mots de passe, c'est un déni de service sur toute l'application.

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : un dictionnaire en mémoire `{email: (compteur, dernier_essai)}` avec blocage progressif (3 échecs → 5 s, 6 → 60 s) suffit pour un usage domestique ; pas besoin de Redis. Et déplacer `authenticate` dans `asyncio.to_thread`.

#### S4. Oracle d'énumération de comptes par mesure de temps
**[V]** `auth.py:201-205` : si l'e-mail est inconnu, `verify_password` n'est jamais appelé — la réponse arrive en ~1 ms. Si le compte existe, le scrypt s'exécute — ~60 ms. L'écart est mesurable à distance et permet d'énumérer les comptes du foyer.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : lorsque la ligne est absente, appeler quand même `verify_password(password, HASH_FACTICE)` avant de lever l'erreur.

#### S5. `/forgot-password` : pas de limitation, envoi SMTP bloquant
**[V]** `auth_api.py:203-218` + `backend/core/email.py:30-36`. La réponse est correctement générique (pas d'énumération par le corps de réponse), mais :
- aucune limitation de débit → un tiers peut faire envoyer des dizaines de mails à une adresse du foyer et **épuiser le quota d'envoi Gmail** (500/jour), ce qui casserait la récupération de mot de passe au moment où on en a besoin ;
- `smtplib` est **entièrement synchrone** dans une coroutine `async` → chaque appel gèle le serveur 1 à 3 secondes ;
- cette différence de durée recrée un oracle d'énumération (compte existant = lent, inexistant = instantané).

> Sévérité **Élevée** — Effort **S à M**
> **Recommandation** : limiter à 3 demandes / heure / adresse, et exécuter l'envoi via `asyncio.to_thread` (ou en tâche de fond) pour que la réponse soit immédiate dans les deux cas.

#### S6. Jetons de réinitialisation — conforme
**[V]** 32 octets aléatoires, stockés en SHA-256, expiration 1 heure, usage unique (`used_at`), révocation de toutes les sessions à l'utilisation, purge des jetons expirés. **Rien à changer.**

#### S7. IDOR — absent
**[V]** Vérifié route par route. `/rentals/{id}/keep`, `/notifications/{id}/read`, `/devices/{id}`, `/recommendations/sessions/{id}/*` filtrent tous sur `backstage_user_id` en base, pas seulement en lecture. `/medias/{id}` est un catalogue partagé par conception. **Aucune fuite inter-utilisateurs.**

#### S8. Trou d'autorisation : le catalogue commun est modifiable par tout compte
**[V]** Le routeur `/api` applique `Depends(get_current_user)` globalement, mais les routes suivantes **ne vérifient pas le rôle** :
- `PATCH /api/medias/{id}` (`api.py:1007`) — titre, note, avis, genres, casting, affiche du catalogue **partagé**
- `POST /api/medias/{id}/relink_tmdb` (`api.py:361`) — ré-associer un film à un autre identifiant TMDB
- `POST /api/medias/from_tmdb`, `POST /api/series/from_tmdb`, `POST /api/series/{id}/refresh`
- `GET /api/media-server/options` (`api.py:1325`) — expose les chemins racine et profils de qualité Radarr/Sonarr à tout compte

N'importe quel membre du foyer peut donc réécrire ou casser le catalogue commun.

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : `dependencies=[Depends(require_admin)]` sur ces cinq routes. Les utilisateurs gardent `PATCH /medias/{id}/personal`, qui est la bonne porte.

#### S9. `PATCH /api/episodes/{id}` viole la séparation catalogue / état utilisateur
**[V]** `api.py:851` → `store.set_episode_watched()` écrit `episode.watched` **globalement**, puis `_recalculate_series_status()` (`store.py:781`) réécrit `media.status`, également partagé. Concrètement : quand un membre du foyer marque un épisode vu, il est vu **pour tout le monde**, et le statut de la série change pour tout le monde.

C'est la seule violation structurelle de la règle « un contenu n'existe qu'une fois, chaque utilisateur a sa propre relation avec lui ». Elle bloque directement le chantier « séries par saison/épisode ».

> Sévérité **Élevée** — Effort **M**
> **Recommandation** : table `user_episode_state (backstage_user_id, episode_id, watched, updated_at)`, et transformer `series_progress` en projection par utilisateur. `episode` ne garde que les métadonnées TMDB.

#### S10. La lecture n'est liée à aucune location
**[V]** `GET /medias/{id}/playback/manifest` (`api.py:1081`) ne vérifie ni location active, ni quota, ni propriété. Tout compte authentifié peut lire tout contenu présent sur Jellyfin.

C'est peut-être le comportement voulu en foyer — mais il faut en être conscient : **le quota de 5 locations est un outil de gestion de stockage, pas un contrôle d'accès**. Et c'est un prérequis bloquant si un contrôle parental est envisagé un jour.

> Sévérité **Moyenne** (à requalifier selon la réponse à [?6]) — Effort **S**

#### S11. SSRF — absent
**[V]** Toutes les URL sortantes sont construites à partir de la configuration (`Config.RADARR_URL`, etc.), jamais d'une entrée utilisateur. Le seul segment contrôlé par l'utilisateur est `resource_path` de `/playback/resource/`, et il est validé contre les chemins absolus et `..` (`jellyfin.py:163-165`), puis ré-encodé. Le paramètre `api_key` est filtré à l'aller comme au retour (`api.py:68`, `api.py:1109`). **Rien à corriger.**

#### S12. Injection SQL — absente
**[V]** Revue exhaustive de `store.py` et `auth.py`. Une seule requête utilise une f-string (`store.py:664`), et elle interpole `_COLUMNS`, une constante du module. Toutes les clauses `SET`/`INSERT` dynamiques sont construites à partir de clés préalablement filtrées par des listes blanches (`allowed = {...}`). Toutes les valeurs sont paramétrées. **Rien à corriger.**

#### S13. Concurrence SQLite
**[V]** La base réelle est en `journal_mode = delete` (vérifié par `PRAGMA`). Avec un écrivain permanent (le scheduler) et un `UPDATE auth_sessions SET last_seen_at` **à chaque requête authentifiée**, les lecteurs sont bloqués pendant chaque écriture. Aucun `timeout` n'est passé à `sqlite3.connect()` → le défaut de 5 s s'applique, puis `database is locked`.

> Sévérité **Moyenne** — Effort **S** — voir P2.

#### S14. Clés étrangères non appliquées
**[V]** `PRAGMA foreign_keys` = 0 sur la base réelle. Toutes les clauses `ON DELETE CASCADE` déclarées dans les schémas sont **décoratives**. `_delete_sync` (`store.py:706`) supprime `episode` et `media` à la main, mais **pas** `user_media_state`, `media_rentals`, `media_availability` ni `playback_progress` → orphelins garantis à chaque suppression de média.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : `PRAGMA foreign_keys=ON` dans `init_schema` — mais **d'abord sur une copie**, car la base actuelle peut déjà contenir des orphelins qui feraient échouer des écritures.

#### S15. Gestion des secrets — conforme
**[V]** `git ls-files` ne remonte que `.env.example`, sans valeur. `.env`, `backstage.db`, `credentials.json` sont ignorés, et `.env` est également exclu de l'image via `.dockerignore`. **La règle énoncée est effectivement respectée en pratique.**

#### S16. Conteneur exécuté en root
**[V]** Aucune directive `USER` dans le `Dockerfile`.
> Sévérité **Faible** — Effort **S** — `RUN useradd -r backstage && chown -R backstage /data` + `USER backstage`.

#### S17. `/health/backup` public
**[V]** Renvoie `status`, `reason`, `age_hours` et, en 503, le détail complet. Fuite mineure (existence et fraîcheur des sauvegardes) — les chemins de fichiers restent bien réservés à `/admin/system/backup`. Nécessaire pour Uptime Kuma. **Acceptable**, sévérité **Faible**.

#### S18. Aucune journalisation de sécurité
**[V]** Aucun log sur : connexion réussie, échec d'authentification, création/suppression/modification d'utilisateur, décision de conservation, révocation de session. En cas d'incident, il n'y a rien à analyser.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : un `logger.info` structuré sur ces six événements (horodatage, identifiant utilisateur, adresse IP, résultat). Pour un foyer, c'est suffisant — pas besoin d'un SIEM.

#### S19. 2FA
Hors sujet pour ce contexte. Le gain marginal est nul comparé aux trois mesures qui comptent réellement : limitation de débit (S3), cookie `Secure` (S2a), et **ne pas exposer Backstage sur Internet sans VPN** ([?3]).

---

### Axe 2 — Performance et efficacité

#### P1. Requête N+1 sur l'écran d'accueil
**[V]** `api.py:405-411` : `list_medias` charge tous les médias, puis appelle `_media_for_user` pour chacun, qui exécute `store.get_user_media_state(user, media.id)` — soit **une requête SQLite par film**, chacune dans un `asyncio.to_thread` distinct qui ouvre et ferme sa propre connexion.

Avec la base actuelle (**252 médias, vérifié**) : 253 requêtes et 253 allers-retours vers le pool de threads à chaque affichage du catalogue. Et le front rappelle `fetchMedias()` en entier après chaque modification (`refreshCanonicalMedia`, `handleRelinkMovie`).

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : `store.list_user_media_states(user_id)` existe déjà et fait le travail en **une** requête. Charger le dictionnaire une fois, puis passer l'état à `_media_for_user`.

#### P2. Base en `journal_mode=delete`
**[V]** Vérifié sur `backstage.db`. Passer en WAL supprime le blocage lecteurs/écrivain, ce qui est exactement le profil de charge ici (scheduler qui écrit en continu + requêtes de lecture).

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;` dans `init_schema`, et `sqlite3.connect(path, timeout=15)` partout. ⚠ WAL crée des fichiers `-wal`/`-shm` : vérifier qu'ils sont bien dans le volume `/data` et couverts par la sauvegarde (`sqlite3.backup()` les gère correctement, contrairement à une copie de fichier).

#### P3. Aucun index sur la table `media`
**[V]** `PRAGMA` : seul `sqlite_autoindex_media_1` (la clé primaire) existe. Or `_resolve_playback_item_sync` (`store.py:1216`) exécute `SELECT id FROM media WHERE tmdb_id = ? AND type = ?` **pour chaque élément de progression synchronisé**, et `confirm_recommendation` fait un `fetch_all()` complet pour retrouver un film par `tmdb_id`.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : `CREATE INDEX idx_media_tmdb_type ON media(tmdb_id, type)` et `CREATE INDEX idx_media_type_title ON media(type, title)`.

#### P4. Le scheduler resynchronise tout, toutes les 60 secondes
**[V]** `scheduler.py:20-51` avec `MEDIA_SYNC_INTERVAL_SEC=60` par défaut (et dans le compose). `sync_all()` (`media_server.py:205`) itère sur les 252 médias et, **pour chacun**, appelle :
- `arr.list_library()` — la bibliothèque Radarr/Sonarr **entière**
- `arr.list_queue()` — la file entière
- `jellyfin.find_by_tmdb()` — qui **pagine toute la bibliothèque Jellyfin** par lots de 1000 (`jellyfin.py:108-137`)

Soit de l'ordre de **750 requêtes HTTP par minute** vers des services qui tournent sur le même i5-8500T, sans aucune mise en cache entre les itérations.

> Sévérité **Critique** (pour la santé de la machine) — Effort **M**
> **Recommandation** : charger `list_library()`, `list_queue()` et l'index Jellyfin **une fois par cycle**, les passer à `sync_media()`, et porter l'intervalle à 300 s. Le gain est d'un facteur ~250.

#### P5. Boucle imbriquée dans les notifications automatiques
**[V]** `scheduler.py:86-98` : `for availability in list_availabilities(): for item in await store.list_admin_rentals():` — la seconde requête est **relancée à chaque itération** de la première.
> Sévérité **Moyenne** — Effort **S** — sortir `list_admin_rentals()` de la boucle.

#### P6. Appels bloquants dans la boucle d'événements
**[V]** Quatre familles d'appels synchrones exécutés directement dans des coroutines `async`, sans `asyncio.to_thread` :

| Appel | Coût | Fréquence |
|---|---|---|
| `gateway.plan_questions` / `select_final` (`api.py:640,741`) — **SDK Gemini synchrone** | 1 à 3 s | 2× par session de recommandation |
| `EmailSender.send_password_reset` (`auth_api.py:215`) — smtplib | 1 à 3 s | à chaque mot de passe oublié |
| `store.authenticate` (`auth_api.py:175`) — scrypt | ~60 ms | à chaque connexion |
| `store.user_from_token` (`auth_api.py:115`) + `auth_store.list_users()` | ~2 ms | **à chaque requête API** |

Pendant chaque appel Gemini, **tout le serveur est figé** : aucun autre membre du foyer ne peut charger une page ou lancer une lecture.

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : envelopper les quatre dans `asyncio.to_thread`. C'est un changement d'une ligne par site d'appel.

#### P7. Profil de goût chargé deux fois par réponse
**[V]** `api.py:732-734` : `_recommendation_pool()` charge médias + états + événements + progression (5 requêtes), puis `_recommendation_profile()` **refait exactement les mêmes 5 requêtes** ligne suivante.
> Sévérité **Moyenne** — Effort **S** — faire renvoyer le profil par `_recommendation_pool`.

#### P8. Aucun cache TMDB
**[V]** `backend/core/tmdb.py` : chaque `get_movie_details`, `search_*` et `discover_movies` part sur le réseau. Aucune couche de cache. Le fichier `cache.json` à la racine est un vestige de la V1 : **aucune référence dans le code V2** (vérifié).
> Sévérité **Moyenne** — Effort **M**
> **Recommandation** : un cache mémoire à durée de vie (`get_movie_details` : 7 jours ; `discover_movies` : 6 h) suffit — pas besoin de persistance. Ça divise aussi par beaucoup la consommation du quota TMDB.

#### P9. Bundle frontend monolithique
**[V]** `proto-ui/dist/assets/` : **un seul fichier JavaScript de 816 Ko** + 62 Ko de CSS. Aucun découpage. `hls.js` est importé statiquement en tête de `BackstagePrototype.jsx` alors qu'il ne sert qu'au lecteur vidéo.
> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : `const Hls = (await import('hls.js')).default` dans l'effet du lecteur, et `React.lazy` sur `AdminCenter` et `AccountPanel`. Gain estimé : 40 à 50 % du bundle initial.

#### P10. `BackstagePrototype.jsx` : 2024 lignes, 45 états, zéro mémoïsation
**[V]** Comptage : 45 `useState`, 9 `useEffect`, 9 `useRef`, et **0 occurrence de `useMemo`, `useCallback` ou `React.memo`**. Chaque frappe dans le champ de recherche re-rend la grille de 252 affiches et recrée l'intégralité des gestionnaires d'événements.
> Sévérité **Moyenne** — Effort **M** — à traiter en même temps que l'extraction de la fiche film (voir U5).

#### P11. Rechargement complet pour un seul élément
**[V]** `refreshCanonicalMedia` (`BackstagePrototype.jsx:456`) appelle `fetchMedias()` — les 252 médias, avec le N+1 côté serveur — pour rafraîchir **un** film.
> Sévérité **Moyenne** — Effort **S** — utiliser `GET /medias/{id}` qui existe déjà.

#### P12. Segments HLS entièrement bufferisés
**[V]** `api.py:1117` : `Response(content=response.content, ...)` — chaque segment vidéo est chargé intégralement en mémoire avant d'être renvoyé, au lieu d'être relayé en flux.
> Sévérité **Moyenne** — Effort **M** — `StreamingResponse` + `client.stream()`.

#### P13. `/playback/sync` redondant
**[V]** Déclenché au montage du composant et à chaque changement d'utilisateur côté front, **et** pour tous les utilisateurs toutes les 60 s par le scheduler.
> Sévérité **Faible** — Effort **S**

---

### Axe 3 — Architecture et dette technique

#### A1. La branche déployée est 17 commits en retard sur `main`
**[V]** `git log origin/agent/backstage-docker-deployment..origin/main` = **17 commits**. La branche de déploiement s'arrête à `e556fa2`. Ne sont **pas en production** :

- tout le mode « Choisir un film » (questions adaptatives, quotas quotidiens, mémoire anti-répétition)
- la passerelle Gemini et le suivi de consommation (`ai_usage`)
- la confirmation de recommandation avec acquisition automatique

Or `BACKSTAGE_OVERVIEW.md` §6 liste ces fonctionnalités comme **livrées au 06/08/2026**. L'écart entre la documentation et la production est total sur ce périmètre.

> Sévérité **Critique** — Effort **S**
> **Recommandation** : fusionner `main` dans la branche de déploiement (ou faire pointer Portainer sur `main`), puis ajouter dans `BACKSTAGE_OVERVIEW.md` une ligne « déployé : branche X, commit Y, date Z » pour rendre cet écart visible en permanence.

#### A2. Variables d'environnement absentes du `docker-compose.yml`
**[V]** Comparaison ligne à ligne entre `backend/config.py` et le bloc `environment:` du compose. Manquent :

| Variable | Conséquence de l'absence |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_MAX_OUTPUT_TOKENS` | **La passerelle Gemini est désactivée en silence** (`enabled` renvoie `False`), même une fois A1 corrigé |
| `RADARR_DEFAULT_QUALITY_PROFILE_NAME`, `RADARR_DEFAULT_ROOT_FOLDER` | `acquisition_defaults` cherche un profil nommé `"1080 FR - max 10go"` en dur ; s'il n'existe pas, l'acquisition automatique lève `ValueError` |
| `RECOMMENDATION_DAILY_LIMIT`, `RECOMMENDATION_TIMEZONE`, `RECOMMENDATION_RECENT_DAYS` | valeurs par défaut imposées, non pilotables |
| `BACKSTAGE_COOKIE_SECURE` | voir S2a |
| `TMDB_API_KEY` | présent ✔ |

> Sévérité **Critique** — Effort **S** (ajouter 8 lignes au compose)

#### A3. Le conteneur a été en boucle de crash
**[V]** `_backstage-backstage-1_logs.txt` contient **17 traces identiques** de `ModuleNotFoundError: No module named 'backend.core.tmdb_relink'` — le conteneur redémarrait en boucle sous `restart: unless-stopped`. La cause est identifiée par git : le module existait en local mais n'était pas commité, il a été ajouté par `d5430109 "fix: include TMDB relink module in image"` le 6 août à 10h04.

L'incident est résolu, mais il révèle le problème de fond : **rien ne vérifie qu'une image construite depuis un checkout propre du dépôt démarre effectivement.** A1, A2 et A3 sont trois manifestations de la même absence de vérification.

> Sévérité **Élevée** — Effort **M**
> **Recommandation** : un workflow GitHub Actions sur push de `main` qui (1) lance `pytest`, (2) construit l'image, (3) démarre le conteneur avec des variables minimales et vérifie que `/health` répond. Une trentaine de lignes de YAML.

#### A4. `ZoneInfo("Europe/Paris")` sans dépendance `tzdata`
**[V]** L'exécution de la suite de tests donne **178 passés / 8 échoués**, et les 8 échecs sont tous `ZoneInfoNotFoundError: 'No time zone found with key Europe/Paris'` (tests de recommandation). `tzdata` n'est pas dans `requirements.txt`.

**[D]** En local (Windows) c'est attendu. En production, si `/usr/share/zoneinfo` est absent de l'image `python:3.11-slim`, alors `_recommendation_day_start` (`api.py:98-101`) lève une exception et **toute session de recommandation d'un utilisateur non-admin renvoie 500**. Les administrateurs ne sont pas affectés : `_recommendation_quota` retourne avant d'atteindre ce code (`api.py:85-86`). Ce qui expliquerait qu'un développeur travaillant sous son compte admin n'ait jamais vu le problème.

**[?]** À vérifier en une commande sur le serveur :
```bash
docker exec backstage-backstage-1 python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Europe/Paris'))"
```

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : ajouter `tzdata` à `requirements.txt` quel que soit le résultat du test. C'est une ligne, et ça supprime la dépendance à l'image de base.

#### A5. NiceGUI n'est plus qu'un lanceur
**[V]** `main.py` n'utilise de NiceGUI que `app` (l'application FastAPI sous-jacente), `@ui.page` pour servir deux fichiers `index.html`, et `ui.run()`. Aucun composant d'interface. En échange, le projet embarque tout l'arbre de dépendances de NiceGUI 3.6 (Vue/Quasar, socket.io, aiohttp…) et expose un serveur socket.io inutilisé.

> Sévérité **Moyenne** — Effort **M**
> **Recommandation** : remplacer par `FastAPI()` + `uvicorn.run()` + deux `FileResponse`. `main.py` passerait sous 40 lignes et le `requirements.txt` de 5 à 4 lignes avec beaucoup moins de transitives. **Chantier propre mais non urgent** — à faire quand rien de plus important n'est en cours.

#### A6. Deux centres d'administration coexistent
**[V]** Deux composants se partagent les fonctions d'administration :

| | `AccountPanel.jsx` (446 l.) | `AdminCenter.jsx` (165 l.) |
|---|---|---|
| Conservation | ✅ accepter / refuser / prolonger | ❌ **affichage seul, aucun bouton** |
| Sauvegardes | ✅ créer / vérifier / statut | ❌ absent |
| Simulation de nettoyage | ✅ | ❌ absent |
| Utilisateurs | ✅ créer / modifier / lier Jellyfin | ❌ liste seule |
| Notifications | ✅ | ❌ absent |
| Sections Phase 14 | ❌ | ✅ (7 onglets) |

`AdminCenter` est la coquille Phase 14 : la structure de navigation est là, les actions n'ont pas été portées. Tant que la migration n'est pas finie, l'administrateur doit connaître deux chemins différents selon l'action.

> Sévérité **Moyenne** — Effort **M**

#### A7. Code mort et erreur latente
**[V]**
- `backend/core/stats.py` : **importé nulle part** dans `backend/`, `main.py` ou `tests/`.
- `recommendations.score_candidate` : doublon obsolète de `score_recommendation_candidate`, appelé par personne.
- `api._question_from_candidates` : jamais appelé.
- `api._adaptive_question_from_candidates` : jamais appelé — **et lèverait un `NameError`** s'il l'était, car `build_adaptive_question` n'est pas dans la liste d'imports de `api.py` (`api.py:29-32`).
- `backend/core/__pycache__/` contient des `.pyc` de modules supprimés (`omdb`, `processor`).

> Sévérité **Faible** — Effort **S**

#### A8. `frontend/` et `legacy/` — risque réel : nul
**[V]**
- `frontend/` : **0 fichier suivi par git** (`git ls-files frontend/` est vide). Il ne contient que des `.pyc` orphelins, tous couverts par `.gitignore`. **Suppression locale sans le moindre risque** — le dossier n'existe déjà pas dans le dépôt ni dans l'image.
- `legacy/2026-07-cleanup/` : suivi par git (27 fichiers), mais exclu de l'image par `.dockerignore` et importé par aucun module V2.

> Sévérité **Faible** — Effort **S**
> **Recommandation** : `rm -rf frontend/` immédiatement. Pour `legacy/`, poser un tag git `v1-notion` puis supprimer le dossier — l'historique reste accessible.

#### A9. Migrations de schéma ad hoc, sans versionnement ni retour arrière
**[V]** `init_schema()` (`store.py:30-337` et `auth.py:64-127`) empile 14 séquences `PRAGMA table_info(...)` → `ALTER TABLE ... ADD COLUMN`. Ça fonctionne pour ajouter des colonnes, mais :
- `PRAGMA user_version` n'est **pas utilisé** : impossible de savoir dans quel état est une base
- aucune sauvegarde n'est prise **avant** migration (or `main.py:54-55` appelle `init_schema` au démarrage, donc avant que le scheduler n'ait pu créer une sauvegarde)
- impossible de renommer une colonne, de changer une contrainte, ou d'annuler
- une migration qui échoue à mi-parcours laisse la base dans un état intermédiaire non identifiable

> Sévérité **Moyenne** — Effort **M**
> **Recommandation** minimale et suffisante pour ce projet : (1) `PRAGMA user_version` incrémenté par migration, (2) chaque migration dans une fonction numérotée, (3) **appel de `create_backup()` avant toute migration au démarrage**. Pas besoin d'Alembic ici.

#### A10. `api.py` (1467 l.) et `store.py` (1485 l.)
**[V]** `api.py` mélange définitions de routes, ~350 lignes de logique de recommandation (`_recommendation_pool`, `_planned_question`, `_vary_question_plan`…) et sérialisation. `store.py` couvre 10 domaines fonctionnels dans une seule classe.
> Sévérité **Moyenne** — Effort **M**
> **Recommandation** : découper `api.py` en `api/medias.py`, `api/recommendations.py`, `api/rentals.py`, `api/admin.py`, `api/playback.py`. À faire **en profitant** du chantier A6/U5, pas comme refonte isolée.

#### A11. Couverture de tests — réellement bonne, avec trois angles morts
**[V]** 186 tests, 178 verts (les 8 échecs relèvent de A4, pas de régressions).

**Solidement couvert** : authentification (sessions 24h/30j, révocation ciblée et globale, changement et réinitialisation de mot de passe, isolation des rôles, migration du schéma, désactivation de compte), quotas de location (5 maximum, admin exclu, blocage sur espace disque et quota temporaire), décisions de conservation et notifications associées, **simulation de suppression sécurisée** (protections permanent / conservation en attente / lecture en cours / autre location active), sauvegardes (intégrité, purge, vérification), recommandations (quota quotidien avec bascule à minuit Europe/Paris, non-répétition, scoring, validation des identifiants renvoyés par Gemini).

**Non couvert** :
1. **Les rôles sur `PATCH /medias/{id}`, `relink_tmdb`, `from_tmdb`, `episodes/{id}`** — aucun test n'exerce ces routes avec un compte non-admin, ce qui explique que S8 et S9 soient passés inaperçus.
2. **`main.py`** — aucun test n'importe le module ni ne vérifie qu'il démarre. C'est exactement le trou par lequel A3 est passé.
3. **`scheduler._media_loop`** — `notify_automatic_events` et `backup_if_due` sont testés, la boucle elle-même ne l'est pas.
4. **L'intégrité référentielle après suppression** d'un média ou d'un utilisateur (S14).

> **Recommandation** : trois tests règlent 1 et 2 (`test_catalogue_routes_require_admin`, `test_main_module_imports`, `test_all_admin_routes_reject_regular_users` par introspection du routeur).

#### A12. Documentation — écart mesuré et plan de réconciliation
**[V]** Trois écarts constatés :
1. `README.md` décrit la V1 Notion (obsolète, déjà identifié).
2. `BACKSTAGE_OVERVIEW.md` §2 cite **OMDB** comme source de notes IMDb et de classification d'âge. **Aucun client OMDB n'existe dans le code V2** — il ne subsiste que dans `legacy/` et dans des `.pyc` orphelins. `tests/test_config.py` **assert explicitement l'absence d'OMDB** de la configuration.
3. `BACKSTAGE_OVERVIEW.md` §6 déclare le mode « Choisir un film » livré, alors qu'il n'est pas déployé (A1).

> **Plan concret** :
> - Réécrire `README.md` en ~40 lignes : quoi / stack / lancer en local / déployer / tester. Déplacer le récit V1 dans `legacy/2026-07-cleanup/README.md`.
> - Corriger §2 d'`OVERVIEW` : OMDB abandonné en V2 ([?7]).
> - Ajouter en tête d'`OVERVIEW` un bloc « **État de déploiement** : branche / commit / date », mis à jour à chaque redéploiement. C'est ce qui aurait rendu A1 visible.
> - Garder `BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md` comme roadmap (le futur) et `OVERVIEW` comme état (le présent) — la séparation actuelle est bonne, c'est la fraîcheur qui manque.

---

### Axe 4 — Fiabilité et résilience

#### R1. Les sauvegardes sont sur le même volume que la base
**[V]** `docker-compose.yml` : `DB_PATH: /data/backstage.db` et `BACKUP_DIR: /data/backups`, avec un unique bind-mount `${BACKSTAGE_DATA_DIR}:/data`. **La base et toutes ses sauvegardes sont sur le même système de fichiers, sur le même disque.**

Scénarios de perte totale, aujourd'hui : panne du SSD système, corruption du système de fichiers, suppression accidentelle du volume, erreur de manipulation Portainer sur le stack, chiffrement par rançongiciel. Dans les cinq cas, `BACKUP_RETENTION_DAYS=7` ne sert à rien.

Le mécanisme de sauvegarde lui-même est **correct** : `sqlite3.backup()` (copie cohérente, pas un `cp` sur une base ouverte), vérification d'intégrité après création, purge par ancienneté, endpoint de santé supervisé. C'est uniquement la **destination** qui est le problème.

> Sévérité **Critique** — Effort **S**
> **Mitigation immédiate, sans attendre le disque dédié** : la base fait **1,2 Mo**. Un cron hôte quotidien suffit :
> ```bash
> sqlite3 /srv/data/backstage/backstage.db ".backup /tmp/bs.db" \
>   && age -r <clé-publique> -o /tmp/bs.db.age /tmp/bs.db \
>   && rclone copy /tmp/bs.db.age remote:backstage/ \
>   && rm -f /tmp/bs.db /tmp/bs.db.age
> ```
> Destination indifférente (Drive, S3, Backblaze, ou même un `scp` vers un autre poste du foyer). Le point important est **hors du serveur**. Le disque dédié restera utile pour les médias, mais il ne résoudra pas ce risque-ci : un second disque dans la même machine ne protège ni d'une erreur humaine ni d'un sinistre.

#### R2. Les exceptions sont avalées en masse
**[V]** Cinq emplacements où une erreur de programmation devient indiscernable d'une panne réseau :

| Emplacement | Comportement |
|---|---|
| `media_server.py:146` | `except Exception:` → écrit « Synchronisation indisponible » et continue |
| `media_server.py:221` | `except Exception: continue` sur l'espace disque |
| `tmdb.py` (7 méthodes) | `except Exception:` → `logger.error` puis `[]` ou `None` |
| `BackstagePrototype.jsx:~356` | `.catch(() => {})` — **silence total** |
| `auth_api.py:216` | `logger.exception` sur l'échec d'envoi de mail, mais réponse 202 identique |

Conséquence : un quota TMDB épuisé, une clé API révoquée et un `TypeError` introduit par une régression produisent tous **le même symptôme visible** — « il ne se passe rien ».

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : dans `sync_media` et `activity`, remplacer `except Exception` par les exceptions attendues (`httpx.HTTPError`, `MediaServerError`, `ValueError`) et laisser remonter le reste, ou au minimum `logger.exception`. Distinguer dans `last_error` « service injoignable » de « erreur interne ».

#### R3. Comportement quand un service externe est injoignable
**[V]** Comportement réel, service par service :

| Service HS | Comportement | Verdict |
|---|---|---|
| Radarr / Sonarr | `MediaServerError` → HTTP 502 avec message clair ; la sync note `last_error` | ✅ correct |
| Jellyseerr | 502 avec le motif distant préservé (`seerr.py:25-33`) | ✅ correct |
| **Jellyfin** | `find_by_tmdb` renvoie `None` → l'état retombe de `available` à `imported` | ⚠ **effet de bord** : un contenu disponible **perd son bouton « Lire »** pendant la panne, et `mark_rentals_available` ne se déclenche pas — donc `expires_at` n'est jamais posé |
| Jellyfin (progression) | `/playback/sync` → 503, le front loggue en console **sans rien dire à l'utilisateur** | ⚠ silencieux |
| **Un seul service** | `AdminCenter` fait `Promise.all` de 6 appels (`AdminCenter.jsx:43-50`) → **une seule panne vide tout le centre d'administration** | ⚠ à corriger |

> Sévérité **Moyenne** — Effort **S**
> **Recommandations** : `Promise.allSettled` dans `AdminCenter` (afficher les sections disponibles et signaler celles qui ont échoué) ; ne pas rétrograder `available` → `imported` sur une simple absence de réponse Jellyfin (conserver l'état antérieur et poser `last_error`).

#### R4. Règle de suppression sécurisée — trois cas limites non couverts
**[V]** `_cleanup_preview_sync` (`store.py:1102-1142`) implémente correctement quatre des cinq protections annoncées : contenu permanent (`storage_policy='permanent'` ou statut `kept`), conservation en attente (`keep_requested`), **autre** location active sur le même média, et lecture en cours. La règle « la suppression suit la dernière location active » est bien respectée.

**Manquent** :

| # | Cas limite | Conséquence |
|---|---|---|
| a | Le test « lecture en cours » est `percent > 0 AND played = 0`, **sans filtre temporel**. Une progression abandonnée il y a 8 mois protège le fichier indéfiniment. | Faux positif permanent — le stockage ne se libère jamais |
| b | **La protection « pas d'incohérence de sync » de la spécification n'est pas implémentée** : ni `media_availability.last_error` ni la fraîcheur de `last_synced_at` ne sont consultés. | Un média dont la synchronisation échoue depuis 3 jours peut être proposé à la suppression sur la base d'un état périmé |
| c | `expires_at IS NULL` est traité comme « expiré ». Or une location `available` dont l'expiration n'a jamais été posée (cas R3 : Jellyfin indisponible au moment de la mise à disposition) tombe exactement dans ce cas. | Une location parfaitement valide apparaît en `would_delete` |

**Point rassurant [V]** : c'est une **simulation seule**. Aucune suppression réelle n'existe dans le code — `cleanup_preview` renvoie explicitement `"simulation": True` et le message « aucun fichier ne sera supprimé ». **Le risque est donc nul aujourd'hui.** Mais ces trois défauts doivent être corrigés **avant** de brancher l'exécution réelle, car ils produisent tous des faux positifs de suppression.

> Sévérité **Élevée** (conditionnée à l'implémentation de la suppression) — Effort **M**

#### R5. Quota Gemini et repli local
**[V]** Le plafond de 2 appels par session est **structurel** : `plan_questions` au démarrage (`api.py:640`) et `select_final` à la conclusion (`api.py:741`), sans boucle possible entre les deux. Le rejeu est bloqué par `advance_recommendation_session` (`store.py:498-507`), qui est un compare-and-swap sur `question_count` avec vérification `status='active'` — un double envoi renvoie 409. Les échecs partiels sont tracés dans `ai_usage` avec `status='error'` et le type d'exception, puis le repli local (`choose_from_top`) prend le relais. **La conception est saine.**

Deux réserves :
- l'appel est bloquant (P6) — c'est le vrai problème
- `_gemini_cost_estimate` (`api.py:112-117`) code en dur des tarifs qui deviendront faux sans que rien ne le signale

> Sévérité **Faible** — Effort **S**

#### R6. Supervision — ce qui est couvert et ce qui ne l'est pas
**[V]** Uptime Kuma sur `/health/backup` toutes les 5 min couvre deux choses : le processus répond, et une sauvegarde récente et intègre existe. C'est bien plus qu'un simple ping — c'est un bon choix de sonde.

**Angles morts** :

| Angle mort | Illustration |
|---|---|
| **Boucle de crash rapide** | A3 : `restart: unless-stopped` fait redémarrer le conteneur en quelques secondes ; Kuma, qui sonde toutes les 5 min, ne voit qu'un trou intermittent — voire rien du tout |
| Quota TMDB épuisé | Erreurs avalées (R2) → l'application « fonctionne », les recherches renvoient des listes vides |
| Échec de sync Radarr/Sonarr persistant | Écrit dans `last_error`, **jamais remonté** |
| Échec d'envoi SMTP | Loggué uniquement ; la réponse reste 202 |
| Erreurs 5xx applicatives | Aucune agrégation |
| Croissance de la base | Aucun suivi |

> Sévérité **Moyenne** — Effort **S**
> **Recommandations** : (1) exposer `/health/services` (admin) agrégeant les `last_error` et l'âge maximal de `last_synced_at`, et le surveiller ; (2) surveiller le **compteur de redémarrages** du conteneur (`docker inspect -f '{{.RestartCount}}'`) — c'est ce qui aurait détecté A3 en quelques minutes ; (3) faire échouer la sonde `/health/backup` si l'espace disque libre passe sous le seuil.

---

### Axe 5 — Expérience utilisateur

#### U1. Le catalogue n'a ni indicateur de chargement ni message d'erreur
**[V]** `BackstagePrototype.jsx:131-132` :
```javascript
const [, setLoading] = useState(true);
const [, setError] = useState(null);
```
Les deux valeurs sont **déstructurées en position vide** : elles sont écrites (`setError('Impossible de se connecter au serveur Python (port 8090).')`, ligne 474) mais **jamais lues nulle part**. Et `INITIAL_MOVIES = []` (ligne 44).

Conséquence concrète : si le backend est injoignable, ou pendant le temps de chargement, l'utilisateur voit **une bibliothèque vide, sans spinner ni message** — strictement indiscernable d'un catalogue réellement vide. Le message d'erreur existe, il est écrit dans une variable poubelle.

> Sévérité **Élevée** — Effort **S** — c'est probablement la correction avec le meilleur rapport gain/effort de tout l'audit côté interface.

#### U2. Les utilisateurs non-admin ne voient jamais les états de disponibilité
**[V]** `BackstagePrototype.jsx:~355` appelle `fetchMediaServerActivity()` **pour tous les utilisateurs**, sans condition de rôle. Or `GET /api/media-server/activity` est protégé par `require_admin` (`api.py:1350`). Pour un compte non-admin : HTTP 403, avalé par `.catch(() => {})` → `availabilityByMedia` reste **vide en permanence**.

Comme c'est cette table qui alimente `getMediaAction()` (« Lire », « Téléchargement en cours », « Demande en cours »…), **les utilisateurs normaux ne voient jamais l'état réel des contenus dans la bibliothèque**. Seul l'administrateur a l'expérience complète — ce qui expliquerait que le problème n'ait pas été remarqué.

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : exposer une variante non-admin de `activity` (les états de disponibilité ne sont pas des données sensibles), ou n'appeler l'endpoint que si `user.role === 'admin'` et alimenter la table depuis `GET /medias/{id}/availability`.

#### U3. L'expiration de session n'est pas gérée
**[V]** Seul `fetchCurrentUser` traite le 401 (`api.js:49-55`). Les 40 autres fonctions du client lèvent des erreurs génériques. Après 24 h avec un onglet ouvert (session sans « appareil mémorisé »), l'utilisateur reçoit *« Failed to fetch medias: Unauthorized »* au lieu d'être ramené à l'écran de connexion.

> Sévérité **Moyenne** — Effort **S** — intercepter le 401 dans un helper commun et déclencher `logout()`.

#### U4. Mode « Choisir un film »
##### U4a. Le pool de candidats est structurellement trop étroit — **c'est LA limite du mode aujourd'hui**
**[V]** `api.py:464` : `tmdb.discover_movies(page=1, min_vote_count=25)`. La page est **figée à 1**, le tri à `popularity.desc` : le moteur puise donc, session après session, dans **les ~20 mêmes films populaires du moment**, identiques pour tous les membres du foyer.

Composé avec :
- le refroidissement de 30 jours (`RECOMMENDATION_RECENT_DAYS`) qui exclut tout ce qui a déjà été montré
- les exclusions permanentes (déjà vu, refus durable)
- 2 sessions par jour et par utilisateur

… le pool se vide en quelques sessions. La « sensation de répétition » puis l'écran `state: "empty"` sont **garantis par construction**, quelle que soit la qualité du scoring. Aucun raffinement algorithmique ne peut compenser 20 candidats.

> Sévérité **Élevée** — Effort **S**
> **Recommandation** : tirer une page au hasard entre 1 et 5, faire varier `sort_by` (`popularity.desc`, `vote_average.desc`, `revenue.desc`), et injecter `with_genres` à partir des trois meilleures affinités du profil de goût — `discover_movies` accepte déjà ces trois paramètres, aucune modification du client TMDB n'est nécessaire. Le pool passe de 20 à ~100 candidats pertinents.

##### U4b. L'axe de question « era » ne produit aucun effet
**[V]** `build_local_question` propose l'axe `era` avec les réponses `era:recent` / `era:classic` (`recommendations.py:300-310`). Mais `answer_recommendation` (`api.py:693-703`) ne reconnaît que `light`/`intense` et le préfixe `genre:`, et `score_recommendation_candidate` **n'utilise jamais `release_date`** dans son calcul. La réponse est enregistrée puis ignorée.

Un axe sur quatre du parcours est donc décoratif : l'utilisateur répond à une question qui ne change rien à la recommandation.

> Sévérité **Moyenne** — Effort **S** — soit ajouter un terme de score sur l'année, soit retirer l'axe de `SUPPORTED_QUESTION_AXES`.

##### U4c. Cas « aucun résultat »
**[V]** Point positif : quand le pool est vide, l'API renvoie `state: "empty"` **avant** de créer la session (`api.py:634-635, 652`) — la tentative n'est donc **pas décomptée du quota**. C'est le bon comportement.
**[?]** À vérifier côté interface : que `RecommendationFlow.jsx` affiche un message explicite (« pas de suggestion pour l'instant, réessayez plus tard ») et non un écran vide.

##### U4d. Le quota de 2/jour est trop serré tant que U4a n'est pas corrigé
Deux sessions par jour puisant dans les mêmes 20 films consomment le quota sans rien apporter. Une fois U4a corrigé, 2/jour redevient un réglage raisonnable.

#### U5. Fiche film plein écran (Phase 14) — points d'attention avant implémentation
**[V]** `FilmDetailView.jsx` ne fait aujourd'hui que **20 lignes** : un simple sur-calque plein écran qui gère `Escape` et le blocage du défilement. Tout le contenu de la fiche vit encore dans `BackstagePrototype.jsx`.

Quatre points à traiter avant d'écrire la nouvelle fiche :
1. **[V]** `onClick={onClose}` est posé sur le conteneur plein écran (`FilmDetailView.jsx:17`), sans `stopPropagation` sur l'enfant — **tout clic à l'intérieur de la fiche la fermera**. `AdminCenter.jsx:105` montre le bon pattern (`onClick={(e) => e.stopPropagation()}` sur la section interne).
2. **[V]** Aucun `role="dialog"`, `aria-modal="true"`, ni piège de focus. Au clavier, la tabulation sort de la fiche et parcourt la bibliothèque en arrière-plan.
3. **[V]** `libraryScrollTop` (`BackstagePrototype.jsx:135`) existe déjà pour restaurer la position de défilement à la fermeture — à conserver, c'est ce qui rend le passage grille ↔ fiche agréable.
4. C'est le bon moment pour **extraire réellement la fiche du monolithe** (P10) plutôt que de déplacer 400 lignes dans un composant qui n'en garde que la coquille.

> Sévérité **Moyenne** (préventive) — Effort **M**

#### U6. Centre d'administration pour un usage occasionnel
**[V]** Au-delà de la duplication (A6), le problème d'ergonomie est que la vue d'ensemble affiche **quatre compteurs non cliquables** (`AdminCenter.jsx:134-139`) : « Expirations proches : 2 », « Demandes de conservation : 1 »… sans moyen d'agir depuis là.

Pour quelqu'un qui ouvre ce panneau une fois par semaine, ce qu'il faut c'est une seule liste « **ce qui demande votre attention** » : demandes en attente + erreurs de service + expirations sous 3 jours, chaque ligne portant son action. `GET /api/admin/dashboard` **renvoie déjà exactement ces trois listes** (`expiring`, `downloads`, `errors`) — il ne manque que le rendu.

> Sévérité **Moyenne** — Effort **S** (une fois A6 tranché)

#### U7. Accessibilité
**[V]**
- **`<html lang="en">`** dans `proto-ui/index.html` alors que l'intégralité de l'interface est en français → les lecteurs d'écran prononcent le français avec une voix anglaise. **Correction : un mot.**
- **1 seul `aria-label`** dans 2024 lignes de `BackstagePrototype.jsx`.
- Aucune modale n'a `role="dialog"` ni `aria-modal`, aucune ne piège le focus (U5.2).
- Le thème sombre utilise `text-white/60` sur `#111111` : ratio de contraste ≈ **4,1:1**, sous le seuil AA de 4,5:1 pour du texte normal. Utilisé pour les textes secondaires — dates d'expiration, quotas, états de service.
- Cibles tactiles du panneau admin : `px-2 py-1 text-xs` ≈ 28 px de haut, contre 44 px recommandés.

Pour un usage familial multi-générationnel, les deux premiers points comptent réellement.

> Sévérité **Moyenne** — Effort **S** (`lang` + contrastes) / **M** (modales)

#### U8. Adaptation mobile et tablette
**[V]** La base est saine : `<meta name="viewport">` correct, et les préfixes Tailwind `sm:`/`lg:`/`xl:` sont utilisés systématiquement (`AdminCenter` bascule en colonne sous `sm`, la nav devient horizontale, etc.).

Deux points à vérifier sur un vrai usage canapé :
- **[V]** La grille de bibliothèque affiche les **252 affiches sans virtualisation ni pagination**. La pagination existait dans la V1 NiceGUI mais n'a pas été reportée dans `proto-ui`. Sur mobile, c'est 252 images à charger et à conserver en mémoire.
- Les cibles tactiles trop petites du panneau admin (U7).

> Sévérité **Moyenne** — Effort **M** (pagination ou défilement infini)

#### U9. Notifications peu visibles
**[V]** Le système est complet côté serveur (expiration, disponibilité, alerte stockage, décisions de conservation, avec déduplication par `dedupe_key`). Mais côté interface, `fetchNotifications` n'est appelée **que dans `AccountPanel.jsx:33**, donc **uniquement quand l'utilisateur ouvre le panneau de compte**. Aucun badge de non-lus dans la barre principale, aucune bulle à l'arrivée.

Une alerte « votre location expire dans 48 h » ou « espace disque faible » peut donc rester invisible plusieurs jours.

> Sévérité **Moyenne** — Effort **S**
> **Recommandation** : un compteur de non-lus sur l'icône de compte, rafraîchi au chargement et après chaque action. Très bon rapport gain/effort.

---

### Axe 6 — Nouvelles fonctionnalités à évaluer

| # | Fonctionnalité | Pertinence | Complexité | Dépendances |
|---|---|---|---|---|
| F1 | Séries par saison/épisode | **Haute** | **M-L** | **Bloquée par S9** |
| F2 | Watchlists / favoris partagés | Moyenne-haute | **S** | aucune |
| F3 | Statistiques personnelles | Haute | **M** | F1 pour les séries |
| F4 | Contrôle parental | Conditionnelle [?5] | **L** | **Bloquée par S10** |
| F5 | PWA installable / hors-ligne | Faible (PWA S, hors-ligne à écarter) | **S** | aucune |
| F6 | Amélioration du moteur de reco | Haute, mais **pas par les embeddings** | **S** puis M | **U4a d'abord** |
| F7 | Journal d'activité utilisateur | Moyenne | **S** | aucune |
| F8 | Export / partage de fiche | Faible-moyenne | **S** (interne) | aucune |
| F9 | GHCR + dev/stable | **Haute — à remonter en priorité** | **S** puis M | aucune |

**F1 — Séries par saison/épisode.** Le plus attendu, et le plus contraint. Les données sont là (**1091 épisodes en base, vérifié**), mais `episode.watched` est **global, pas par utilisateur** (S9) : implémenter une gestion fine par saison sur cette base reviendrait à construire une fonctionnalité multi-utilisateur sur un modèle mono-utilisateur. Prérequis : table `user_episode_state` + `series_progress` transformé en projection par utilisateur. **C'est le prérequis n°1 du multi-utilisateur réel**, et il doit précéder F2 et F3.

**F2 — Watchlists partagées.** Le modèle de données est déjà correct pour ça : une route qui agrège `user_media_state WHERE is_watchlist = 1` de tous les comptes, en lecture seule, sans jamais dupliquer un `Media`. Coût réel : une requête et un composant. **Point d'attention vie privée** : rendre le partage explicite (opt-in par utilisateur) plutôt qu'implicite — dans un foyer, voir la watchlist de quelqu'un d'autre sans qu'il l'ait choisi peut gêner.

**F3 — Statistiques personnelles.** ⚠ **`stats.py` est inutilisable en l'état** : il est orphelin (importé nulle part, A7) **et** il raisonne sur la liste globale des `Media`, sans aucune notion d'utilisateur — il calcule des agrégats de catalogue (doublons, taux d'enrichissement TMDB), pas des statistiques personnelles. Les vraies données sont ailleurs : `user_media_state` (notes, statuts, dates) et `playback_progress` (`position_ticks`/`runtime_ticks` donnent le **temps réellement regardé**, ce que `stats.py` ne sait pas faire). **Recommandation : écrire un module neuf orienté utilisateur et supprimer l'ancien**, plutôt que d'essayer de réutiliser le premier.

**F4 — Contrôle parental.** ⚠ **Ce serait une illusion tant que S10 n'est pas corrigé** : filtrer côté interface ne sert à rien si `/playback/manifest` reste ouvert à tout compte. Il faut trois briques : (a) une source de classification par âge — **et OMDB, cité dans la documentation, n'existe pas dans le code V2** ([?7]) ; TMDB fournit les `release_dates` avec certification, déjà récupérées par `get_movie_details` via `append_to_response`, c'est la piste à privilégier ; (b) un champ `max_certification` par utilisateur ; (c) un contrôle **côté serveur** sur `availability`, `manifest` et `acquisition`. Pertinence entièrement conditionnée à [?5].

**F5 — PWA / hors-ligne.** À dissocier. La **PWA installable** (manifest + icônes + service worker minimal) coûte S et donne une icône sur l'écran d'accueil de la tablette — gain réel et immédiat pour l'usage canapé. Le **hors-ligne**, en revanche, n'a pas de sens : tout le contenu vient du serveur domestique, qui est sur le même réseau que le client. Faire la première, écarter le second.

**F6 — Amélioration du moteur.** ⚠ **Le problème n'est pas l'algorithme, c'est le pool de 20 candidats (U4a).** Le scoring local est déjà correct et explicable (affinités de genre, favoris, watchlist, nouveauté, pénalités temporaires dégressives). Ordre recommandé :
1. Élargir et diversifier le pool TMDB (**S**) — c'est ce qui débloque tout.
2. Utiliser `/movie/{id}/similar` et `/movie/{id}/recommendations` de TMDB à partir des favoris (**M**, sans IA) — très efficace et bien plus adapté que des embeddings à cette échelle.
3. **Embeddings : à écarter** (**L**, gain marginal sur quelques centaines de films).
4. **Historique cross-utilisateur anonymisé : à écarter** — avec 2 à 4 comptes, il n'y a mathématiquement pas assez de signal pour du filtrage collaboratif, et ça introduit un sujet de vie privée pour rien.

**F7 — Journal d'activité utilisateur.** Toutes les données existent déjà (`recommendation_events`, `playback_progress`, `media_rentals`, `notifications`), toutes portent `backstage_user_id`. Une route « mon activité » est essentiellement une lecture filtrée et fusionnée. **Excellente candidate pour être livrée avec F3** — même écran, même requêtes.

**F8 — Export / partage de fiche.** Dans un foyer où tout le monde a un compte, un lien public n'a pas d'intérêt et exposerait le serveur. En revanche, un « recommander à X » **interne** est quasi gratuit : une `Notification` avec un `dedupe_key` — toute l'infrastructure existe déjà. Faire la version interne, écarter le lien public.

**F9 — GHCR + stratégie dev/stable : oui, à remonter en priorité.**
Ce n'est plus un confort. **A1 (17 commits de retard), A2 (variables manquantes) et A3 (crash-loop sur un module non commité) sont trois symptômes de la même cause** : la chaîne « code local → GitHub → image → conteneur » n'est vérifiée par rien, et le développeur n'apprend qu'un déploiement est cassé qu'en consultant les logs après coup.

Le minimum viable coûte **S** : un workflow GitHub Actions qui, sur push de `main`, (1) lance `pytest`, (2) construit l'image Docker, (3) la démarre avec des variables minimales et vérifie que `/health` répond. Ces trois étapes auraient intercepté A3 et signalé A4. Le registre GHCR et les tags `dev`/`stable` viennent ensuite (**M**), et permettront en plus un retour arrière immédiat par changement de tag.

**C'est le meilleur rapport gain/effort de tout l'audit, après la sauvegarde hors-site.**

---

## 3. Quick wins (fort impact, faible effort)

Dans l'ordre d'exécution recommandé :

| # | Action | Réf. | Durée |
|---|---|---|---|
| 1 | Aligner la branche de déploiement sur `main` | A1 | 15 min |
| 2 | Ajouter au `docker-compose.yml` : `GEMINI_*`, `RECOMMENDATION_*`, `RADARR_DEFAULT_*`, `BACKSTAGE_COOKIE_SECURE` | A2 | 15 min |
| 3 | **Sauvegarde chiffrée quotidienne hors-site** (1,2 Mo/jour) | R1 | 1 h |
| 4 | `tzdata` dans `requirements.txt` | A4 | 1 min |
| 5 | Supprimer le N+1 de `GET /medias` (`list_user_media_states` existe déjà) | P1 | 30 min |
| 6 | `PRAGMA journal_mode=WAL` + `timeout=15` sur les connexions | P2 | 15 min |
| 7 | Rendre visibles le chargement et l'erreur du catalogue | U1 | 20 min |
| 8 | Ne plus appeler `fetchMediaServerActivity` pour les non-admins | U2 | 15 min |
| 9 | `require_admin` sur `PATCH /medias/{id}`, `relink_tmdb`, `from_tmdb`, `series/refresh` | S8 | 20 min |
| 10 | `asyncio.to_thread` sur SMTP, Gemini et `authenticate` | P6 | 20 min |
| 11 | Élargir le pool TMDB (page aléatoire + genres du profil) | U4a | 1 h |
| 11b | **`BACKSTAGE_PUBLIC_URL` sur le nom MagicDNS du tailnet + vérifier les `SMTP_*` dans Portainer** | N1 | 10 min |
| 11c | **Révoquer les identifiants Notion et Google Calendar dormants, puis nettoyer `.env`** | N2 | 15 min |
| 12 | ~~Limitation de débit sur `/login` et `/forgot-password`~~ — **déclassée** (accès VPN uniquement) ; le volet robustesse est couvert par l'action 10 | S3, S5 | — |
| 13 | Index `media(tmdb_id, type)` | P3 | 5 min |
| 14 | Badge de notifications non lues | U9 | 30 min |
| 15 | `lang="fr"` dans `index.html` | U7 | 1 min |
| 16 | Journalisation des six événements de sécurité | S18 | 45 min |
| 17 | `Promise.allSettled` dans `AdminCenter` | R3 | 15 min |
| 18 | Supprimer `frontend/`, `stats.py`, `score_candidate`, `_adaptive_question_from_candidates` | A7, A8 | 20 min |
| 19 | Sortir `list_admin_rentals()` de la boucle du scheduler | P5 | 10 min |

**Total : environ une journée de travail**, pour lever les deux risques critiques et la majorité des problèmes visibles à l'usage.

⚠ **Exception** : `PRAGMA foreign_keys=ON` (S14) n'est **pas** un quick win — à tester d'abord sur une copie de la base, car des orphelins existants pourraient faire échouer des écritures.

---

## 4. Chantiers de fond (ordre de priorité suggéré)

### 1. Intégration continue minimale — *pourquoi en premier*
Tests + construction de l'image + démarrage à blanc, sur push de `main`. A1, A2 et A3 ne se reproduiront plus, et **tous les chantiers suivants reposent sur la confiance qu'on peut avoir dans le déploiement**. Sans ça, chaque correction apportée ci-dessous risque de ne jamais arriver en production sans qu'on le sache. Coût : une demi-journée.

### 2. État des épisodes par utilisateur — *pourquoi en deuxième*
C'est **la seule violation structurelle** de la règle catalogue/état utilisateur (S9), et elle bloque simultanément F1 (séries par saison), F3 (statistiques) et tout usage multi-utilisateur crédible des séries. Tant qu'elle est là, chaque fonctionnalité série construite par-dessus devra être refaite. À noter : la base compte aujourd'hui **1 utilisateur, 0 `user_media_state`, 0 location** — le multi-utilisateur n'a jamais été éprouvé en conditions réelles, c'est le moment le moins coûteux pour corriger le modèle.

### 3. Budget du scheduler et fin des exceptions muettes
P4 (750 requêtes HTTP/minute) et R2 (erreurs indiscernables). C'est ce qui consommera la machine et masquera les pannes dès que le catalogue grandira. Mise en cache par cycle, intervalle à 300 s, exceptions typées.

### 4. Durcir la règle de suppression sécurisée — *avant* d'implémenter la suppression réelle
R4 : les trois cas limites produisent tous des faux positifs de suppression. Sans risque aujourd'hui (simulation seule), critique le jour où l'exécution sera branchée. À traiter **avant** ce branchement, pas après.

### 5. Versionner le schéma + sauvegarde automatique avant migration
A9 : `PRAGMA user_version`, migrations numérotées, et surtout `create_backup()` **avant** toute migration au démarrage. C'est le filet de sécurité qui manque lorsqu'on modifiera le schéma pour le chantier n°2.

### 6. Unifier les deux panneaux d'administration + fiche film plein écran
A6 + U5 + U6. Les deux chantiers touchent les mêmes fichiers et le même monolithe — les mener ensemble évite de traverser `BackstagePrototype.jsx` deux fois.

### 7. Découper `api.py` et `store.py`
A10. **À faire en profitant du chantier n°6**, pas comme refonte isolée : un découpage sans motif fonctionnel produit du mouvement sans valeur.

### 8. Sortir NiceGUI
A5. Faible risque, faible urgence, vraie simplification. À faire quand rien de plus important n'est en cours.

---

## 5. Points nécessitant une confirmation du développeur

| # | Question | Ce que ça change |
|---|---|---|
| 1 | `/usr/share/zoneinfo` est-il présent dans le conteneur ? (`docker exec … python -c "from zoneinfo import ZoneInfo; ZoneInfo('Europe/Paris')"`) | Détermine si les recommandations renvoient 500 en production pour **tous les comptes non-admin** (A4). Ajouter `tzdata` quoi qu'il arrive. |
| 2 | Le conteneur tourne-t-il actuellement, et sur quel commit ? | A1/A3 — les logs fournis montrent une boucle de crash, dont il faut confirmer qu'elle est bien résolue en ligne. |
| 3 | **Backstage est-il exposé sur Internet, ou uniquement sur le LAN / via VPN ?** | Requalifie S2a, S3 et S5 de « moyenne/élevée » à **critique** si l'exposition est publique. C'est la question la plus structurante de l'axe sécurité. |
| 4 | Combien de comptes réels sont prévus à court terme ? | La base compte **1 utilisateur, 0 état utilisateur, 0 location, 0 événement de recommandation** : tout le multi-utilisateur est **non éprouvé**. Le nombre cible conditionne la priorité du chantier n°2. |
| 5 | Y a-t-il des enfants dans le foyer ? | Détermine la pertinence de F4 (contrôle parental) — et donc l'urgence de S10. |
| 6 | **La lecture doit-elle être réservée aux détenteurs d'une location active, ou tout le foyer peut-il lire tout ce qui est disponible ?** | S10 — c'est une décision produit, pas technique. Elle change la nature du système de locations : gestion de stockage ou contrôle d'accès. |
| 7 | OMDB : abandonné ou à réintégrer ? | `BACKSTAGE_OVERVIEW.md` §2 le cite ; **aucun code V2 ne l'utilise** et `tests/test_config.py` assert son absence. Impacte F4 (classification par âge) et la correction de la documentation (A12). |
| 8 | Les branches `codex/*` sont-elles à supprimer ? | **[V]** Les deux branches distantes sont entièrement fusionnées dans `main` (0 commit d'avance). Ménage sans risque. |
| 9 | Le disque de sauvegarde dédié est-il destiné aux médias, à la base, ou aux deux ? | Ne change pas R1 : un second disque **dans la même machine** ne protège ni d'une erreur humaine ni d'un sinistre. La sauvegarde hors-site reste nécessaire dans tous les cas. |

---

*Audit réalisé sur le dépôt à l'état du commit `cb16cbe` (branche `main`), base de données de 252 médias / 1091 épisodes / 1 utilisateur, suite de tests exécutée : 178 passés, 8 échoués (cause unique : A4).*
