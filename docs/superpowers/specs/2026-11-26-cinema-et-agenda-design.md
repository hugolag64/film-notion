# Cinéma et agenda — design

Date : 2026-11-26 · Statut : en relecture

## Intention

Les colocs repèrent des films parfois un an avant leur sortie et les rangent dans les listes partagées (projet 2). Le risque, c'est de **rater le film en salle** : il sort, passe deux ou trois semaines au cinéma, et disparaît. Le projet 3 fait en sorte qu'on n'oublie pas d'aller le voir au **Multiplexe Ciné Grand Sud (Saint-Pierre, La Réunion)**, le seul cinéma suivi.

Troisième de cinq projets (précédents : bibliothèque nettoyée, journal et listes ; suivants : social, quotidien).

Trois fonctions :
- **Agenda ICS** : un abonnement qui met dans l'agenda de chacun la date de sortie des films suivis.
- **Rappels dans le tchat** : un bot « Ciné » prévient le salon quand un film suivi arrive au Grand Sud, et quand il en est à ses dernières séances.
- **Bot `@ciné`** : dans le tchat, on lui demande les films à l'affiche et leurs horaires.

## Objectifs

- Un flux ICS par utilisateur (adresse secrète), avec **un événement d'une journée par film suivi, à sa date de sortie**, et rien d'autre (décision de l'utilisateur).
- La date de l'événement s'affine : d'abord la date de sortie **française** en salle (TMDB), puis la date de sortie **à La Réunion** dès que cine-reunion.com la donne.
- Le bot poste dans le salon, une seule fois par film :
  - à l'arrivée d'un film suivi dans la programmation du Grand Sud ;
  - quand un film suivi en est à ses dernières séances (« A + C », décision de l'utilisateur).
- Commandes du bot :
  - `@ciné films` : les films à l'affiche, sous forme de **boutons**. Un clic affiche les horaires du film sous le message, uniquement pour celui qui clique (décision de l'utilisateur : on clique au lieu de taper, pour ne pas se tromper de titre).
  - `@ciné ce soir` et `@ciné demain` : les séances du jour (à partir de maintenant) ou du lendemain.
  - `@ciné aide` : la liste des commandes.
- Une aide visible sans rien taper : un bouton 🎬 à côté de la zone de saisie du tchat ouvre la liste des commandes ; un clic sur une commande la met dans la zone de saisie (décision de l'utilisateur : « une petite aide pour qu'on ait les commandes quelque part »).

## Non-objectifs

- Autres cinémas (Cambaie, Lacaze) : uniquement le Grand Sud (décision de l'utilisateur).
- Séances dans l'agenda ICS : seulement la date de sortie (décision de l'utilisateur).
- IA ou langage libre dans le bot : commandes fixes uniquement (décision de l'utilisateur ; une IA pourra se brancher plus tard).
- Réservation, prix, disponibilité des places : le bot donne le lien de réservation du site, rien de plus.
- Séries.
- Correction manuelle d'une mauvaise association film du site ↔ TMDB.

## Anti-objectifs

- Le bot ne doit **jamais donner un horaire faux**. Si la dernière lecture réussie du site date de plus de 2 jours, il le dit au lieu de répondre avec des données périmées.
- Pas de bruit : jamais deux fois le même rappel pour un même film, et pas de rappel pour un film qui n'est dans aucune liste.
- Le tchat ne doit pas casser si le site est injoignable ou change de mise en page. Les commandes répondent « horaires indisponibles », et les messages des humains passent toujours.
- Les films du site n'entrent **jamais** dans la bibliothèque, comme pour les listes.
- Aucun test et aucun essai ne touche le vrai serveur (port 8090, vraie base) ni le vrai site pendant les tests automatisés.

## Approches

- **1. Backstage fait tout lui-même (retenue).** Une tâche quotidienne lit les pages du Grand Sud, garde films et séances en base et les relie à TMDB. Le bot répond côté serveur, l'ICS est une route de l'API. Aucun service en plus ; s'appuie sur le planificateur, le client TMDB, les listes et le tchat existants. Point fragile : un changement de mise en page du site casse la lecture. Un test sur des pages enregistrées et le message « horaires indisponibles » limitent les dégâts.
- **2. changedetection.io surveille la page.** Il signale un changement, mais Backstage doit quand même lire et découper la page. Ça fait un service de plus pour la partie la plus facile. Écartée.
- **3. Bot côté interface uniquement.** Les réponses ne seraient vues que par celui qui tape, et les rappels ont de toute façon besoin du serveur. Écartée.

L'utilisateur a choisi la 1.

## Ce qu'on sait du site (relevé le 2026-11-26)

- La programmation est rendue côté serveur, en HTML : `https://cine-reunion.com/programmation/multiplexe-cine-grand-sud-saint-pierre/`.
  - Pour chaque film : un lien `/film/<slug>/<id>/` (l'`id` numérique identifie le film sur le site), l'affiche, la durée, puis des blocs par jour (« vendredi 27 novembre 2026 »).
  - Chaque séance donne l'heure, la version (`VF`, `VOST`, parfois suivie de `3D`) et un lien de réservation `ticketingcine.com`.
  - La programmation couvre environ 6 jours en détail, plus quelques avant-premières lointaines.
- Une page film (`/film/<slug>/<id>/`) donne : titre original, réalisateur, « Sortie nationale » et « Sortie à La Réunion » (dates en toutes lettres).
- `https://cine-reunion.com/films/prochaines-sorties/` liste une vingtaine de films à venir, avec des liens `/film/<slug>/<id>/`.
- Aucun flux RSS, ICS ou JSON.
- Les heures sont des heures de La Réunion (`Indian/Reunion`, UTC+4).

## Conception

### Films suivis

Un film est **suivi** s'il est dans au moins une liste partagée (`film_list_items`). Il n'y a pas de liste « ciné » dédiée (décision de l'utilisateur). Ce choix ne crée pas de bruit :
- dans le tchat, le bot ne parle que des films réellement programmés au Grand Sud ;
- dans l'agenda, on ne garde que les sorties en salle.

### Lecture du site

- Une tâche tourne **une fois par jour**, avec son propre tour de boucle dans `backend/core/scheduler.py`, indépendant de la synchronisation des serveurs média. Elle lit :
  - la page de programmation du Grand Sud ;
  - la page « Prochaines sorties » ;
  - la page de chaque film pas encore connu en base.
- Adresse de base configurable (`CINEMA_BASE_URL`, par défaut `https://cine-reunion.com`), pour que le bac à sable puisse la pointer sur `127.0.0.1:9`. On peut désactiver la tâche (`CINEMA_ENABLED`).
- User-Agent générique (« Backstage »), aucune donnée personnelle. Les pages film déjà connues ne sont pas relues, sauf si la date de sortie à La Réunion manque encore.
- **Une lecture qui échoue ne détruit rien.** Une programmation lue sans aucun film compte comme un échec (mise en page changée). Les séances en base ne sont remplacées qu'après une lecture complète réussie de la programmation. On garde la date de la dernière lecture réussie.
- Le découpage HTML est isolé dans un module pur (HTML en entrée, données en sortie), testé sur des copies enregistrées des vraies pages.

### Association avec TMDB

Pour chaque film du site, on cherche l'id TMDB :
1. On interroge TMDB avec le titre original, dans l'année de la sortie nationale.
2. On compare le réalisateur.
3. À défaut, on prend le premier résultat dont l'année correspond.

On garde le résultat, y compris « pas trouvé ». Un film « pas trouvé » est retenté au plus une fois par semaine. Un film sans id TMDB apparaît quand même dans `@ciné films` et `@ciné ce soir`, mais ne peut pas être « suivi ».

### Données

Nouvelles tables, noms au choix du constructeur :
- **films du site** : id du site, titre, titre original, réalisateur, sortie nationale, sortie à La Réunion, affiche, URL, id TMDB (nullable), date de la dernière tentative d'association ;
- **séances** : id du film sur le site, date et heure locales, version, lien de réservation ;
- **rappels envoyés** : film, type (`arrivee` ou `fin`), date. C'est ce qui empêche les doublons ;
- **état de la lecture** : date de la dernière lecture réussie, dernière erreur.

Côté agenda, il faut la date de sortie française en salle de chaque film suivi. On la tire de `release_dates` (pays `FR`, type 3 « Theatrical » ou, à défaut, 2 « Theatrical (limited) »), déjà demandé par `get_movie_details`. Le cache `tmdb_movie_cache` gagne une colonne pour cette date, et une date de rafraîchissement : `ensure_cached_movie` ne rafraîchit jamais, il faut donc un rafraîchissement explicite. La tâche quotidienne rafraîchit les films suivis dont la sortie est à venir ou inconnue, au plus une fois par semaine par film : les dates bougent souvent un an à l'avance.

### Rappels dans le tchat

- **Fenêtre des rappels** *(appel du constructeur de la conception)* : les rappels ne regardent que les séances des **7 prochains jours** (la programmation détaillée). Les avant-premières plus lointaines apparaissent dans `@ciné films` et dans les horaires d'un film, mais ne déclenchent aucun rappel et n'allongent pas la fenêtre utilisée pour « dernières séances ». Sinon, une avant-première lointaine consommerait « arrivée » puis « fin » avant la vraie sortie.
- **Arrivée** : la première fois qu'un film suivi a au moins une séance dans la programmation lue. Le message dit le titre et sa première séance, par exemple « 🎬 *Dune 3* arrive au Grand Sud : première séance mercredi 2/12 à 20:00 ». Il porte un bouton pour voir les horaires.
- **Dernières séances** : quand un film suivi a des séances dans la fenêtre, mais que la fenêtre lue s'étend **au moins 2 jours** après sa dernière séance, alors que d'autres films ont des séances ces jours-là. Le message ressemble à « ⏳ Dernières séances de *Dune 3* au Grand Sud : jusqu'à mardi 8/12 ». Le site n'annonce pas les fins d'exploitation, donc c'est le meilleur signal disponible. Une même lecture ne doit pas produire « arrivée » et « fin » pour un même film.
- **Une seule fois par film et par type**, enregistré dans les rappels envoyés.
- **Le premier passage ne poste rien pour l'arrivée** : il enregistre les films déjà programmés comme « arrivée déjà annoncée », pour éviter une rafale au déploiement. La règle « dernières séances » s'applique normalement dès la lecture suivante *(appel de la conception : un film vraiment en fin de course au déploiement mérite son avertissement, et il y en a peu)*.

### Bot `@ciné`

- **Message du bot** : il est stocké comme un message du tchat dont l'auteur est le bot (id réservé, par exemple `bot:cine`, nom « Ciné »). La table `chat_messages` gagne une colonne `payload` (JSON, nullable) qui décrit les boutons :
  - liste de films (id du site, titre, et un indicateur « dans vos listes ») ;
  - aide (liste des commandes).
- **Déclenchement** : quand un message posté commence par `@ciné` ou `@cine` (sans tenir compte de la casse), le serveur enregistre le message de l'humain normalement, puis la réponse du bot. Les deux sont visibles par tout le salon. Une commande inconnue renvoie l'aide.
- **Commandes** :
  - `films` : les films ayant au moins une séance à venir, ceux des listes marqués d'une ★ ;
  - `ce soir` : les séances du jour dont l'heure n'est pas passée, groupées par film ;
  - `demain` : les séances du lendemain, groupées par film ;
  - `aide` : la liste des commandes.

  « Aujourd'hui » se calcule à l'heure de La Réunion (`Indian/Reunion`, fixé, car lié au cinéma, et non `RECOMMENDATION_TIMEZONE`).
- **Clic sur un film** : une route renvoie ses séances à venir, groupées par jour, avec version et lien de réservation. L'interface les affiche sous le message, **pour celui qui a cliqué seulement**. Rien n'est posté.
- **Données périmées** : si la dernière lecture réussie date de plus de 2 jours, toutes les réponses le disent (« Horaires indisponibles depuis le 24/11 ») au lieu d'afficher des séances.
- **Aide visible** : un bouton 🎬 à côté du bouton emoji ouvre la liste des commandes avec une phrase d'explication chacune ; un clic sur une commande la met dans la zone de saisie.

### Agenda ICS

- **Adresse** : `GET /api/cinema/agenda.ics?token=…`, sans session. Elle doit donc vivre hors du routeur principal, qui impose la connexion sur toutes ses routes, car les applis d'agenda ne savent pas se connecter. Chaque utilisateur a son jeton. Le régénérer invalide l'ancienne adresse.
- **Où on l'obtient** : sur la page Listes, un bouton « Ajouter à mon agenda » montre l'adresse avec un bouton « Copier » et un bouton « Régénérer ».
- **Contenu** : le même pour tout le monde, puisque les listes sont partagées. Un `VEVENT` d'une journée par film suivi :
  - date : la sortie à La Réunion si le site la connaît, sinon la sortie française en salle de TMDB ;
  - `UID` stable par film, pour qu'un changement de date déplace l'événement au lieu d'en créer un autre ;
  - titre : « 🎬 Titre — sortie au cinéma » ;
  - description : « Au Grand Sud » quand la date vient du site, sinon « Date France, à confirmer pour La Réunion ».
- **Quels films** : sortie dans les 12 derniers mois ou à venir. Pas d'événement pour un film sans date de sortie en salle, ni pour un film qui ne sort qu'en streaming.
- **Format** : RFC 5545 valide (fin de ligne CRLF, lignes repliées à 75 octets, caractères spéciaux échappés), en `text/calendar; charset=utf-8`.

## Contraintes

- Stack existante : FastAPI, `MediaStore` SQLite (méthodes synchrones enveloppées par `asyncio.to_thread`), interface React dans `proto-ui`, client TMDB `backend/core/tmdb.py`.
- Pas de nouvelle dépendance Python si l'analyseur HTML de la bibliothèque standard suffit. Au choix du constructeur, à justifier s'il en ajoute une.
- Conserver les fins de ligne existantes : CRLF pour `backend/api.py`, `backend/core/store.py`, `backend/core/models.py`, `main.py`, `proto-ui/src/api.js`, `proto-ui/src/library.js` ; LF pour les nouveaux fichiers.
- Tests :
  - Python : `.venv/Scripts/python.exe -m pytest`. Les 11 échecs déjà présents sur `main` (`test_auth_api` ×8, `test_auth_store` ×2, `test_catalogue_playback_ui` ×1) restent les seuls.
  - Interface : `npm --prefix proto-ui test`.
- Les tests de découpage utilisent des copies enregistrées des pages, déjà capturées le 2026-11-26 dans `tests/fixtures/cinema/` (programmation du Grand Sud, page du film *Camembert*, prochaines sorties ; pages publiques, sans donnée personnelle). Jamais le vrai site pendant les tests. Le constructeur peut capturer à la main une page de plus si un cas manque.
- Essais manuels uniquement sur une copie de la base, port 8091, intégrations pointées sur `127.0.0.1:9`.

## Laissé au constructeur

- Noms des tables, des modules et des routes, sauf l'adresse ICS ci-dessus.
- Mise en page exacte des boutons de films et du panneau d'horaires dans `ChatDock.jsx`, dans le style existant du tchat.
- Comment la réponse du bot arrive au client : renvoyée par le POST, ou récupérée par l'interrogation périodique déjà en place.
- Heure de la tâche quotidienne : au démarrage, puis toutes les 24 h, suffit.
