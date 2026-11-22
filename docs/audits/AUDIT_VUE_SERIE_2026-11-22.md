# Audit de la vue Série — 22/11/2026

Périmètre : fiche série (`proto-ui/src/BackstagePrototype.jsx:1826-1945`), cartes série de la bibliothèque (`:1712-1803`), API épisodes (`backend/api.py:1537-1735`), synchro Jellyfin/Sonarr (`backend/core/media_server.py`), demande de téléchargement (`backend/api.py:2057+`, `backend/core/seerr.py`).

---

## 1. Bugs bloquants

### B1 — « Aucun épisode disponible » alors que la série est sur Jellyfin
Il y a deux causes possibles, qui peuvent se cumuler :

| Cause | Où | Effet |
|---|---|---|
| **a. Les séries créées par la synchro n'ont aucun épisode en base.** `import_existing_libraries` crée le média (`media_server.py:347` et `:373`) mais n'appelle jamais `create_episodes`. Seul l'import manuel TMDB (`api.py:1652`) remplit la table `episode`. | synchro Sonarr/Jellyfin | liste vide → message « Aucun épisode disponible » (`jsx:1940`) |
| **b. La correspondance Jellyfin passe uniquement par l'ID TMDB.** `list_library` ignore tout item sans `ProviderIds.Tmdb` (`jellyfin.py:175-177`). Pour les séries, Jellyfin (et Sonarr) utilisent surtout **TVDB** : beaucoup de séries n'ont pas d'ID TMDB côté Jellyfin. | synchro | pas de `jellyfin_id` → tous les épisodes en « Non téléchargé », bouton « Demander cette série » |
| c. La disponibilité d'un épisode n'est calculée que si `availability.jellyfin_id` existe (`api.py:1557`). Un état `imported` côté Sonarr ne compte pas. | API épisodes | idem (b) |

Dans la base locale, *Person of Interest* a bien 103 épisodes mais **aucune ligne `media_availability`**. On est donc dans le cas (b). La base Docker (`/data/backstage.db`) n'a pas pu être vérifiée d'ici. Si la fiche y affiche « Aucun épisode disponible », c'est le cas (a).

Le libellé lui-même est faux : il veut dire « aucun épisode connu en base », pas « aucun épisode disponible ».

### B2 — Image du haut absente ou mauvaise
- Le mapping met `backdrop = backdrop_url || cover_url || photo Unsplash` (`jsx:152`). Sans vraie image horizontale, la fiche série affiche donc **l'affiche verticale recadrée en 16:9** ou **une photo générique**.
- La fiche film gère ce cas (repli « affiche + flou », `jsx:1960-1995`). La fiche série ne le gère pas (`jsx:1832`), et il n'y a pas de `onError` si l'URL est cassée.
- `_enrich_media` ne fait rien dès que `cover_url` et `synopsis` existent (`media_server.py:306`). Une série qui a une affiche mais pas d'image de fond n'en reçoit donc jamais.
- Jellyfin renvoie pourtant `backdrop_tag` (`jellyfin.py:186`). Cette donnée n'est jamais utilisée comme source de secours.

### B3 — Impossible de télécharger une saison ou un épisode
- La demande ne connaît que « toute la série » : `seasons = "all"` (`seerr.py:64`).
- Le mode `monitor="future"` envoie `seasons: []`, ce qui revient à ne rien demander dans Seerr.
- Les non-admins reçoivent une 403 (`api.py:2078`) et ont un bouton grisé « Série à demander à l'admin », sans aucun moyen de faire réellement la demande.

---

## 2. Incohérences UX

1. **Le même bouton apparaît trois fois** (« Choisir un épisode » / « Demander cette série ») : bloc disponibilité (`:1862`), sous le synopsis (`:1876`), et implicitement via l'onglet.
2. **Les boutons de statut sont en double**, avec deux orthographes : « Terminée » en haut (`:1848`), « Terminé » dans Informations (`:1895`). Le filtre de la bibliothèque propose les deux (`:1687`).
3. **Le statut manuel entre en conflit avec le statut calculé.** Le backend recalcule le statut à partir des épisodes vus (`store.py:983-991`), mais on peut forcer « Terminée » à la main. De plus, le mapping force « Terminé » dès qu'il y a une note (`jsx:156`).
4. **Le bloc « Support / Emplacement » est décoratif** : quatre étiquettes en dur, non cliquables et non liées aux données (`:1854`).
5. **On masque des données manquantes par de fausses valeurs** : « Acteur principal », « Créateur inconnu », « Aucun synopsis disponible pour le moment. ».
6. **Le geste « double-clic = marquer vu »** sur un épisode est invisible. Le clic simple ouvre le synopsis avec un délai lié au minuteur.
7. **L'onglet Détails s'ouvre par défaut** alors que pour une série, l'action principale, ce sont les épisodes.
8. **Carte de bibliothèque** : le texte « Suivi des épisodes disponible » est figé et identique sur toutes les séries (`:1797`). La durée est vide. Le filtre « Disponible maintenant » dit « Films prêts… ». L'état vide dit « Aucun film… ».
9. Pour un non-admin, la bibliothèque Séries affiche un bandeau « demande à l'admin », mais l'application ne propose aucune action de demande.

---

## 3. Ce qui manque (par rapport à Netflix / Prime)

- **Reprendre** : aucun bouton « Reprendre S2:E5 ». La donnée existe pourtant : `list_next_episodes` (`store.py:1594`) sert déjà au tableau de bord.
- **Statistiques de la série** : saisons, épisodes vus/total, épisodes téléchargés/total, temps restant, statut TMDB (terminée / en production), prochain épisode diffusé, taille sur disque (admin).
- **Sélecteur de saison** (menu déroulant ou onglets) au lieu d'un accordéon.
- **Épisodes riches** : vignette 16:9, durée, date de diffusion, barre de progression de lecture, badge « À venir » pour les épisodes non diffusés.
- **Actions par saison** : « Tout marquer vu », « Télécharger la saison », avec un état visible (Complète, Partielle 8/22, Absente, En cours 45 %).
- **Note TMDB et métadonnées dans la bannière**, comme sur la fiche film.

Limite du modèle de données : la table `episode` ne contient que `season_number, episode_number, title, synopsis, watched`. Il manque `air_date`, `runtime`, `still_url` et `tmdb_episode_id`, et il n'y a pas de table `season` (affiche, nom, résumé).

---

## 4. Proposition de refonte

### 4.1 Structure de la fiche

```
┌───────────────────────────────────────────────────────────────┐
│  [IMAGE DE FOND pleine largeur, dégradé]                [✕]  │
│  PERSON OF INTEREST                                           │
│  2011–2016 · 5 saisons · Thriller, Drame · ★ 8.4 · Terminée   │
│  [▶ Reprendre S3:E07]  [＋ Watchlist]  [⇩ Télécharger ▾]  [↗] │
├───────────────────────────────────────────────────────────────┤
│  Vu 34/103 ███████░░░ 33 %   Dispo 87/103   ~52 h restantes   │
│  Prochain : S3:E07 « Mors Praematura »   (admin) 142 Go       │
├───────────────────────────────────────────────────────────────┤
│  [Saison 3 ▾]   22 épisodes · Partielle 18/22                 │
│                 [✓ Tout marquer vu]  [⇩ Télécharger la saison] │
│  ┌──────────┐ E07 · Mors Praematura · 43 min · 2013-11-05     │
│  │ vignette │ Synopsis sur deux lignes…                [▶]    │
│  │ ▓▓▓▓░░░░ │                                                 │
│  └──────────┘                                                 │
│  ┌──────────┐ E08 · …                      Non téléchargé [⇩] │
│  ┌──────────┐ E23 · …                      À venir · 12/12    │
├───────────────────────────────────────────────────────────────┤
│  À propos : synopsis, créateurs, casting, titre original,     │
│  outils admin (Actualiser TMDB, titre original)               │
└───────────────────────────────────────────────────────────────┘
```

Principes :
- **Un seul bouton principal**, qui change selon le contexte : *Reprendre SxEy* / *Commencer S1:E1* / *Demander* / *Téléchargement 45 %*.
- **Les épisodes d'abord**, la section « À propos » ensuite : plus d'onglets.
- **Le statut est calculé** à partir des épisodes vus. On garde seulement « Marquer la série comme vue » dans un menu « ⋯ ».
- On retire le bloc Support décoratif et les doublons.
- La bannière reprend la logique de repli de la fiche film. Ordre des sources pour l'image de fond : TMDB, puis Jellyfin (`backdrop_tag`), puis affiche floutée.

### 4.2 Téléchargement : série, saison ou épisode

Le menu **Télécharger ▾** propose :
- **Série entière** (avec ou sans les saisons à venir)
- **Choisir des saisons…** → liste de cases à cocher, avec l'état de chaque saison (Complète / Partielle / Absente)
- Au niveau de l'épisode : une icône **⇩** sur chaque ligne non téléchargée

Côté backend :
| Granularité | Mécanisme |
|---|---|
| Série / saisons | Seerr `POST /api/v1/request` avec `seasons: [1, 3]`, que Seerr accepte nativement. Corrige aussi le cas `future` → `[]`. |
| Épisode seul | **Seerr ne gère pas les épisodes.** Il faut passer par Sonarr directement : `PUT /api/v3/episode/monitor`, puis la commande `EpisodeSearch`. Il faut donc que Sonarr soit configuré en plus de Seerr. |

Droits des non-admins : **à décider** (voir §6).

### 4.3 Backend
1. **La synchro crée les épisodes.** Quand une série est créée ou liée sans épisodes, appeler `_fetch_tmdb_series_episodes` puis `upsert_episodes` (corrige B1a).
2. **Correspondance Jellyfin plus tolérante** : garder `Tvdb` et `Imdb` dans `list_library` et faire la correspondance sur TMDB, puis TVDB (via `external_ids` TMDB ou `tvdbId` Sonarr), puis IMDb (corrige B1b).
3. **Migration de la table `episode`** : ajouter `air_date`, `runtime`, `still_url` et `tmdb_episode_id`. Nouvelle table `season` (`media_id`, `season_number`, `name`, `poster_url`, `overview`). Le remplissage se fait au rafraîchissement TMDB.
4. **Nouvel endpoint `GET /series/{id}/overview`**, qui renvoie en une seule fois : statistiques, épisode suivant, disponibilité par saison, statut TMDB et prochaine diffusion.
5. **Demande d'acquisition** : `AcquisitionRequest` reçoit `seasons: list[int] | "all"` et `episode_ids: list[str]`.
6. **`_enrich_media`** remplit aussi l'image de fond quand seule celle-ci manque (corrige B2).

### 4.4 Front
- Sortir la fiche dans `components/SeriesDetailView.jsx`, ce qui allège aussi le fichier de 2 674 lignes.
- Carte de bibliothèque : vraie barre de progression, mention « S3:E07 suivant », badge de disponibilité Partielle/Complète.
- Corriger les libellés liés aux films (filtre, état vide) et unifier « Terminée ».

---

## 5. Découpage proposé

| Lot | Contenu | Taille |
|---|---|---|
| **1. Correctifs** | B1a (épisodes créés par la synchro), B1b (correspondance TVDB/IMDb), B2 (bannière + repli), doublons et libellés | S |
| **2. Refonte de la fiche** | Données de la migration épisodes/saisons, endpoint `overview`, nouvelle fiche (bannière, statistiques, sélecteur de saison, épisodes riches, Reprendre) | M-L |
| **3. Téléchargement granulaire** | Saisons via Seerr, épisodes via Sonarr, menu Télécharger, états par saison | M |
| **4. Bibliothèque** | Cartes série avec progression et disponibilité | S |

---

## 6. Décisions (validées le 22/11/2026)
1. **Granularité** : saison complète (cas le plus fréquent, packs de saison) **et** épisode seul. Saisons → Seerr `seasons: [..]` (ou Sonarr `SeasonSearch`) ; épisode → Sonarr direct (`episode/monitor` + `EpisodeSearch`).
2. **Non-admins** : peuvent **louer une saison** (même logique que la location de film, 21 jours, `rental_scope = "season"`).
3. **Statut manuel** : conservé, déplacé dans un menu « ⋯ » ; le statut affiché par défaut est celui calculé depuis les épisodes vus.
