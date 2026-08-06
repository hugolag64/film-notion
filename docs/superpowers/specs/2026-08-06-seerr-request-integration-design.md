# Intégration Seerr pour les demandes Backstage

## Objectif

Faire de Seerr l’intermédiaire de demande pour les films et séries, tout en conservant le suivi de disponibilité déjà présent dans Backstage.

## Décision

Backstage utilise `SEERR_URL` et `SEERR_API_KEY` pour appeler `POST /api/v1/request` avec l’en-tête `X-Api-Key`. La clé n’est jamais enregistrée dans le dépôt. Le backend transmet le `tmdb_id`, le type (`movie` ou `tv`) et les options de qualité choisies.

Quand Seerr est configuré, la route d’acquisition l’utilise. Si Seerr n’est pas configuré, le comportement Radarr/Sonarr existant reste disponible comme solution de compatibilité.

Les utilisateurs authentifiés peuvent créer une demande depuis Backstage. Seerr reste responsable de l’approbation automatique, des profils, des quotas et de l’envoi vers Radarr/Sonarr. La séparation des comptes et quotas Seerr fera l’objet d’une étape ultérieure ; Backstage conserve son authentification et son catalogue local.

## Erreurs et sécurité

- La clé API est fournie par les variables d’environnement Portainer.
- Les erreurs Seerr sont converties en message utilisateur générique.
- Une demande déjà existante est signalée sans créer de doublon lorsque Seerr le permet.
- Les tests couvrent l’authentification API, les payloads film/série et le repli Radarr/Sonarr.
