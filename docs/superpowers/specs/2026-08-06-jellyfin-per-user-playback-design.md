# Progression Jellyfin par utilisateur

## Objectif

Synchroniser la progression Jellyfin de chaque compte Backstage associé et afficher ses reprises de lecture dans Backstage.

## Périmètre de cette phase

Inclus :

- progression séparée pour chaque utilisateur Backstage ;
- lecture des éléments Jellyfin via le `jellyfin_user_id` déjà associé ;
- affichage de « Reprendre », « Prochain épisode » et « Récemment terminé » ;
- synchronisation manuelle et périodique ;
- conservation des données locales lors d’une erreur Jellyfin.

Exclus :

- modification des notes, favoris ou statuts locaux ;
- création ou suppression de comptes Jellyfin ;
- transmission de l’identité utilisateur au proxy HLS actuel ;
- notifications et règles de stockage temporaire.

## Architecture

Ajouter une table `playback_progress` indexée par `(backstage_user_id, jellyfin_id)`. Elle conserve l’élément Jellyfin, le média ou l’épisode local correspondant, la position, la durée, le pourcentage, le statut terminé, la date de dernière lecture et la date de synchronisation.

`JellyfinClient` reçoit un `user_id` pour appeler les endpoints `/Users/{user_id}/Items`. Les données sont réduites côté serveur et rapprochées par identifiant Jellyfin, puis par TMDB et informations de saison/épisode.

Le scheduler parcourt uniquement les utilisateurs Backstage actifs possédant un `jellyfin_user_id`. Les routes authentifiées `POST /api/playback/sync` et `GET /api/playback/summary` travaillent sur l’utilisateur connecté.

## Interface

La page d’accueil affiche les cartes de progression de l’utilisateur connecté. Chaque carte indique le titre, le pourcentage et l’action de lecture existante. Les sections sans résultat ne sont pas affichées. Un compte non associé voit un état vide explicite, sans erreur technique.

## Règles

- Un élément est terminé si Jellyfin le signale lu ou si sa progression atteint 95 %.
- Une synchronisation distante en erreur conserve les données déjà enregistrées.
- Une synchronisation ne modifie jamais les notes, favoris ou statuts locaux.
- Les données d’Hugo et d’Ophélie ne doivent jamais être mélangées.
- Le proxy HLS continuera temporairement à fonctionner comme aujourd’hui ; la transmission d’une identité Jellyfin au lecteur fera l’objet d’une phase dédiée.

## Vérification

Tester la persistance multi-utilisateur, le rapprochement film/épisode, le seuil de 95 %, le prochain épisode, l’isolation entre utilisateurs, les erreurs Jellyfin, les routes authentifiées et le rendu frontend.
