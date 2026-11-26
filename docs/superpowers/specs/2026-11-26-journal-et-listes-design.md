# Journal « Vu » et listes partagées — design

Date : 2026-11-26 · Statut : en relecture

## Intention

Backstage est la bibliothèque de films partagée entre colocs. Depuis le projet 1, **bibliothèque = films présents ou demandés sur le serveur**. Mais les colocs voient aussi des films ailleurs (surtout au cinéma) et veulent garder des films « à voir » (souvent des sorties en salle) sans qu'ils atterrissent sur le serveur.

Deuxième de cinq projets (précédent : bibliothèque nettoyée ; suivants : cinéma + agenda, social, quotidien).

Deux fonctions :
- **Journal « Vu »** : chacun note ce qu'il a vu, où qu'il l'ait vu. Il nourrit les recommandations.
- **Listes partagées** : des listes de films communes aux colocs (ex. « Films à voir au ciné »), indépendantes de la bibliothèque.

## Objectifs

- Noter un film vu (date, note, critique) même s'il n'est pas dans la bibliothèque, sans créer de fiche dans la bibliothèque.
- Journal **privé** : chaque coloc ne voit que le sien (décision de l'utilisateur).
- Listes **partagées** entre tous les colocs, contenant des films hors bibliothèque, avec proposition de demande Seerr à l'ajout.
- Les films du journal comptent comme « déjà vus » pour les recommandations.

## Non-objectifs

- Séries (le journal et les listes ne concernent que les films).
- Journal visible par les colocs, fil d'activité, recommander un film à un coloc (projet 4).
- Séances en salle, flux agenda ICS (projet 3) — mais la case « Vu au cinéma » et la liste « ciné » le préparent.
- Listes privées, réordonnancement manuel des films d'une liste.

## Anti-objectifs

- Un film ajouté au journal ou à une liste ne doit **jamais** apparaître dans la grille ou la rangée « En route » de la bibliothèque, sauf s'il est réellement sur le serveur ou demandé.
- Un coloc ne doit jamais voir le journal d'un autre (ni via l'API).

## Approches

- **A. Tables à part, films identifiés par leur id TMDB (retenue).** Nouvelles tables journal et listes ; titre, affiche, année et date de sortie copiés depuis TMDB. Rien n'entre dans la table `media`. Lien avec la bibliothèque par `tmdb_id`. Protège la bibliothèque par construction.
- **B. Lignes `media` marquées « hors bibliothèque ».** Réutilise `user_media_state`, mais chaque requête de la bibliothèque doit filtrer le drapeau : un oubli et des films de ciné réapparaissent dans la grille. Écartée.
- **C. Événements `already_seen` des recommandations.** Ni date, ni critique, ni listes. Écartée.

L'utilisateur a choisi A.

## Design

### Données

**Cache de films TMDB** (partagé) : `tmdb_id`, titre, année, `release_date`, affiche, genres. Rempli à l'ajout dans le journal ou une liste ; évite de rappeler TMDB à chaque affichage.

**Entrée de journal** : id, utilisateur, `tmdb_id`, date de visionnage (peut être vide), note sur 5 par demi-points (même échelle que la note actuelle), critique (facultative), « vu au cinéma » (booléen), date de création. Plusieurs entrées possibles pour le même film (revisionnage).

**Liste** : id, nom, créateur, date de création. **Film de liste** : liste, `tmdb_id`, ajouté par, date d'ajout ; un film n'apparaît qu'une fois par liste.

### Journal (privé)

- Page **Journal** dans le menu latéral, à côté de Films et Séries. Entrées groupées par mois, plus récentes d'abord ; les entrées sans date en fin, groupe « Date inconnue ».
  ```
  NOVEMBRE 2026
  [affiche] Dune 2  · 22/11 · ★★★★½ · 🎬
  [affiche] Heat    · 14/11 · ★★★★
  ```
- Ajouter une entrée : recherche TMDB depuis la page Journal ; bouton « Vu » sur un film de la bibliothèque ; bouton « Vu » sur un film d'une liste. Tous ouvrent la même fenêtre : date (aujourd'hui par défaut), note, critique, case « Vu au cinéma ».
- Modifier ou supprimer une entrée depuis la page Journal.
- Toutes les routes du journal ne renvoient que les entrées de l'utilisateur connecté (admin compris).

**Lien avec l'état « vu » existant** (`user_media_state` : statut « Terminé », note) — choix du designer, le journal est la source de vérité :
- Noter ou marquer vu un film de la bibliothèque, par le bouton « Vu » **ou** par l'ancien chemin (`PATCH /medias/{id}/personal` avec note ou statut vu), crée une entrée de journal datée du jour **et** met à jour `user_media_state` (statut « Terminé », note de l'entrée la plus récente). Les filtres actuels de la bibliothèque continuent de marcher sans réécriture.
- Pour l'affichage et les filtres de la bibliothèque, un film compte comme vu par l'utilisateur s'il a un état « Terminé » / une note **ou** au moins une entrée de journal avec le même `tmdb_id`. Ainsi un film du journal qui arrive plus tard sur le serveur apparaît directement « vu ».
- Modifier une entrée recopie sa note dans `user_media_state` si c'est l'entrée la plus récente. Supprimer la dernière entrée d'un film ne touche pas `user_media_state` (pas d'effacement implicite de l'historique ancien).
- Film de la bibliothèque sans `tmdb_id` : le bouton « Vu » tente de le relier à TMDB (même logique que `/medias/{id}/tmdb-rating`) ; en cas d'échec, seul `user_media_state` est mis à jour, comme aujourd'hui.

**Reprise de l'existant** (une fois, à la migration) — base réelle au 26/11 : 129 lignes `user_media_state`, 90 « Terminé », 94 notes ; 0 événement `already_seen`.
- Source : `user_media_state` ; en complément, pour le propriétaire du catalogue uniquement, `media.status` / `media.rating` quand il n'a pas de ligne `user_media_state` pour ce film (même repli que `_media_for_user`).
- Compte comme vu : statut « Terminé », « Terminée » ou « A revoir », ou une note non vide.
- Note : convertie avec `_rating_value` de `backend/core/recommendations.py` ; illisible → entrée sans note, texte brut ajouté à la critique.
- Date vide ; films sans `tmdb_id` ignorés. Idempotent : ne rien recréer si la migration repasse (une entrée reprise par utilisateur et film au plus).

**Recommandations** : les `tmdb_id` du journal de l'utilisateur rejoignent les ensembles « déjà vu » (`seen_tmdb_ids` et `hard_seen_tmdb_ids` dans `backend/api.py`, comme `already_seen`). La note d'un film hors bibliothèque ne nourrit pas encore le profil de goûts (v1) ; les genres sont stockés dans le cache pour le permettre plus tard. À l'inverse, cliquer « déjà vu » sur une recommandation crée une entrée de journal sans date ni note (choix du designer : le journal est « tout ce que j'ai vu »).

### Listes partagées

- Page **Listes** dans le menu latéral : toutes les listes avec leur nombre de films ; ouvrir une liste montre ses films.
- Tout coloc peut créer une liste, la renommer, ajouter ou retirer des films. Supprimer une liste demande une confirmation.
- Ajouter un film : recherche TMDB. Ensuite, si le film n'est ni sur le serveur ni déjà demandé, une fenêtre « Demander aussi sur le serveur ? » propose la demande Seerr (flux existant `POST /seerr/requests`). Refuser ne retire pas le film de la liste.
- Chaque film affiche qui l'a ajouté et un badge : « Sort le JJ/MM » (sortie future), « Au cinéma » (sortie il y a moins de `CINEMA_WINDOW_DAYS`), « Demandé » / état « En route », « Sur le serveur » (prêt sur Jellyfin, avec lecture possible). Réutilise la logique de `proto-ui/src/library.js`.
  ```
  FILMS À VOIR AU CINÉ · 4 films
  [affiche] Avatar 3 · Sort le 17/12 · ajouté par Léa
  [affiche] Dune 2   · Au cinéma    · ajouté par toi    ✓ Vu
  ```
- **Marque « Vu »** : si l'utilisateur connecté a au moins une entrée de journal pour ce film, le film porte « ✓ Vu » — visible par lui seul. Le film **reste dans la liste** (décision de l'utilisateur).

## Laissé au builder

- Noms des tables et des routes, découpage en modules (un module de logique testable côté UI, comme `library.js` / `rentals.js`, est recommandé).
- Disposition exacte des pages et de la fenêtre « Vu », dans le style existant (`#635bff`).
- Durée de vie du cache TMDB (rafraîchir la date de sortie d'un film à venir est utile pour le badge).

## À part

« Dans la ligne de mire » apparaît en double dans la bibliothèque : doublon probable en base, toujours à vérifier séparément.
