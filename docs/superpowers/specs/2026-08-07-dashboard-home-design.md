# Dashboard d’accueil — Sprint 2

## Objectif

Faire du dashboard la première vue utile après connexion : comprendre immédiatement quoi reprendre, découvrir une recommandation, puis retrouver l’activité récente et l’état des téléchargements sans ouvrir plusieurs écrans.

## Décisions validées

- Le dashboard devient l’accueil après connexion.
- La bibliothèque reste accessible depuis la navigation et conserve ses filtres.
- La priorité d’usage combine trois besoins : savoir quoi regarder, suivre les téléchargements/disponibilités, et voir l’activité/la bibliothèque.
- L’ordre de lecture est : `Continuer à regarder`, `Pour vous`, puis `Mon activité récente et ma bibliothèque`.
- Le bloc `Continuer à regarder` ne montre que les contenus réellement commencés et non terminés.
- Une carte en cours propose deux actions : `Reprendre` et `Voir la fiche`.
- Les recommandations sont présentées dans une rangée horizontale défilable.
- Chaque recommandation propose `Voir la fiche`, `Pourquoi ce film ?` et `Ajouter à ma watchlist`.
- L’activité mélange ajouts, interactions personnelles, demandes/téléchargements et notifications, triés par date décroissante.
- Les disponibilités sont présentées comme une liste compacte avec les statuts `Disponible`, `Téléchargement`, `Erreur` et `Demande possible`.
- Il n’y a pas de rangée d’actions rapides en haut : l’interface reste minimaliste et cinématographique.
- La densité visuelle privilégie l’espace, les grands posters et une hiérarchie nette.

## Architecture

Le backend expose `GET /api/dashboard`, protégé par l’utilisateur courant. Il agrège les données déjà stockées et les enrichit avec les candidats de recommandation existants. Le frontend consomme une seule ressource pour l’accueil et rend le dashboard dans un composant `DashboardHome` indépendant de la grille de bibliothèque.

Le contrat est tolérant aux intégrations optionnelles : si Jellyfin, TMDB ou un serveur de téléchargement est indisponible, le dashboard rend les autres blocs et affiche un état vide explicite au lieu de casser la page.

## Contrat de données

`GET /api/dashboard` retourne :

```json
{
  "continue_watching": [
    {
      "media_id": "media-1",
      "title": "Titre",
      "series_title": null,
      "season_number": null,
      "episode_number": null,
      "percent": 42.5,
      "last_played_at": "2026-08-07T08:00:00+00:00",
      "media": {"id": "media-1", "title": "Titre", "cover_url": "...", "type": "Film"}
    }
  ],
  "recommendations": [
    {
      "tmdb_id": 123,
      "title": "Titre recommandé",
      "overview": "...",
      "score": 0.8,
      "reasons": ["Parce que vous aimez le thriller"],
      "poster_path": "/poster.jpg",
      "backdrop_path": "/backdrop.jpg",
      "release_date": "2024-01-01",
      "vote_average": 7.4
    }
  ],
  "activity": [
    {"id": "...", "kind": "media_added", "label": "Ajouté à la bibliothèque", "title": "Titre", "media_id": "media-1", "created_at": "..."}
  ],
  "availability": [
    {"media_id": "media-1", "title": "Titre", "poster": "...", "state": "available", "progress_percent": null, "last_error": null, "updated_at": "..."}
  ],
  "last_synced_at": "..."
}
```

Les collections sont bornées côté serveur pour garder un accueil rapide : 6 reprises, 8 recommandations, 10 activités et 8 disponibilités.

## Comportement et états

- Chargement : squelette léger pour les sections principales, sans spinner plein écran.
- Erreur globale : message discret avec bouton `Réessayer`.
- Aucun contenu en cours : le bloc affiche une invitation vers la bibliothèque ou le choix personnalisé.
- Recommandations indisponibles : le bloc affiche `Les recommandations seront disponibles dès que TMDB sera connecté.` sans empêcher l’usage du reste.
- Une carte de reprise sans média local correspondant reste visible avec ses métadonnées Jellyfin, mais `Voir la fiche` n’est proposé que si le média est résolu.
- `Reprendre` déclenche le même lecteur Jellyfin que la fiche existante.
- `Voir la fiche` ouvre la fiche du média dans l’état actuel de l’application.
- `Ajouter à ma watchlist` réutilise la mutation personnelle existante et met à jour la carte immédiatement.
- `Pourquoi ce film ?` ouvre une explication courte basée sur `reasons`, sans lancer une nouvelle session de recommandation.
- La rangée de recommandations défile horizontalement au clavier et expose un libellé accessible.

## Responsive et accessibilité

- Desktop : sections aérées, cartes de reprise larges, recommandations en ligne.
- Mobile : une carte de reprise par ligne, recommandations toujours horizontales avec défilement tactile, activité et disponibilités en pleine largeur.
- Les images ont un texte alternatif utile, les boutons ont des libellés explicites et les couleurs d’état sont accompagnées d’un texte.
- Les actions essentielles sont accessibles au clavier et les cartes ne dépendent pas uniquement d’un clic sur une image.

## Critères d’acceptation

1. Après connexion, l’utilisateur arrive sur le dashboard et peut rejoindre la bibliothèque.
2. Un contenu avec progression entre 0 et 95 % apparaît dans `Continuer à regarder`, avec `Reprendre` et `Voir la fiche` si le média est résolu.
3. Les recommandations apparaissent en défilement horizontal et les trois actions prévues fonctionnent.
4. L’activité regroupe au moins ajouts, interactions utilisateur et disponibilité/demandes dans un ordre chronologique.
5. Les statuts de disponibilité sont lisibles sans ouvrir une fiche.
6. Une panne optionnelle de TMDB/Jellyfin n’empêche pas l’accueil de se charger.
7. Les tests backend, le lint frontend et le build frontend passent.
