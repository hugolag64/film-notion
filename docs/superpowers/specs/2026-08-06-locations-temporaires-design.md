# Locations temporaires — Design V1

## Objectif

Permettre à chaque utilisateur de louer temporairement jusqu’à cinq films simultanément, avec une durée lisible et une demande de conservation, sans supprimer automatiquement de fichiers tant que le disque de sauvegarde n’est pas installé et testé.

## Périmètre V1

- Les locations concernent les films uniquement.
- Chaque location appartient à un compte Backstage.
- Un utilisateur peut avoir au maximum cinq locations actives.
- Un même utilisateur ne peut pas créer deux locations actives pour le même film.
- Les séries temporaires sont hors périmètre.
- La suppression automatique est désactivée.
- Les décisions administratives de conservation sont préparées mais leur tableau de bord complet reste une étape ultérieure.

## Règles métier

Une location active est dans l’un des états suivants : `requested`, `downloading`, `available` ou `keep_requested`. Ces états comptent dans la limite de cinq films.

Une location passe en `available` lorsque Jellyfin confirme que le film est disponible. À ce moment, `available_at` est renseigné et `expires_at` est fixé à 21 jours.

Lors de la première lecture du film par l’utilisateur concerné, `first_played_at` est renseigné et `expires_at` est recalculé à sept jours à partir de cette première lecture.

Le bouton « Demander à conserver » passe la location en `keep_requested` et suspend toute évolution automatique de l’expiration. Aucune suppression n’est exécutée en V1.

Une location `kept` ne compte plus dans le quota. Les états `expired` et `cancelled` ne comptent plus non plus lorsqu’ils seront ajoutés par le cycle de nettoyage futur.

## Modèle de données

Ajouter une table `media_rentals` :

- `id` : identifiant UUID de la location ;
- `media_id` : film concerné ;
- `backstage_user_id` : utilisateur propriétaire ;
- `status` : état métier ;
- `requested_at` : date de demande ;
- `available_at` : première date de disponibilité Jellyfin ;
- `first_played_at` : première lecture par cet utilisateur ;
- `expires_at` : date d’expiration courante ;
- `keep_requested_at` : date de demande de conservation ;
- `created_at` et `updated_at` : dates techniques.

Créer un index unique partiel empêchant deux locations actives pour le même couple utilisateur/film. Le quota est calculé sur les états actifs définis plus haut.

## Flux applicatif

1. L’utilisateur demande un film absent.
2. Backstage vérifie le quota et l’absence d’une location active identique.
3. Seerr/Radarr reçoit la demande.
4. Backstage crée la location en `requested`.
5. La synchronisation Radarr/Jellyfin met à jour la location en `available` et fixe l’expiration à 21 jours.
6. La synchronisation de lecture détecte la première lecture de cet utilisateur et ramène l’expiration à sept jours.
7. L’utilisateur peut demander la conservation ; la location passe en `keep_requested`.

## API

- `GET /api/rentals` : retourne les locations de l’utilisateur connecté ; un administrateur peut demander une vue globale ultérieurement.
- `POST /api/medias/{media_id}/acquisition` : vérifie le quota et crée la location liée à la demande.
- `POST /api/rentals/{rental_id}/keep` : demande la conservation de la location de l’utilisateur connecté.

Les routes vérifient systématiquement l’utilisateur courant. Un utilisateur ne peut ni lire ni modifier la location d’un autre compte.

## Interface

Dans la fiche d’un film :

- afficher l’état de la location personnelle ;
- afficher la date d’expiration lorsqu’elle existe ;
- afficher « Demander à conserver » pour une location `available` ;
- remplacer le bouton de demande serveur par l’état de la location lorsque celle-ci existe.

Le quota personnel de cinq films sera affiché dans la navigation ou le panneau de compte. Le suivi global des téléchargements reste réservé aux administrateurs.

## Sécurité et données

- Les dates sont stockées en UTC.
- Les permissions sont appliquées côté API, pas uniquement dans React.
- Aucune suppression de fichier ou appel de suppression Radarr n’est introduit dans cette V1.
- La migration SQLite doit être additive et conserver les locations existantes lorsqu’une mise à jour est redéployée.

## Tests d’acceptation

- Un utilisateur avec cinq locations actives reçoit une erreur 409 à la sixième demande.
- Deux demandes du même utilisateur pour le même film ne créent pas deux locations.
- Deux utilisateurs peuvent louer le même film et possèdent chacun leur expiration.
- Une disponibilité Jellyfin crée `available_at` et une expiration à 21 jours.
- La première lecture de l’utilisateur réduit l’expiration à sept jours.
- La demande de conservation passe en `keep_requested` sans supprimer de fichier.
- Un utilisateur ne peut pas consulter ou modifier la location d’un autre utilisateur.
- Un administrateur peut consulter les locations globales dans une étape ultérieure.
