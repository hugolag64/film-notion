# Détails des séries et badges de support

## Objectif

Faire de la fiche Série l'équivalent fonctionnel de la fiche Film, tout en séparant ses détails du suivi d'épisodes, et corriger l'affichage des supports sur les cartes.

## Fiche Série

- Deux onglets : `Détails` et `Épisodes`.
- `Détails` affiche l'affiche, le titre, créateur, année, genres, casting, synopsis, note, avis, supports et favori, avec les mêmes interactions que la fiche Film.
- Le titre original anglais est enregistré lorsqu'il est fourni par TMDB. Un bouton `Utiliser le titre original` permet de le définir comme titre principal local ; cette action est facultative et réversible par modification du titre.
- Les séries n'affichent pas l'option Cinéma. Leur statut reste calculé par la progression : `À regarder`, `En cours` ou `Terminée`.

## Onglet Épisodes

- Il conserve les barres de progression générale et par saison.
- Chaque épisode affiche son numéro, son titre et son synopsis quand TMDB le fournit.
- Le synopsis absent n'affiche pas de zone vide.

## Badges de support

- Sur les cartes Film et Série, une pastille Streaming, Cinéma ou Serveur est affichée uniquement si ce support appartient réellement au média.
- Un média sans support n'affiche aucune pastille de support.

## Vérification

- Tests de l'import du titre original et du synopsis d'épisode depuis TMDB.
- Tests des règles d'affichage des badges de support.
- Compilation Vite et régression de la suite Python.
