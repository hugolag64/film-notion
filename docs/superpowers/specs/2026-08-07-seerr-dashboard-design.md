# Design — demandes Seerr et en-tête Backstage

## Objectif

Permettre de demander un film ou une série depuis une fiche TMDB, puis de suivre et d’annuler cette demande directement depuis l’accueil Backstage.

## Décisions validées

- Le bouton principal de la fiche TMDB est `Demander à Seerr`.
- Une section `Mes demandes` apparaît sur l’accueil.
- Chaque demande affiche son titre, son état, sa progression quand Seerr la fournit et une action `Annuler la demande` lorsqu’elle est encore annulable.
- Les états présentés à l’utilisateur sont `En attente`, `Recherche`, `Téléchargement`, `Disponible` et `Erreur`.
- Backstage utilise le `SeerrClient` existant ; Seerr reste responsable de Radarr/Sonarr, du téléchargement et du suivi distant.
- La synchronisation finale vers la bibliothèque locale reste découplée : la disponibilité est visible immédiatement, puis le mécanisme de synchronisation existant peut importer le média.

## Flux

1. L’utilisateur ouvre une fiche TMDB.
2. Backstage envoie l’identifiant TMDB et le type de média à `POST /seerr/requests`.
3. Seerr crée et suit la demande via Radarr/Sonarr.
4. Le dashboard récupère les dernières demandes Seerr et les normalise dans son contrat public.
5. L’utilisateur peut annuler une demande via `DELETE /seerr/requests/{id}` si Seerr l’autorise.

## Contrat dashboard

Le payload `/dashboard` ajoute `requests`, une liste de cartes contenant au minimum `id`, `tmdb_id`, `title`, `media_type`, `status`, `status_label`, `progress_percent`, `poster_url`, `created_at`, `updated_at` et `cancellable`.

Le backend accepte les réponses Seerr sous forme de liste ou d’objet enveloppant (`results`/`requests`) afin de rester compatible avec les variantes de versions de Seerr.

## En-tête

La navigation primaire `Accueil`, `Films`, `Séries` est positionnée au centre mathématique de la fenêtre. Les utilitaires restent à droite : recherche, ajout, administration, compte, puis un bouton rond avec une lune SVG monochrome. Le sous-titre de marque et le préfixe `+` de l’action d’ajout sont supprimés.
