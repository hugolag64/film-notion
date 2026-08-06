# Liaison manuelle des comptes Backstage et Jellyfin

## Objectif

Permettre à un administrateur d'associer chaque compte Backstage à un compte utilisateur Jellyfin existant. L'association servira de base à la personnalisation future de la lecture et du suivi de progression.

Cette phase ne transmet pas encore l'identité Jellyfin au lecteur vidéo. Elle se limite à gérer une association persistante, sûre et administrable.

## Périmètre

Inclus :

- enregistrer l'identifiant utilisateur Jellyfin dans le compte Backstage ;
- afficher les utilisateurs Jellyfin disponibles via l'API Jellyfin ;
- associer, modifier ou retirer une association depuis le panneau administrateur ;
- empêcher qu'un même compte Jellyfin soit associé à plusieurs comptes Backstage ;
- conserver les associations existantes si Jellyfin est momentanément indisponible ;
- couvrir la migration SQLite et les erreurs par des tests.

Exclus de cette phase :

- stocker un mot de passe ou un jeton Jellyfin par utilisateur ;
- créer ou supprimer des utilisateurs Jellyfin depuis Backstage ;
- changer le comportement du lecteur vidéo ;
- synchroniser automatiquement les comptes par adresse e-mail.

## Architecture

### Stockage

Ajouter une colonne nullable `jellyfin_user_id` à la table SQLite `users`.

- `NULL` signifie qu'aucun compte Jellyfin n'est associé.
- L'identifiant est stocké comme une chaîne opaque fournie par Jellyfin.
- Une contrainte d'unicité partielle garantit qu'un identifiant Jellyfin non nul ne peut être utilisé qu'une fois.
- La migration est additive et exécutée au démarrage : vérifier `PRAGMA table_info(users)`, puis effectuer `ALTER TABLE` uniquement si la colonne manque.
- Créer l'index unique partiel après l'ajout de la colonne.

Les réponses Backstage exposent uniquement l'identifiant Jellyfin et l'état de liaison. Aucun secret Jellyfin n'est renvoyé au navigateur.

### API backend

Ajouter à l'API d'authentification, avec contrôle administrateur :

- `GET /api/auth/jellyfin-users` : interroger Jellyfin avec la clé API globale déjà configurée et retourner une liste réduite `{id, name, is_admin}` ;
- `PUT /api/auth/users/{user_id}/jellyfin` : recevoir `{jellyfin_user_id: string|null}`, vérifier l'existence de l'utilisateur Backstage et appliquer ou retirer l'association ;
- étendre `GET /api/auth/me` et `GET /api/auth/users` afin d'inclure `jellyfin_user_id`.

La logique d'association reste dans `AuthStore` pour conserver les transactions SQLite et les règles d'unicité au même endroit. L'accès Jellyfin reste dans `JellyfinClient`.

### Interface

Dans la section administrateur « Utilisateurs », chaque compte affiche un sélecteur Jellyfin :

- option « Non associé » ;
- liste des comptes Jellyfin récupérés à l'ouverture ou au rafraîchissement du panneau ;
- sauvegarde immédiate lors de la sélection ;
- message de succès ou d'erreur ;
- indication lisible lorsqu'un compte Jellyfin est déjà utilisé.

Si la récupération Jellyfin échoue, le panneau conserve les données Backstage et affiche une erreur sans effacer les associations actuelles.

## Flux de données

1. L'administrateur ouvre le panneau Compte.
2. Backstage demande la liste des utilisateurs Jellyfin avec la clé serveur globale.
3. Backstage affiche les comptes disponibles et les associations actuelles.
4. L'administrateur sélectionne un compte Jellyfin pour un utilisateur Backstage.
5. L'API vérifie les droits administrateur, l'existence de la cible et l'unicité de l'identifiant.
6. SQLite enregistre l'association dans une transaction.
7. L'API renvoie l'utilisateur mis à jour ; l'interface rafraîchit son état.

## Erreurs et sécurité

- Les endpoints de lecture et de modification sont réservés aux administrateurs.
- Un identifiant Jellyfin inconnu est refusé plutôt que stocké silencieusement.
- Une association déjà utilisée par un autre compte renvoie une erreur explicite et ne modifie rien.
- Une valeur vide est normalisée en `NULL` pour permettre de dissocier un compte.
- Les erreurs Jellyfin sont transformées en messages génériques côté interface ; la clé API reste côté serveur.
- La suppression ou la désactivation d'un compte Backstage ne supprime pas le compte Jellyfin associé.

## Tests et critères d'acceptation

Backend :

- migration sur une base existante sans colonne ;
- démarrage idempotent sur une base déjà migrée ;
- retour du `jellyfin_user_id` dans les utilisateurs ;
- liste Jellyfin réduite aux champs autorisés ;
- association, modification et dissociation ;
- refus d'une association dupliquée ;
- refus des opérations sans rôle administrateur ;
- conservation des associations si Jellyfin répond en erreur.

Frontend :

- chargement du sélecteur pour un administrateur ;
- affichage de l'association actuelle ;
- sauvegarde d'une association et rafraîchissement ;
- dissociation ;
- affichage d'une erreur sans perte des données déjà affichées.

Le comportement actuel du lecteur et les comptes Jellyfin eux-mêmes doivent rester inchangés.

## Évolution prévue

Une phase ultérieure pourra utiliser `jellyfin_user_id` dans les requêtes de lecture et de progression. Cette phase fera l'objet d'une vérification séparée avec la version Jellyfin installée avant toute modification du lecteur.
