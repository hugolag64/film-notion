# Unification de l’administration et séparation du compte utilisateur

## Objectif

Supprimer la duplication entre le panneau `GogBoss` et le `Centre d’administration`. `GogBoss` doit rester un espace personnel ; toutes les fonctions de pilotage doivent être regroupées dans `Administration`.

## Décisions

- `GogBoss` conserve uniquement : nom du compte, changement de mot de passe, notifications, appareils mémorisés et déconnexion.
- `Administration` devient l’unique espace pour : tableau de bord, activité serveur, demandes de conservation, utilisateurs et droits, stockage, services, paramètres, sauvegardes et aperçu du nettoyage.
- La section `Administration > Utilisateurs` reprend toutes les actions actuellement disponibles dans `GogBoss` : création, modification du nom, association Jellyfin, changement de mot de passe, rôle, activation/désactivation et suppression.
- Les cartes utilisateurs de l’administration sont interactives ; les actions restent soumises aux autorisations de l’API, notamment l’interdiction de supprimer son propre compte.

## Architecture d’interface

Un composant `UserManagement` regroupe l’état, les appels API et le rendu des utilisateurs. Il est monté dans `Administration > Utilisateurs`, afin qu’il n’existe plus de seconde copie de cette logique dans `AccountPanel`.

La carte « Utilisateurs » de la vue d’ensemble devient également un bouton qui ouvre directement la section utilisateurs.

## Flux de données

`AdminCenter` charge les données de pilotage et transmet le contexte visuel au composant `UserManagement`. Après chaque mutation, celui-ci recharge les utilisateurs et les comptes Jellyfin. Les erreurs et confirmations restent visibles dans le centre d’administration.

## Vérification

- Le build Vite doit réussir.
- L’ancien panneau `GogBoss` ne doit plus afficher les blocs de pilotage administratif.
- `Administration > Utilisateurs` doit permettre de gérer les comptes et rendre les cartes cliquables.
- Les tests backend existants de création, modification et suppression restent verts.

