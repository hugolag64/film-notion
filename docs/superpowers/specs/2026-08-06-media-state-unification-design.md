# Unification des états média

## Objectif

Garantir qu’une action effectuée dans la fiche film se reflète immédiatement dans la vue générale, et que la présence sur le serveur soit visible de la même manière dans la fiche et dans les cartes.

## Règles métier

- Une note personnelle non vide implique le statut `Terminé` pour l’utilisateur concerné.
- Un film téléchargé par Radarr ou déjà présent dans Jellyfin reçoit l’emplacement `Serveur`.
- `À regarder` désigne les films non vus.
- `Watchlist` est une sélection volontaire, indépendante du statut de visionnage et personnalisée par utilisateur.
- La note et la présence serveur ne doivent jamais être déduites uniquement de l’état visuel local.

## Source de vérité et flux UI

Le backend renvoie l’état canonique du média. Après une modification personnelle, la fiche et la collection remplacent toutes deux leur objet local par la réponse canonique du backend. `selectedMovie` est une projection de l’élément présent dans `movies`, et non une seconde copie métier indépendante.

La disponibilité serveur reste un état technique séparé pour la lecture et les badges de progression. Lorsqu’elle indique un film importé ou disponible, le média canonique est rechargé afin que `support` et la carte générale indiquent également `Serveur`.

## Interface

- Les boutons de statut de la fiche pilotent le même état que les filtres de la collection.
- Le bouton de note met à jour le statut visible dans la fiche, la carte et le filtre `Films vus`.
- Le support `Serveur` apparaît dans la fiche et dans les cartes après synchronisation serveur.
- La Watchlist utilise un indicateur personnel indépendant ; son compteur et son filtre ne reposent pas sur le statut `À regarder`.

## Vérification

- Tests backend pour note → `Terminé`, Watchlist indépendante et support serveur.
- Build et lint de l’interface.
- Vérification que la fiche et la collection affichent la même valeur après chaque mutation.
