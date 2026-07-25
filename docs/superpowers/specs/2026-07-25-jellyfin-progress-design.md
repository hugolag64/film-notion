# Phase 2.1 — Reprise de lecture Jellyfin

## Objectif

Synchroniser la progression du compte Jellyfin unique vers Backstage afin d'afficher les médias à reprendre, le prochain épisode et les lectures récemment terminées.

## Données et synchronisation

Une table `playback_progress` associe un média Backstage à un élément Jellyfin et conserve la position, durée, pourcentage, dernière lecture et statut terminé. Le client Jellyfin lit les éléments utilisateur en cours et récemment lus ; Backstage les rapproche prioritairement par `jellyfin_id`, puis par TMDB ID.

La synchronisation est périodique et manuelle. Une erreur Jellyfin conserve les données locales et l'heure de dernière synchronisation valide. Elle ne modifie jamais notes, favoris ou note personnelle.

## Interface

- Liste `Reprendre` : films et épisodes dont la lecture est incomplète, avec progression et action Jellyfin.
- Liste `Prochain épisode` : premier épisode non terminé de chaque série en cours.
- Liste `Récemment terminé` : médias dont Jellyfin a confirmé la fin de lecture.
- Une fiche média affiche la progression et la date de dernière lecture lorsque disponibles.

## Règles

- Un élément est terminé lorsque Jellyfin le signale comme lu ou que sa progression atteint 95 %.
- Le prochain épisode respecte l'ordre saison/épisode et ignore les épisodes spéciaux.
- La phase ne gère qu'un compte Jellyfin ; les notifications et les règles de stockage restent hors périmètre.

## Vérification

- Tests de rapprochement, reprise, seuil de 95 %, séries et échec distant.
- Tests de requêtes API et compilation/lint React.
