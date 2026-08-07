# Note utilisateurs TMDB dans la fiche film — Design

Date : 2026-08-07

## Contexte et objectif

La fiche film affiche déjà la note personnelle de l’utilisateur sur 5 étoiles, mais ne montre pas la note publique TMDB. Les médias sont déjà associés à TMDB via `tmdb_id` et le backend sait récupérer les détails complets d’un film, dont `vote_average`.

L’objectif est d’afficher la note moyenne des utilisateurs TMDB à côté de la note personnelle, sans mélanger les deux échelles et sans ajouter de dépendance à Rotten Tomatoes.

## Décision

La note TMDB sera récupérée à l’ouverture de la fiche film, au moyen d’un endpoint backend dédié. Elle ne sera pas ajoutée au schéma SQLite et ne sera pas chargée pour toute la bibliothèque.

Cette approche permet de prendre en charge les films existants dès maintenant, limite le nombre de requêtes TMDB et évite une migration de données pour une information qui peut évoluer.

## Architecture et flux de données

### Backend

Ajouter `GET /api/medias/{media_id}/tmdb-rating` :

1. Vérifier que le média existe.
2. Si le média n’a pas de `tmdb_id`, retourner une réponse sans note.
3. Interroger `TMDBClient.get_movie_details()` avec l’identifiant existant.
4. Extraire `vote_average` et le normaliser en nombre flottant sur l’échelle TMDB `/10`.
5. Si TMDB ne renvoie pas de détail ou de note exploitable, retourner une réponse sans note plutôt qu’une erreur bloquante.

Réponse nominale :

```json
{"rating": 8.2}
```

Réponse sans note :

```json
{"rating": null}
```

L’endpoint reste protégé par l’authentification existante des routes médias.

### Frontend

Ajouter une fonction `fetchTMDBRating(mediaId)` dans le client API. À l’ouverture ou au changement de film sélectionné, la fiche déclenche cette récupération et maintient un état local de chargement et d’erreur.

Le résultat est affiché dans le bloc de notation existant, à côté de la note personnelle. Le chargement est limité au film sélectionné et le résultat n’est pas persisté côté navigateur au-delà de la fiche ouverte.

## Interface utilisateur

Le bloc de notation conserve son comportement actuel : étoiles interactives, demi-étoiles et note personnelle sur 5.

Un second indicateur est ajouté :

- libellé : `UTILISATEURS TMDB` ;
- valeur : `8,2 / 10`, arrondie à une décimale ;
- badge visuel `TMDB` pour identifier clairement la source ;
- aucune interaction ni modification possible.

Sur écran large, les deux indicateurs sont alignés horizontalement avec une séparation discrète. Sur petit écran, ils peuvent s’empiler sans provoquer de débordement horizontal.

États d’affichage :

- chargement : `Chargement…` ;
- note disponible : valeur sur 10 ;
- média non associé, note absente ou erreur : `Note TMDB indisponible`.

La note personnelle et la note TMDB restent explicitement séparées, car elles utilisent des échelles, des sources et des finalités différentes.

## Gestion des erreurs

Une erreur TMDB ne doit pas fermer la fiche, empêcher la notation personnelle ou perturber les actions de lecture et de statut. Le frontend affiche l’état indisponible dans le seul indicateur TMDB.

Les réponses inattendues ou les valeurs non numériques sont traitées comme une note absente. Aucune valeur par défaut ne sera inventée.

## Tests et vérification

Ajouter des tests backend couvrant :

- un film sans `tmdb_id` ;
- une réponse TMDB contenant `vote_average` ;
- l’absence de détails TMDB ou l’absence de note exploitable.

Vérifier ensuite :

- `pytest` pour les tests backend concernés puis l’ensemble de la suite ;
- `npm run lint` dans `proto-ui` ;
- `npm run build` dans `proto-ui`.

La vérification manuelle couvrira une fiche avec note TMDB, une fiche sans association TMDB et une largeur mobile.

## Hors scope

- Rotten Tomatoes ou toute autre source externe ;
- combinaison, moyenne ou pondération entre la note TMDB et la note personnelle ;
- modification de la note TMDB ;
- stockage de la note TMDB en base de données ;
- chargement de toutes les notes TMDB dans la grille de bibliothèque ;
- ajout d’un logo TMDB externe ou d’une nouvelle dépendance graphique.
