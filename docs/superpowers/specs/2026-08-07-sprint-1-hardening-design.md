# Sprint 1 Hardening — Design

## Objectif

Rendre Backstage suffisamment sûr et reproductible pour un déploiement familial/LAN : les mutations partagées sont réservées à l’administration, les états de lecture sont personnels, les routes de playback appliquent les droits de location, les limites de connexion sont protégées, la timezone fonctionne dans un environnement propre et la documentation de déploiement sécurisé est exploitable.

## Décisions

1. Catalogue partagé : les routes qui créent, réassocient, rafraîchissent ou modifient les métadonnées partagées exigent require_admin. Les actions personnelles continuent d’utiliser /medias/{media_id}/personal et user_media_state.
2. Épisodes et progression : les métadonnées d’épisode restent partagées, mais le statut vu/non vu devient une propriété de l’utilisateur dans une nouvelle table personnelle par épisode. Les données historiques peuvent être importées pour l’administrateur.
3. Playback et locations : les routes d’accès à une ressource Jellyfin vérifient l’utilisateur, le média et la location. Un contenu permanent ou une location active autorise la lecture ; une location expirée ou inexistante renvoie 403.
4. Rate limiting : ajouter un composant mémoire à fenêtre glissante, sans nouvelle dépendance. Limiter login et reset par IP et identifiant normalisé, avec 429 et Retry-After. L’état reste local au processus mono-instance.
5. Timezone et déploiement : ajouter tzdata aux dépendances, propager BACKSTAGE_COOKIE_SECURE et les variables de rate limiting, puis documenter HTTPS/VPN, secrets, sauvegarde hors volume et restauration.

## Hors périmètre

- Réécriture React.
- Nouveau fournisseur de cache ou de queue.
- Migration complète des notes de recommandation.
- 2FA.
- Déploiement multi-réplicas.

## Critères d’acceptation

- Un utilisateur non administrateur ne peut plus modifier le catalogue partagé.
- Les épisodes vus d’un utilisateur ne modifient pas ceux des autres.
- Une location expirée ne permet plus d’obtenir une URL ou une ressource de playback.
- Login et reset sont limités et répondent 429 avec délai.
- La suite Python passe sans échec dans l’environnement documenté.
- La documentation explique un déploiement HTTPS/reverse proxy ou VPN, les secrets et la restauration.
- Le lint et le build frontend restent verts.

