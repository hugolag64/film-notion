# Lecteur Jellyfin plein écran dans Backstage

## Objectif

Depuis la fiche d’un film disponible dans Jellyfin, le bouton « Lire » doit ouvrir immédiatement une vue lecteur plein écran dans Backstage, sans passer par la fiche Jellyfin.

## Décision

Utiliser le transcodage HLS de Jellyfin et un lecteur vidéo côté navigateur.

- Le navigateur ne reçoit jamais la clé API Jellyfin.
- Backstage identifie le média local et son `jellyfin_id`.
- Le backend demande à Jellyfin un flux lisible par navigateur et relaie les ressources nécessaires.
- Le frontend ouvre une vue plein écran avec contrôles vidéo, état de chargement et erreurs.
- Le bouton Retour ferme le lecteur et revient à la fiche du film.

## Flux de données

1. L’utilisateur clique sur « Lire ».
2. Backstage vérifie que le média possède une disponibilité Jellyfin.
3. Le frontend ouvre la vue lecteur.
4. Le lecteur demande au backend le flux HLS du média.
5. Le backend authentifie la requête auprès de Jellyfin avec `X-Emby-Token` et relaie la playlist/les segments.
6. Le navigateur lit le flux et affiche les contrôles natifs.

## Composants

### Backend

- Ajouter une méthode Jellyfin pour construire les paramètres de lecture HLS.
- Ajouter une route de lecture protégée par l’existence d’une disponibilité Jellyfin.
- Ne jamais inclure la clé API dans une URL ou une réponse envoyée au frontend.
- Préserver les statuts HTTP et les types MIME utiles au lecteur.

### Frontend

- Ajouter un état `playerMedia` indépendant de la fiche détaillée.
- Afficher un lecteur plein écran au-dessus de l’application avec `<video controls autoPlay>`.
- Afficher chargement, erreur, bouton Retour et titre du film.
- Conserver l’action actuelle d’acquisition quand le média n’est pas disponible.

## Compatibilité et erreurs

- Le lecteur doit fonctionner avec le MKV 4K HEVC HDR d’Interstellar via le transcodage Jellyfin.
- Une disponibilité absente ou un flux indisponible doit produire un message lisible, sans exposer de détail sensible.
- La fermeture du lecteur doit arrêter le chargement du flux et nettoyer l’état local.

## Tests et validation

- Test backend : un média disponible génère une requête de lecture Jellyfin sans exposer la clé dans l’URL publique.
- Test backend : un média sans disponibilité renvoie une erreur explicite.
- Build frontend.
- Vérification manuelle avec Interstellar : clic sur « Lire » → vue plein écran Backstage → début de lecture.

## Hors périmètre

- Remplacer l’interface complète de Jellyfin.
- Ajouter Sonarr.
- Gérer le téléchargement ou la conversion permanente des fichiers.
