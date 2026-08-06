# Conservation définitive des locations — Design

## Objectif

Permettre à Hugo de traiter les demandes de conservation des utilisateurs depuis Backstage, sans ligne de commande, tout en protégeant les contenus validés contre une future suppression automatique.

## Périmètre

- Les administrateurs voient uniquement les locations en statut `keep_requested`.
- L’administrateur peut conserver définitivement, refuser ou prolonger de sept jours.
- Une conservation définitive retire l’expiration et marque le contenu comme permanent.
- Un refus laisse le contenu disponible jusqu’à son expiration normale.
- Une prolongation ajoute sept jours à l’expiration actuelle.
- L’utilisateur reçoit une notification interne Backstage persistante.
- Aucun email et aucune suppression de fichier ne sont ajoutés dans cette tranche.

## Modèle de données

La table `media_rentals` reçoit les informations nécessaires à la décision :

- `storage_policy`: `temporary` ou `permanent` ;
- `keep_decision`: `accepted` ou `refused`, nullable ;
- `decided_by`: identifiant de l’administrateur, nullable ;
- `decided_at`: date UTC de décision, nullable.

Le statut `kept` représente une conservation acceptée. Une location refusée revient au statut `available`, conserve son expiration existante et efface la demande en attente.

## API

- `GET /api/admin/rentals/keep-requests` : liste administrateur des demandes en attente.
- `POST /api/admin/rentals/{rental_id}/keep` : rend la location permanente.
- `POST /api/admin/rentals/{rental_id}/refuse` : refuse la conservation.
- `POST /api/admin/rentals/{rental_id}/extend` : ajoute sept jours.
- `GET /api/notifications` : retourne les notifications de l’utilisateur connecté.
- `POST /api/notifications/{notification_id}/read` : marque une notification comme lue.

Chaque route admin vérifie le rôle administrateur et la cohérence du statut avant modification. Chaque décision crée une notification pour le demandeur.

## Interface

Une section administrateur affiche les demandes avec le titre, le demandeur, l’expiration et les actions. Après action, la liste est rafraîchie.

Dans l’interface utilisateur, les notifications sont visibles depuis le compte connecté. Une location `keep_requested` affiche « Conservation demandée » et une location `kept` affiche « Conservé définitivement ».

## Sécurité et stockage

- Toutes les routes nécessitent une session valide.
- Les routes de décision nécessitent le rôle `admin`.
- Les dates sont stockées en UTC.
- Le nettoyage automatique n’est pas activé par cette tranche.
- Une location `kept` ne pourra pas être sélectionnée par un futur processus de suppression.

## Vérification

- Tests API de rôle, propriété, transitions et notifications.
- Tests de persistance des décisions et de la politique permanente.
- Test UI des libellés et actions administrateur.
- Suite Python complète, lint et build frontend.
