# Synchronisation Jellyfin-Backstage et uniformisation des fiches — Conception

**Date :** 2026-08-08  
**Statut :** Validée par l’utilisateur

## Objectif

Faire de Jellyfin la source de vérité des films et séries réellement présents dans le stockage, afin que Backstage relie automatiquement les fiches existantes, crée les fiches absentes et reflète correctement leur disponibilité. En parallèle, remplacer la fiche série latérale par la même expérience centrée que la fiche film.

## Décisions

- Jellyfin est la source de vérité de la présence physique d’un média.
- Le rapprochement se fait par `ProviderIds.Tmdb` quand il est disponible.
- Une fiche Backstage absente est créée automatiquement puis enrichie par TMDB.
- Une présence Jellyfin force l’état de disponibilité à `available` et conserve le `jellyfin_id`.
- Radarr/Sonarr restent les sources des demandes, de la file de téléchargement et des erreurs d’acquisition.
- Le profil Radarr par défaut est `1080 FR - max 10go`.
- Les utilisateurs non-admin ne voient/utilisent que ce profil ; les admins conservent le choix des profils exposés par le service.
- La synchronisation périodique utilise l’intervalle existant de 60 secondes par défaut.

## Architecture et flux de données

### 1. Découverte Jellyfin

Ajouter au client Jellyfin une lecture paginée des éléments de type `Movie` et `Series`, avec les champs nécessaires : `ProviderIds`, `Name`, `ProductionYear`, `Overview`, `ImageTags`, `BackdropImageTags` et les identifiants de l’élément. La réponse est normalisée en éléments de bibliothèque contenant au minimum :

```text
jellyfin_id, tmdb_id, title, media_type, year, overview, poster/backdrop metadata
```

Les éléments dépourvus de TMDB ID sont ignorés par la création automatique mais restent journalisés comme non rapprochables ; ils ne doivent pas produire de doublons par titre approximatif.

### 2. Réconciliation locale

Ajouter une opération de synchronisation de bibliothèque qui :

1. lit les bibliothèques Jellyfin ;
2. recherche une fiche locale avec le même type et `tmdb_id` ;
3. crée la fiche si nécessaire avec les métadonnées TMDB disponibles ;
4. met à jour les métadonnées manquantes sans écraser les modifications éditoriales locales ;
5. crée ou met à jour `Availability` avec `state="available"`, le fournisseur correspondant et le `jellyfin_id` ;
6. marque le support local comme `Serveur` ;
7. rend disponibles les locations actives de ce média ;
8. continue ensuite à synchroniser Radarr/Sonarr pour les médias suivis par Arr.

La présence Jellyfin est prioritaire sur les états Arr. Un élément présent dans Arr mais absent de Jellyfin reste `imported` si `hasFile` est vrai, ou garde son état de téléchargement/recherche. Une erreur de service ne doit pas effacer le dernier état persistant.

### 3. Déclencheurs

La synchronisation complète est exécutée :

- au démarrage de la boucle média ;
- toutes les `MEDIA_SYNC_INTERVAL_SEC` secondes, 60 par défaut ;
- après une demande d’acquisition ou un import manuel ;
- via les contrôles d’administration existants ;
- au chargement et au retour sur la bibliothèque côté frontend, via une route authentifiée de synchronisation ciblée ou complète selon les permissions.

La lecture d’une fiche peut demander une synchronisation ciblée lorsque sa dernière disponibilité est absente ou trop ancienne. Le frontend doit ensuite recharger les médias et la disponibilité pour refléter immédiatement la transition.

### 4. Route et permissions

La synchronisation complète reste une opération d’administration. Les utilisateurs non-admin doivent néanmoins bénéficier de l’état déjà synchronisé et d’une synchronisation ciblée, limitée au média demandé, sans accès aux informations d’activité globale, aux disques ou aux paramètres d’administration.

Les options d’acquisition retournent explicitement le profil par défaut. Pour un utilisateur non-admin, l’API doit filtrer le choix au profil `1080 FR - max 10go` et rejeter côté serveur toute autre valeur même si elle est forgée côté navigateur. Pour un admin, le profil par défaut est présélectionné mais les autres profils restent sélectionnables.

## Interface utilisateur

### Fiche série

Le panneau latéral actuel des séries est remplacé par le conteneur de `FilmDetailView` : overlay centré, mêmes dimensions maximales, même gestion de fermeture, même traitement du thème et même responsive.

La fiche série reprend les blocs de la fiche film :

- hero avec backdrop, dégradé, badge `FICHE SÉRIE`, titre, créateur et année ;
- statut personnel et support de stockage ;
- état serveur avec lecture, disponibilité, progression ou demande ;
- note personnelle et note TMDB ;
- pied de fiche et actions communes.

La spécificité série est conservée au centre dans deux onglets `Détails` et `Épisodes`. Les saisons, épisodes, progressions et actions de visionnage sont déplacés dans ce flux sans modifier les règles métier existantes.

### Bibliothèque

Films et séries utilisent la même disponibilité synchronisée pour les pastilles, l’état de la carte et l’action principale. Les textes et actions varient uniquement selon le type (`Demander ce film` / `Demander cette série`) et les contrôles propres aux épisodes.

## Gestion des erreurs et cohérence

- Une panne de Jellyfin, Radarr ou Sonarr est journalisée et ne supprime pas les fiches ni la dernière disponibilité connue.
- Un média Jellyfin sans TMDB ID n’est pas créé automatiquement et apparaît dans les logs de synchronisation avec une raison explicite.
- Les doublons sont évités par le couple `(type, tmdb_id)`.
- Les locations ne sont marquées disponibles que lorsque Jellyfin fournit un identifiant exploitable.
- Les rafraîchissements frontend sont annulables afin d’éviter qu’une réponse obsolète remplace une disponibilité plus récente.

## Tests

### Backend

- listing Jellyfin paginé et normalisation des films/séries ;
- création d’une fiche absente depuis un élément Jellyfin ;
- liaison d’une fiche existante sans doublon ;
- enrichissement TMDB des fiches créées ;
- passage `requested`/`imported` à `available` grâce à Jellyfin ;
- priorité de Jellyfin sur un état Arr obsolète ;
- conservation de l’état en cas d’erreur distante ;
- mise à jour des locations disponibles ;
- filtrage et validation serveur du profil `1080 FR - max 10go` ;
- permissions de synchronisation ciblée et complète.

### Frontend

- appel de synchronisation puis rechargement du catalogue après action serveur ;
- rafraîchissement périodique nettoyé au démontage ;
- pastille et action de carte alimentées par la disponibilité à jour ;
- série rendue dans `FilmDetailView` centré ;
- onglets détails/épisodes conservés ;
- fermeture par clic extérieur, Échap et bouton ;
- formulaire d’acquisition présélectionné et filtré selon le rôle.

## Hors périmètre

- écoute temps réel native des webhooks Radarr/Sonarr/Jellyfin ;
- recherche approximative par titre pour les éléments sans TMDB ID ;
- refonte des règles de location, des épisodes ou du lecteur vidéo ;
- modification des données éditoriales locales déjà renseignées par un utilisateur.
