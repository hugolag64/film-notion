# Phase 1 — Synchronisation complète du serveur média

## Objectif

Finaliser le cœur Sonarr/Radarr/Jellyfin : synchroniser les bibliothèques et files réelles, créer les fiches Backstage manquantes, représenter les états d'acquisition et rendre ces informations visibles dans la bibliothèque React.

## Synchronisation

Une synchronisation lit les bibliothèques Radarr/Sonarr, leurs queues et leurs informations disque. Elle lie les médias par type et TMDB ID. Un élément distant absent de Backstage crée une fiche locale minimale, complétée via TMDB ; une série reçoit également ses épisodes TMDB.

La conversion des états est : queue sans progression `searching`, queue avec progression `downloading`, erreur de queue `error`, fichier *arr importé `imported`, correspondance Jellyfin `available`, demande soumise sans autre état `requested`.

## Interface

- Cartes et résultats TMDB : badge `Possédé`, `Demandé` ou `Disponible`.
- Modal d'acquisition : profils qualité/langue, dossier et monitor Sonarr `all` ou `future`.
- Fiches Film et Série : badge courant, action d'actualisation et bouton Jellyfin si disponible.
- Activité : queue, erreurs, imports récents et espace libre par service.

## Contraintes

- La synchronisation ne modifie jamais note, avis ou progression locale.
- Une erreur distante conserve le dernier état valide et fournit un message sans secret.
- La progression Jellyfin, les notifications, watchlists intelligentes et emplacements multiples restent hors phase 1.

## Vérification

- Tests des transitions requested/searching/downloading/imported/available/error.
- Tests de création idempotente d'un film et d'une série distants inconnus.
- Tests des payloads Sonarr `all` / `future` et des réponses d'activité.
- Suite Python et build/lint Vite verts.
