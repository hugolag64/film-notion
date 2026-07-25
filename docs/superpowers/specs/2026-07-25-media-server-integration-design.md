# Intégration Sonarr, Radarr et Jellyfin

## Objectif

Faire de Backstage le cockpit d'un serveur média personnel installé sur le HP ProDesk. Backstage reste la bibliothèque, l'interface de découverte et le suivi de visionnage. Radarr et Sonarr gèrent les films et séries demandés ; Jellyfin sert les fichiers et la lecture.

La première livraison couvre l'ajout d'un média à Radarr ou Sonarr, le suivi de son acquisition, l'import des bibliothèques existantes, un lien de lecture Jellyfin et une page Activité. Elle ne configure pas les fournisseurs, indexeurs ou clients de téléchargement.

## Contraintes et sécurité

- Backstage, Radarr, Sonarr et Jellyfin tournent sur le même HP ProDesk.
- Backstage peut être consulté hors du réseau domestique, mais les API Radarr, Sonarr et Jellyfin ne sont pas exposées publiquement.
- Les URL internes, clés API et identifiants restent dans le fichier `.env` du serveur. Ils ne sont ni stockés en SQLite ni retournés par l'API HTTP vers le navigateur.
- L'accès externe doit passer par un accès privé (par exemple Tailscale) ou un reverse proxy authentifié. La configuration de cet accès est hors périmètre de Backstage.

## Configuration

Les variables suivantes sont optionnelles. En leur absence, les fonctions correspondantes sont désactivées et l'interface explique comment les activer.

```dotenv
RADARR_URL=http://127.0.0.1:7878
RADARR_API_KEY=...
SONARR_URL=http://127.0.0.1:8989
SONARR_API_KEY=...
JELLYFIN_URL=http://127.0.0.1:8096
JELLYFIN_API_KEY=...
MEDIA_SYNC_INTERVAL_SEC=60
```

Une page « Serveur média » teste chaque connexion et affiche uniquement : disponible/indisponible, version, profils de qualité, profils de langue et dossiers racines. Les clés ne sont jamais affichées.

## Architecture

### Clients distants

- `ArrClient` porte les requêtes HTTP, délais, erreurs normalisées et l'authentification API commune.
- `RadarrClient` récupère les profils et dossiers, ajoute un film à partir de son identifiant TMDB et lit l'état d'un film ou de la file d'attente.
- `SonarrClient` applique la même responsabilité aux séries, avec le choix du suivi (toutes les saisons ou saisons futures).
- `JellyfinClient` recherche un élément correspondant à l'identifiant TMDB, expose sa disponibilité et construit une URL de lecture. La progression Jellyfin est hors du MVP, mais les identifiants nécessaires sont conservés.

### Persistance

Les métadonnées éditoriales restent dans `media`. Une table séparée `media_availability` évite de surcharger le modèle `Media` et permet de conserver l'historique de synchronisation technique.

| Champ | Description |
|---|---|
| `media_id` | Référence unique au média Backstage |
| `provider` | `radarr` ou `sonarr` |
| `arr_id` | Identifiant du média dans Radarr/Sonarr |
| `jellyfin_id` | Identifiant Jellyfin, si le rapprochement existe |
| `state` | `requested`, `searching`, `downloading`, `imported`, `available`, `error` |
| `progress_percent` | Progression connue de la file, sinon vide |
| `root_folder` | Dossier racine logique sélectionné |
| `quality_profile_id` / `language_profile_id` | Profils réellement soumis au service |
| `last_error` | Dernière erreur non sensible à présenter à l'utilisateur |
| `last_synced_at` | Date de la dernière synchronisation réussie |

Un index unique sur `(provider, arr_id)` et les contrôles avant ajout empêchent les doublons. Le champ `support` est défini à `Serveur` lorsqu'un média est importé ; il ne doit pas effacer un autre support choisi manuellement sans confirmation.

## Flux utilisateur

1. Depuis une fiche déjà reliée à TMDB, « Ajouter au serveur » propose les profils disponibles, le dossier racine et le suivi applicable.
2. Backstage sélectionne Radarr pour un film ou Sonarr pour une série, puis envoie le TMDB ID.
3. Une disponibilité est créée avec l'état `requested`. L'interface affiche ensuite les états réels : demandé, recherche, téléchargement avec pourcentage, importé, disponible Jellyfin ou erreur.
4. Le service de synchronisation relève les données *arr toutes les 30 à 60 secondes et propose un rafraîchissement manuel.
5. Lorsqu'un import est terminé, Backstage recherche le média dans Jellyfin. Si le rapprochement réussit, il affiche « Lire » et ouvre la page ou la web-app Jellyfin de cet élément.
6. Une synchronisation initiale importe les éléments déjà connus de Sonarr et Radarr, puis les relie par TMDB ID aux fiches Backstage existantes ou crée une fiche locale minimale si nécessaire.

## Interface

- Fiche média : badge de disponibilité, bouton « Ajouter au serveur », panneau de paramètres, action « Actualiser », lien « Lire » quand Jellyfin le permet et message d'erreur actionnable.
- Fiche série : mêmes actions, plus le choix « toutes les saisons » ou « saisons futures ».
- Page Activité : demandes récentes, file de téléchargement, erreurs, imports récents et espace disque rapporté par les services quand disponible.
- Recherche : résultat marqué « possédé », « demandé » ou « disponible » selon `media_availability`.

## Gestion des erreurs

- Une API indisponible laisse les données locales intactes et affiche l'heure de la dernière synchronisation réussie.
- Les erreurs sont classées en configuration absente, service inaccessible, réponse invalide, doublon distant et échec de requête ; l'utilisateur reçoit un message simple sans clé ni détail sensible.
- Aucun appel de synchronisation ne peut modifier le statut de visionnage ou la note locale.
- Les appels distants ont des délais bornés et des nouvelles tentatives limitées afin que l'interface reste réactive.

## Tests et critères d'acceptation

- Ajouter un film appelle Radarr avec le TMDB ID, les profils et le dossier sélectionnés.
- Ajouter une série appelle Sonarr et respecte le choix de surveillance.
- Un média déjà présent dans le service distant n'est pas créé une seconde fois et est relié à sa fiche locale.
- Les transitions d'état de la file sont correctement traduites en états Backstage.
- L'import distant définit la disponibilité et propose `Serveur` sans détruire une valeur locale incompatible sans confirmation.
- Une indisponibilité Radarr, Sonarr ou Jellyfin produit un état et un message sûrs, sans fuite de secret.
- Un élément Jellyfin correspondant produit un lien de lecture ; son absence ne bloque pas le suivi *arr.
- La suite Python existante et la compilation Vite restent vertes.

## Hors périmètre du MVP

- Configuration des indexeurs, fournisseurs et clients de téléchargement.
- Exposition publique ou configuration réseau des services *arr.
- Retour automatique de progression de lecture Jellyfin et notifications de nouveaux épisodes.
- Règles avancées de stockage multi-emplacements et nettoyage automatisé.

Ces éléments seront la deuxième itération une fois l'intégration et les usages réels stabilisés.
