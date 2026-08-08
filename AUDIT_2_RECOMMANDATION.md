# Audit #2 — 7 août 2026
## Partie A : différentiel depuis l'audit du 6 août · Partie B : moteur « Choisir un film »

État analysé : `ea7776b` (local et `origin/main` alignés). Suite de tests réexécutée : **180 passés / 8 échoués**.
Convention : **[V]** vérifié · **[D]** déduit · **[?]** à confirmer.

---

# Partie A — Ce qui a changé

## A.1 Ce qui a été corrigé

**A6 — Unification des panneaux d'administration : fait, et bien fait.** [V]

Deux commits (`5320570`, `ea7776b`), 451 insertions / 387 suppressions.

| | Avant | Après |
|---|---|---|
| `AccountPanel.jsx` | 446 l. — compte **+** admin mélangés | **130 l.** — compte seul (mot de passe, appareils, notifications) |
| `AdminCenter.jsx` | 165 l. — **lecture seule** | **211 l.** — conserver / refuser / prolonger, sauvegardes, simulation de nettoyage |
| `UserManagement.jsx` | — | **176 l.** — extraction propre |

Les trois actions de conservation, les contrôles de sauvegarde et la simulation de nettoyage sont maintenant dans le centre d'administration. La séparation « mon compte » / « administration » est nette. **Le constat A6 est levé**, et les tests d'interface ont suivi (`test_catalogue_playback_ui.py`, +73 lignes). +2 tests au vert.

## A.2 Ce qui n'a pas bougé

Vérification directe sur le dépôt à jour :

| Réf. | Constat | Sévérité | Statut |
|---|---|---|---|
| **A1** | Branche déployée en retard sur `main` | Critique | ❌ **aggravé : 17 → 19 commits** |
| **A2** | `GEMINI_*`, `RECOMMENDATION_*`, `RADARR_DEFAULT_*`, `BACKSTAGE_COOKIE_SECURE` absents du compose | Critique | ❌ `grep` = 0 occurrence |
| **R1** | `BACKUP_DIR` et `DB_PATH` sur le même volume | Critique | ❌ inchangé |
| **N1** | `BACKSTAGE_PUBLIC_URL` non défini → lien de reset vers `localhost` | Élevée | ❌ inchangé |
| **N2** | Identifiants Notion / Google Calendar dormants dans `.env` | Moyenne | ❌ inchangé |
| **A4** | `tzdata` absent de `requirements.txt` | Élevée | ❌ les 8 mêmes tests échouent |
| **P1** | N+1 sur `GET /medias` | Élevée | ❌ inchangé |
| **P2** | `journal_mode=delete` | Élevée | ❌ inchangé |
| **S8** | `PATCH /medias/{id}` sans `require_admin` | Élevée | ❌ inchangé |
| **S9** | `episode.watched` global | Élevée | ❌ inchangé |
| **U1** | `const [, setLoading]` / `const [, setError]` | Élevée | ❌ les 2 lignes sont toujours là |
| **U2** | `fetchMediaServerActivity` appelée pour les non-admins | Élevée | ❌ inchangé |
| **U7** | `<html lang="en">` | Moyenne | ❌ inchangé |
| **R3** | `Promise.all` dans `AdminCenter` | Moyenne | ❌ toujours `Promise.all` (7 appels maintenant, au lieu de 6) |

**Le travail réalisé est de bonne qualité, mais il portait sur le point n°6 de la liste des chantiers de fond.** Les trois points critiques (déploiement, variables manquantes, sauvegardes) et les quick wins d'une journée sont intacts. Et comme la branche de déploiement n'a pas bougé, **l'unification de l'administration n'est pas non plus en production** — elle rejoint les 19 commits en attente.

> Rien de tout cela n'invalide le travail fait. C'est juste que l'ordre de priorité proposé n'a pas été suivi, et il vaut mieux le dire clairement que de le laisser passer.

---

# Partie B — Moteur « Choisir un film » : diagnostic et remise à niveau

## B.0 Diagnostic en une phrase

**Le moteur n'est pas mal conçu, il est affamé.** 94 notes, 36 films « A revoir », 90 « Terminé » et 252 titres choisis à la main sont en base — **il en lit zéro**. Puis il classe 20 films populaires figés avec une formule qui, à froid, favorise les films dépourvus de métadonnées.

Aucun réglage de pondération ne peut compenser ça. C'est un problème d'**entrées**, pas de formule.

---

## B.1 Les défauts, du plus coûteux au moins coûteux

### D1 — Le profil de goût ne lit rien de ce que vous avez saisi ⛔ *bloquant*

Trois causes qui se cumulent, toutes vérifiées :

**a) Mauvaise table.** `build_taste_profile` (`recommendations.py:81`) itère sur `user_states`, c'est-à-dire la table `user_media_state` — qui contient **0 ligne** [V]. Vos notes et statuts sont dans `media.rating` / `media.status`, jamais lus.

**b) Mauvais format de note.** `_rating_value()` (`recommendations.py:52-58`) fait `float(rating)`. Or votre base contient **deux échelles cohabitant dans la même colonne** [V] :

```
94 medias avec une note non vide
 ├─ 23 parsables en float   (échelle /5 : 3.0, 3.5, 4.0, 4.5…)
 └─ 71 NON parsables        (échelle /10 en étoiles, héritage V1 Notion)
       '⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️'      ×17
       '⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️'     ×16
       '⭐️⭐️⭐️⭐️⭐️⭐️⭐️'        ×13
       '⭐️⭐️⭐️⭐️⭐️⭐️'          ×12
       '⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️'    ×9
```

`_rating_value` renvoie `None` sur les 71 → **75 % de vos notes sont jetées silencieusement**. Et ce sont justement les plus informatives : elles s'étalent de 1 à 10 étoiles, là où les 23 notes numériques sont toutes tassées entre 3 et 4,5.

**c) Vocabulaire de statut incomplet.** `build_taste_profile` ne reconnaît que `{"Terminé", "Terminée"}`. Or vos statuts réels sont [V] :

```
À regarder    124      ← intention, non lue
Terminé        90      ← lue
A revoir       36      ← NON lue  ⚠
watchlist       1
En cours        1
```

Les **36 films « A revoir »** sont le signal positif le plus fort de toute la base — on ne remet pas un film qu'on n'a pas aimé. Ils ne comptent pour rien.

> **Résultat mesuré** : `confidence = 0.0`, `genre_affinity = {}`. Le moteur est en démarrage à froid **permanent**, et le restera même après des années d'usage, puisque `user_media_state` ne se remplit que via `PATCH /medias/{id}/personal`.

---

### D2 — À froid, la formule récompense l'absence d'information 🐛 *bug*

`recommendations.py:183-184` :
```python
matching_affinities = [profile.genre_affinity.get(genre, 0) for genre in genres]
taste = sum(matching_affinities) / len(matching_affinities) if matching_affinities \
        else 0.5 * (1 - profile.confidence)
```

`.get(genre, 0)` fait que `matching_affinities` est **non vide dès que le film a au moins un genre** — remplie de zéros. Le repli neutre `0.5 * (1 - confidence)` ne se déclenche donc que pour un film **sans aucun genre**.

Conséquence, mesurée par simulation sur le profil réel (`confidence = 0`) :

| Film | Score |
|---|---|
| **Sans aucun genre**, note 7,0 | **0,5060** |
| Note 8,5, 1 genre | 0,1930 |
| Note 8,5, 4 genres | 0,1930 |
| Note 6,0, 1 genre | 0,1730 |
| Note 5,0, 2 genres | 0,1650 |

**Un film sans métadonnées de genre score 2,6× plus haut qu'un film noté 8,5.** Le repli est branché à l'envers : il devrait se déclencher quand on ne sait rien de **l'utilisateur**, pas quand on ne sait rien du **film**.

Et entre les films réels (qui ont tous des genres), l'écart total est de **0,028** — soit 17 % — entièrement dicté par `vote_average` pondéré à 0,08. Comme `choose_from_top` tire ensuite au sort parmi le top 8 avec des poids `max(0.05, score)` quasi identiques, **le résultat final est en pratique un tirage uniforme parmi 8 films populaires**.

---

### D3 — Les films multi-genres sont systématiquement pénalisés 🐛 *bug*

Les genres absents du profil comptent comme **0 dans la moyenne**, au lieu d'être ignorés. Mesuré avec un profil chaud (Drame 0,85 / SF 0,80) :

| Film (même note TMDB 8,5) | Score |
|---|---|
| 1 genre, aimé | **0,7005** |
| 4 genres dont 1 aimé | **0,4161** — **−41 %** |

Or un film TMDB porte typiquement 2 à 4 genres. Le moteur préfère structurellement les films mono-genre, ce qui n'a aucun sens : un « Drame / Science-Fiction / Thriller » quand vous aimez les trois devrait remonter, pas descendre.

---

### D4 — Le terme « nouveauté » est une constante 🐛 *bug*

`recommendations.py:195` :
```python
novelty = 1 if profile.confidence > 0 and not matching_affinities else 0.5
```

Même cause que D2 : `matching_affinities` n'est vide que pour un film sans genre. Donc **`novelty` vaut 0,5 pour tous les films, toujours** [V] — confirmé par la simulation, où la raison `discovery_pick` n'apparaît jamais.

Le terme « nouveauté » (poids 0,07) et le terme `exploration` (0,09 ou 0,18) sont donc deux constantes additives : ils décalent tous les scores du même montant et **ne récompensent jamais la découverte**. Le moteur n'a, en réalité, aucun mécanisme d'exploration actif.

---

### D5 — Le vivier fait 20 films figés, et les questions ne le modifient pas

**a)** `api.py:464` : `tmdb.discover_movies(page=1, min_vote_count=25)` → **20 résultats**, `sort_by="popularity.desc"`, page figée. Les mêmes 20 films pour tout le foyer, tous les jours.

**b) Les réponses ne pilotent pas la recherche, seulement le classement.** `discover_movies` accepte `with_genres` (`tmdb.py:83-84`) — **il n'est jamais transmis** [V]. Répondre « Comédie » ne va pas chercher de comédies : ça re-classe les 20 mêmes films en bonifiant ceux qui se trouvent en être. **Si aucun des 20 n'est une comédie, la réponse ne produit rien.**

**c) L'axe `era` est mort.** Déjà signalé (U4b) : `era:recent` / `era:classic` sont enregistrés, jamais lus. TMDB expose `primary_release_date.gte/lte`, inutilisé.

**d) Le vivier s'épuise en 5 jours.** Chaque session pose une question `movie_compare` qui marque **2 films comme `shown`**, exclus pendant `RECOMMENDATION_RECENT_DAYS = 30` jours. À 2 sessions/jour : 4 films brûlés/jour, pour un vivier de 20 → **saturation en ~5 jours d'usage**.

**e) Et là, l'anti-répétition se désactive toute seule.** `api.py:536-539` :
```python
scored = score_pool(seen_tmdb_ids)
if recent_shown_tmdb_ids and sum(item.score >= 0 for item in scored) < 2:
    # A cooldown is a soft memory, never a reason to show an empty screen.
    scored = score_pool(hard_seen_tmdb_ids)   # ← abandonne le cooldown 30 j
```
Passé le 5ᵉ jour, cette condition est vraie **en permanence**. Le refroidissement de 30 jours devient inerte et les mêmes films reviennent en boucle.

> C'est la cause mécanique exacte de la « sensation de répétition ». Le garde-fou fonctionne comme prévu — c'est le vivier qui est trop petit pour qu'il ait jamais une chance de servir.

---

### D6 — La question la plus informative jette son information

`movie_compare` fait choisir entre deux films : c'est de loin la question la plus riche du parcours. La réponse alimente `preferred_tmdb_ids` (`api.py:697-703`), qui accorde `session = 1` **au film que l'utilisateur vient déjà de choisir** — celui qui allait gagner de toute façon.

**Rien n'est généralisé.** Choisir un film de science-fiction ne renforce pas la science-fiction ; refuser un film d'horreur ne pénalise pas l'horreur. Le seul signal transférable du parcours est jeté à chaque session.

---

### D7 — La bibliothèque n'est jamais candidate 🎯 *question produit*

Le vivier ne contient **que** des résultats `discover` TMDB, c'est-à-dire par construction des films **absents** de votre bibliothèque. Or [V] :

```
252 films en bibliothèque, choisis à la main
 ├─ 124 « À regarder »   ← déjà désirés, jamais proposés par le mode
 ├─  36 « A revoir »
 └─   6 réellement disponibles sur Jellyfin
```

> **Correction apportée par le développeur (07/08)** : « À regarder » ne veut **pas** dire « je veux le voir » — c'est simplement le statut par défaut des films non vus. Le signal d'intention réel, c'est la **watchlist**. J'avais surévalué ces 124 titres comme signal de goût dans une première version ; voir §B.1bis pour la conséquence.

Pour un « Netflix maison », c'est tout de même à l'envers. La question « qu'est-ce que je regarde ce soir ? » devrait chercher d'abord dans ce qui est **lisible tout de suite** (6 titres), puis dans la **watchlist** (intention explicite), et seulement ensuite proposer de la découverte. Les 124 « À regarder » restent utiles comme **vivier de candidats** — ce sont des films dont vous avez déjà les métadonnées et que vous n'avez pas vus — mais **pas** comme entrée du profil de goût.

Aujourd'hui, le mode est à 100 % un moteur d'**acquisition** : il conclut par `confirm_recommendation` qui crée le média et déclenche le téléchargement.

> **[?] À trancher** : « Choisir un film » doit-il répondre à *« que puis-je regarder maintenant »* ou à *« que devrais-je télécharger ensuite »* ? Ce sont deux produits différents. Le second est celui qui est implémenté ; le premier est celui que suggère le nom, et probablement l'usage du canapé. **Les deux sont légitimes — mais il faut choisir, ou assumer deux entrées distinctes.**

---

### D8 — Gemini est employé sur les décisions les moins utiles

| Appel | Ce qu'il décide | Valeur |
|---|---|---|
| 1. `plan_questions` | **L'ordre de 4 axes fixes** — et `_vary_question_plan` peut ensuite faire tourner cet ordre pour éviter les répétitions | ~nulle |
| 2. `select_final` | 1 film parmi des candidats déjà classés | faible quand les scores sont plats (D2) |

La force réelle du modèle — comprendre les synopsis, saisir « comme *Blade Runner* mais plus léger », expliquer *pourquoi* ce film — n'est pas utilisée. Et chaque appel gèle la boucle d'événements 1 à 3 s (P6).

Vous payez deux appels par session pour trier une liste de quatre chaînes de caractères.

---

## B.1bis — Signaux d'intention vs signaux de verdict

La correction sur « À regarder » ouvre une distinction que le code ne fait pas du tout aujourd'hui, et qui est structurante.

| Signal | Nature | Ce qu'il dit | En base [V] |
|---|---|---|---|
| Note (⭐ ou /5) | **verdict** | « j'ai vu, et voilà ce que j'en pense » | **94** |
| `A revoir` | **verdict fort** | « j'ai vu, et je veux le revoir » | **36** |
| `Terminé` | verdict faible | « j'ai vu » | 90 |
| **Watchlist** | **intention forte** | « je veux le voir » | **0** ⚠ |
| Favori | intention/verdict | « celui-là compte pour moi » | 2 |
| `À regarder` | **rien** | « pas encore vu » — statut par défaut | 124 |

Les deux familles ne servent pas à la même chose et ne doivent pas alimenter la même formule :

- **Les verdicts calibrent le profil durable** — ce que vous aimez, indépendamment du moment. Ce sont eux qui doivent nourrir `genre_affinity`.
- **Les intentions pilotent la sélection du moment** — ce que vous voulez voir *maintenant*. Elles ne devraient pas modifier vos affinités de genre (vouloir voir un documentaire ne prouve pas que vous aimez les documentaires), mais elles devraient **remonter fortement un candidat dans le classement**, voire court-circuiter la découverte.

Aujourd'hui, `score_recommendation_candidate` mélange les deux dans un unique `list_bonus` de poids **0,05** (`recommendations.py:194`), alimenté indistinctement par `is_watchlist` **ou** `is_favorite`. Sur une échelle de scores qui s'étale sur 0,03 à froid, 0,05 est certes non négligeable — mais c'est le seul endroit où l'intention s'exprime, et elle est noyée.

**Deux conséquences pour le plan** :

1. **Le chiffre de 4,6× tient.** Le calcul du gain de l'étape 1 excluait déjà « À regarder » (seuls notes + `A revoir` + `Terminé` étaient comptés). La correction ne change donc rien aux mesures — elle confirme le choix qui avait été fait.
2. **La watchlist est vide (0 ligne), et c'est normal** : elle ne se remplit que via `PATCH /medias/{id}/personal`, une route récente. Le profil doit donc s'appuyer sur les **verdicts** (94 + 36) pendant plusieurs semaines. C'est exactement ce que fait l'étape 1 — mais il faut prévoir dès maintenant que le poids de l'intention monte quand la watchlist se remplira :

```python
# à substituer au list_bonus unique de poids 0.05
intent = 0.0
if tmdb_id in watchlisted_tmdb_ids: intent += 0.65   # « je veux le voir »
if tmdb_id in favorite_tmdb_ids:    intent += 0.35
score += 0.22 * min(1.0, intent)
```

Et surtout : **la watchlist doit entrer dans le vivier de candidats** (étape 3), pas seulement bonifier ceux que TMDB a renvoyés par hasard. Un film mis en watchlist qui ne figure pas dans la page 1 de `discover` n'a aujourd'hui **aucune chance** d'être proposé — alors que c'est le film que vous avez explicitement demandé à voir. C'est le défaut le plus contre-intuitif de tout le moteur.

---

## B.1ter — « Est-ce que ça appelle Gemini ? » : non. Jamais.

Réponse factuelle, en trois niveaux.

**1. En production : Gemini n'est pas appelé, et ne peut pas l'être.** [V]
`GeminiRecommendationGateway.enabled` vaut `bool(self.api_key and self.client)`. Or `GEMINI_API_KEY` **n'est pas dans le bloc `environment:` du `docker-compose.yml`** (constat A2, toujours ouvert) → le conteneur ne reçoit jamais la clé → `enabled = False` → `plan_questions` et `select_final` retournent `None` immédiatement, sans aucun appel réseau. Le repli local prend silencieusement le relais.

**2. En local : la clé est présente, mais le mode n'a jamais tourné.** [V]
```
sessions de recommandation créées : 0
appels enregistrés dans ai_usage  : 0
```
**Le mode « Choisir un film » n'a jamais été exécuté une seule fois**, ni en production ni en local. Tout ce qui précède est l'analyse d'un code intégralement écrit, unitairement testé… et jamais exercé en conditions réelles. Ça explique que D2, D3 et D4 aient survécu : aucun résultat n'a jamais été observé.

**3. Même activé, Gemini ne pourrait pas sauver le moteur.**
C'est le point important. `_validate_id` (`gemini_recommendations.py:103-111`) impose que l'identifiant renvoyé appartienne à la liste de candidats fournie par Backstage :
```python
allowed = {int(candidate["tmdb_id"]) for candidate in candidates}
if tmdb_id not in allowed:
    raise ValueError(f"ID TMDB non fourni par Backstage: {tmdb_id}")
```
C'est une **bonne** protection (elle empêche le modèle d'inventer des films). Mais elle a une conséquence structurelle : **Gemini est un re-classeur, pas une source.** Si le vivier contient 20 films populaires, Gemini choisit 1 film populaire parmi 20. Aucune qualité de modèle ne compense un vivier pauvre.

> **D'où l'ordre du plan** : étapes 1 à 3 (signal, bugs, vivier) d'abord ; Gemini en étape 6. Brancher l'IA sur les entrées actuelles ne produirait qu'une sélection lente et coûteuse parmi les mêmes 20 films.

**[?] À vérifier avant d'activer** : `GEMINI_MODEL` vaut par défaut `"gemini-3.5-flash-lite"`. Comme aucun appel n'a jamais été émis, cet identifiant de modèle n'a **jamais été validé** contre l'API. S'il est erroné, l'échec sera **silencieux** : `except Exception` → `_record_gemini_failure` → repli local. Le seul endroit où ça se verrait est la table `ai_usage` (`status='error'`). Prévoir de la consulter après le premier essai réel.

---

## B.1quater — Synchronisation bidirectionnelle disque → Backstage *(demande du 07/08)*

**Besoin exprimé** : un film déposé manuellement dans le dossier des films doit apparaître dans Backstage.

**État actuel** [V] : ce n'est pas possible, et il n'y a aucun mécanisme approchant.

- **Aucun parcours du système de fichiers dans le code** : `grep` sur `os.walk`, `os.listdir`, `glob(` dans `backend/` (hors sauvegardes) → **0 occurrence**. Backstage ne regarde jamais le disque, et c'est un bon choix : le conteneur n'a pas à monter la bibliothèque média.
- **`import_existing_libraries`** (`media_server.py:175`) crée bien des médias absents de Backstage, mais **uniquement à partir de Radarr et Sonarr**. Or Radarr n'a pas connaissance d'un fichier déposé à la main tant qu'un « Manual Import » n'a pas été fait — le chemin est donc rompu pour ce cas précis.
- **`JellyfinClient` n'a pas de méthode d'inventaire.** Ses seules méthodes sont `list_users`, `user_playback`, `find_by_tmdb`, `playback_url`, `playback_manifest_url`, `fetch_playback_resource`. `find_by_tmdb` parcourt bien toute la bibliothèque Jellyfin, mais **dans le sens inverse** : « ce média Backstage existe-t-il chez Jellyfin ? ». Il n'existe rien pour « ce film Jellyfin existe-t-il chez Backstage ? ».

**Or Jellyfin est précisément le bon capteur** : c'est le seul service qui indexe automatiquement un fichier déposé dans le dossier, sans intervention. Le manque est donc bien identifié : **un import Jellyfin → Backstage**, symétrique de celui qui existe déjà pour Radarr/Sonarr.

### Implémentation proposée

**1. Ajouter un inventaire à `JellyfinClient`** — la pagination existe déjà dans `find_by_tmdb`, il suffit de l'extraire :
```python
async def list_library(self, media_type: str | None = None) -> list[dict[str, Any]]:
    """Inventorie les films et séries indexés par Jellyfin, avec leurs ProviderIds."""
    item_types = {"Film": "Movie", "Série": "Series"}.get(media_type) or "Movie,Series"
    items, start, limit = [], 0, 1000
    while True:
        response = await (self.client or http.get_client()).get(
            f"{self.base_url}/Items",
            headers={"X-Emby-Token": self.api_key},
            params={"IncludeItemTypes": item_types, "Recursive": "true",
                    "Fields": "ProviderIds,ProductionYear",
                    "Limit": limit, "StartIndex": start},
            timeout=30.0,
        )
        response.raise_for_status()
        page = self._items_from_payload(response.json())
        items.extend(page)
        if len(page) < limit:
            return items
        start += len(page)
```

**2. Étendre `import_existing_libraries` avec une passe Jellyfin**, en réutilisant exactement la logique existante (rapprochement par `tmdb_id`, création si absent, `upsert_availability`) :
```python
if self.jellyfin:
    for remote in await self.jellyfin.list_library():
        tmdb_id = _int_or_none(remote.get("ProviderIds", {}).get("Tmdb"))
        media_type = "Série" if remote.get("Type") == "Series" else "Film"
        media = next((m for m in medias
                      if m.type == media_type and tmdb_id and m.tmdb_id == tmdb_id), None)
        if media is None:
            media = await self.store.create({
                "title": remote.get("Name") or "Sans titre",
                "type": media_type, "tmdb_id": tmdb_id, "tmdb_ok": bool(tmdb_id),
                "status": "À regarder", "support": "Serveur",
            })
            medias.append(media); created += 1
        await self.store.upsert_availability(Availability(
            media_id=media.id, provider="sonarr" if media_type == "Série" else "radarr",
            jellyfin_id=str(remote["Id"]), state="available",
            last_synced_at=datetime.now(timezone.utc),
        ))
```

**3. Enrichir automatiquement les nouveaux venus.** Un fichier déposé à la main aura souvent un `ProviderIds.Tmdb` (si Jellyfin l'a reconnu) — dans ce cas `create_media_from_tmdb` complète la fiche. Sinon, il faut prévoir une **file « à rapprocher »** dans le centre d'administration : titre brut + recherche TMDB suggérée, à valider en un clic. C'est exactement ce que fait déjà `relink_tmdb`.

**4. Déclenchement.** Deux options, non exclusives :
- **bouton « Importer la bibliothèque »** dans `AdminCenter` — il existe déjà (`importAndRefresh`), il bénéficierait simplement de la nouvelle passe ;
- **passe périodique** dans le scheduler, mais **pas à 60 s** : un inventaire complet de Jellyfin est coûteux. Une fois par heure suffit largement pour un dépôt manuel de fichier.

### Points d'attention
- ⚠ **Ne pas mêler cet import à `sync_all()`** : celui-ci tourne déjà toutes les 60 s et souffre du problème P4. L'inventaire Jellyfin doit être une passe séparée, à sa propre cadence.
- ⚠ **Respecter la séparation catalogue / état utilisateur** : un fichier apparu sur le disque crée un `Media` **et rien d'autre**. Aucun `UserMediaState`, aucun `Rental` — personne ne l'a demandé.
- ⚠ **Le sens inverse (Backstage → disque) n'est pas symétrique et ne doit pas l'être** : supprimer un média dans Backstage ne doit jamais effacer un fichier. La règle de suppression sécurisée (R4) existe précisément pour encadrer ce sens-là, et elle n'est aujourd'hui qu'une simulation.
- **[?]** Les fichiers déposés à la main sont-ils dans la même arborescence que celle gérée par Radarr/Sonarr ? Si oui, ils risquent d'être ramassés à la fois par Jellyfin et, plus tard, par un import Radarr — d'où l'importance du rapprochement par `tmdb_id` avant toute création, et de l'index unique `idx_media_availability_arr` déjà en place.

> Effort estimé : **M** (une demi-journée avec les tests). Sans dépendance avec les étapes 1 à 6 — peut être fait en parallèle.

---

## B.2 Le plan de remise à niveau

Six étapes, ordonnées par rapport gain/effort. Les trois premières sont l'essentiel.

### Étape 1 — Récupérer le signal qui existe déjà ⭐ *la plus rentable*
**Effort : 1 à 2 h · Gain : profil vide → profil complet**

Trois corrections dans `recommendations.py`, plus une migration ponctuelle.

**1a. Normaliser les deux échelles de note**
```python
_STAR = "⭐"

def _rating_value(rating: str | None) -> float | None:
    """Accepte l'échelle /5 numérique et l'échelle /10 en étoiles héritée de la V1."""
    if rating is None:
        return None
    text = str(rating).strip()
    if not text:
        return None
    stars = text.count(_STAR)
    if stars:
        return min(10, stars) / 2.0        # /10 → /5
    try:
        return max(0.0, min(5.0, float(text)))
    except (TypeError, ValueError):
        return None
```

**1b. Reconnaître « A revoir » et centrer le signal sur votre propre moyenne**

Le point neutre n'est pas 0, c'est **votre note moyenne (3,81/5)**. Sans centrage, tout est positif et rien ne discrimine.
```python
NEUTRAL = 3.81 / 5     # à calculer par utilisateur, pas en dur

def _signal(state_or_media) -> float | None:
    rating = _rating_value(state_or_media.rating)
    if rating is not None:
        return (rating / 5 - NEUTRAL) * 2      # → [-1, +1], centré
    status = (state_or_media.status or "")
    if status == "A revoir":
        return 0.5                              # signal positif fort
    if status.startswith("Termin"):
        return 0.1                              # a été regardé, sans plus
    return None                                 # ⚠ None, pas 0
```
Le `return None` est important : aujourd'hui, un film sans note ni statut contribue `signal = 0` et **tire la moyenne du genre vers zéro**. Une entrée neutre ne doit rien dire, pas dire « bof ».

**1c. Migration ponctuelle : matérialiser `media.rating`/`status` dans `user_media_state`**

C'est ce qui débloque tout : `build_taste_profile` lit `user_media_state`, qui est vide. Un script à passer une fois, pour le compte administrateur, sur les 94 notes + 90 statuts.
> ⚠ À exécuter **après** une sauvegarde, et à rendre idempotent (`ON CONFLICT DO NOTHING`) pour ne pas écraser un état déjà saisi.

**Résultat mesuré sur vos données réelles :**

| | Aujourd'hui | Après étape 1 |
|---|---|---|
| Notes lues | 23 / 94 | **94 / 94** |
| Signaux exploités | 0 | **~220** (94 notes + 36 « A revoir » + 90 « Terminé ») |
| `confidence` | **0,00** | **1,00** |
| Écart max-min entre genres | 0,083 | **0,383** — soit **4,6× plus discriminant** |

Et le profil obtenu ressemble enfin à quelqu'un :
```
+ Mystère          +0.263  (8 films)        - Histoire     +0.080
+ Fantastique      +0.180  (14 films)       - Crime        +0.027
+ Drame            +0.168  (90 films)       - Musique      +0.014
+ Romance          +0.168  (12 films)       - Guerre       -0.067
+ Science-Fiction  +0.166  (13 films)       - Animation    -0.120
+ Thriller         +0.159  (32 films)
```

---

### Étape 2 — Corriger les trois bugs de scoring
**Effort : 30 min · Gain : le classement devient un classement**

```python
def _taste_score(genres: list[str], profile: TasteProfile) -> float:
    known = [profile.genre_affinity[g] for g in genres if g in profile.genre_affinity]
    if not known:
        # Aucune information sur CE film : prior neutre pondéré par la confiance.
        return 0.5 * (1 - profile.confidence)
    # max dominant : un film multi-genres n'est plus puni pour ses genres inconnus.
    return 0.65 * max(known) + 0.35 * (sum(known) / len(known))

# novelty devient un vrai signal de découverte
unknown_ratio = 1 - len(known) / max(1, len(genres))
novelty = unknown_ratio if profile.confidence > 0 else 0.5
```

Corrige D2 (le repli ne se déclenche plus que quand on ne connaît aucun des genres du film), D3 (le `max` domine) et D4 (`novelty` mesure enfin une proportion d'inconnu).

---

### Étape 3 — Élargir le vivier et le piloter par les réponses ⭐
**Effort : 2 à 3 h · Gain : 20 candidats figés → 100-150 candidats orientés**

```python
async def _build_pool(tmdb, profile, prefs, library):
    top_genres = [g for g, _ in sorted(profile.genre_affinity.items(),
                                       key=lambda kv: -kv[1])[:3]]
    params = {"page": random.randint(1, 5),
              "sort_by": random.choice(["popularity.desc", "vote_average.desc"])}

    # les réponses pilotent la REQUÊTE, pas seulement le classement
    if prefs.get("genre"):
        params["with_genres"] = [GENRE_IDS[prefs["genre"]]]
    elif top_genres:
        params["with_genres"] = [GENRE_IDS[g] for g in top_genres]
    if prefs.get("era") == "recent":
        params["primary_release_date.gte"] = "2019-01-01"
    elif prefs.get("era") == "classic":
        params["primary_release_date.lte"] = "2005-12-31"

    pools = await asyncio.gather(
        tmdb.discover_movies(**params),
        *[tmdb.similar(m.tmdb_id) for m in _seed_films(library, profile)[:3]],
    )
    return _dedupe(chain(*pools))
```

Trois changements, chacun indépendant :
1. **Page aléatoire 1-5 + tri variable** → 100 candidats au lieu de 20, différents à chaque session (corrige D5a et D5d d'un coup).
2. **`with_genres` transmis** → les réponses vont chercher le bon contenu (D5b). Nécessite une table inverse `GENRE_IDS`, c'est-à-dire `TMDB_GENRE_NAMES` retournée : 3 lignes.
3. **`/movie/{id}/similar` sur 3 films de référence** (vos mieux notés / « A revoir ») → des candidats réellement proches de vos goûts, sans IA. C'est la brique qui rapporte le plus après l'étape 1.

**Et calculer le vivier une seule fois par session**, mis en cache dans `session_preferences` : aujourd'hui `_recommendation_pool` refait un `discover` **à chaque réponse**, soit 6 appels TMDB par session pour la même page 1 (corrige aussi P7).

---

### Étape 4 — Faire généraliser la comparaison
**Effort : 1 h · Gain : les questions servent enfin à quelque chose**

```python
# à l'enregistrement d'une réponse movie_compare
picked   = next(c for c in shown if c.tmdb_id == int(payload.value))
rejected = next(c for c in shown if c.tmdb_id != picked.tmdb_id)

delta = prefs.setdefault("genre_delta", {})
for gid in picked.genre_ids:
    delta[TMDB_GENRE_NAMES[gid]] = round(delta.get(TMDB_GENRE_NAMES[gid], 0) + 0.30, 3)
for gid in set(rejected.genre_ids) - set(picked.genre_ids):
    delta[TMDB_GENRE_NAMES[gid]] = round(delta.get(TMDB_GENRE_NAMES[gid], 0) - 0.20, 3)
```
puis, au scoring, additionner `genre_delta` aux affinités durables **pour la session en cours seulement**.

Le `- set(picked.genre_ids)` compte : si les deux films partagent le Drame, refuser l'un ne dit rien contre le Drame. Sans ce filtre, la comparaison produirait du bruit.

Corrige D6, et rend le parcours de questions réellement adaptatif — ce que son nom promet déjà.

---

### Étape 5 — Réduire le taux de brûlage
**Effort : 30 min**

1. **Distinguer « montré » de « rejeté ».** Un film simplement affiché dans une comparaison ne mérite pas 30 jours d'exclusion. Proposition : `shown` → **7 jours** ; `not_now` → 14 j (déjà le cas) ; `less_like_this` → 45 j (déjà) ; `already_seen` / `hard_reject` → permanent (déjà).
2. **Supprimer le repli qui désactive le cooldown** (`api.py:537-539`). Une fois l'étape 3 en place, le vivier est assez large pour ne plus jamais en avoir besoin — et ce repli masque aujourd'hui le vrai problème au lieu de le signaler.

---

### Étape 6 — Réaffecter Gemini là où il paie *(optionnel)*
**Effort : 2 h**

1. **Supprimer `plan_questions`.** Choisir l'ordre de 4 axes fixes ne justifie pas un appel réseau ; `_vary_question_plan` fait déjà le travail d'anti-répétition, localement et gratuitement.
2. **Réinvestir l'appel libéré dans un re-classement sémantique** des ~30 meilleurs candidats à la lumière des réponses : c'est là que le modèle apporte quelque chose qu'aucune formule ne sait faire (comprendre qu'un thriller contemplatif ressemble à un drame lent, pas à un film d'action).
3. **Garder `select_final`**, mais lui demander en plus **une phrase de justification** affichée avec le résultat. C'est le meilleur gain de qualité perçue par euro dépensé.
4. **Envelopper les deux appels dans `asyncio.to_thread`** (P6) — sans ça, chaque session gèle le serveur pour tout le foyer.

---

## B.3 Récapitulatif

| Étape | Effort | Corrige | Gain attendu |
|---|---|---|---|
| **1. Récupérer le signal existant** | 1-2 h | D1 | `confidence` 0 → 1 · **4,6× de discrimination** |
| **2. Corriger les 3 bugs de scoring** | 30 min | D2, D3, D4 | fin du biais mono-genre et du bonus « sans métadonnées » |
| **3. Élargir et piloter le vivier** | 2-3 h | D5 | 20 → ~120 candidats, orientés, renouvelés |
| **4. Généraliser la comparaison** | 1 h | D6 | les questions influencent enfin le résultat |
| **5. Réduire le brûlage** | 30 min | D5d/e | fin de la répétition au 5ᵉ jour |
| **6. Réaffecter Gemini** | 2 h | D8 | qualité perçue, justification du choix |
| **7. Import Jellyfin → Backstage** *(indépendant)* | M | §B.1quater | un fichier déposé à la main apparaît dans Backstage |

**Total : environ une journée.** Les étapes 1 et 2 (2 h 30) délivrent à elles seules la majeure partie du gain — et l'étape 1 ne demande aucune décision de conception, seulement de lire ce qui est déjà là.

**Deux décisions préalables** [?] :
1. **D7** — « que puis-je regarder maintenant » ou « que télécharger ensuite » ? Cela détermine si la bibliothèque entre dans le vivier, et c'est la seule question de cette partie qui ne soit pas purement technique.
2. Confirmer que les notes en étoiles sont bien sur **10** (17 films à 8 étoiles, 9 à 10 étoiles — cohérent avec une échelle /10, mais vous seul pouvez le confirmer).

---

## B.4 Une remarque de méthode

Les défauts D2, D3 et D4 sont invisibles à la lecture du code : les trois expressions sont correctes syntaxiquement et se lisent bien. Ils ne sont apparus qu'en **exécutant le scorer sur des candidats fabriqués** et en comparant les scores.

Trois tests de caractérisation suffiraient à les figer définitivement :
```python
def test_film_sans_genre_ne_bat_pas_un_film_bien_note()      # D2
def test_multi_genres_nest_pas_penalise()                     # D3
def test_novelty_recompense_un_genre_inconnu()                # D4
```
La suite actuelle teste le scoring (`test_recommendation_scoring.py`), mais sur des **comparaisons relatives** (« le film vu n'est pas éligible », « le bonus watchlist est petit ») — jamais sur les valeurs absolues ni sur les cas dégénérés. C'est exactement là que ces trois bugs se sont logés.
