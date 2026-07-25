# Interface Séries et progression des épisodes

## Objectif

Ajouter une collection Séries à Backstage, visuellement cohérente avec les Films, avec import TMDB TV et suivi local des saisons et épisodes vus.

## Navigation et animation

- L'en-tête contient un sélecteur segmenté `Films | Séries`.
- Le changement utilise l'animation « portail cinéma » : la collection sort avec un décalage et un flou léger, la suivante entre depuis le côté opposé avec une lueur adaptée.
- Les films et séries conservent leurs propres filtres, recherche, tri et sélection dans l'interface React.

## Collection et fiche Série

- La vue Séries reprend la grille de cartes des films et affiche explicitement le type `Série`.
- Chaque fiche série affiche le créateur, l'année, les genres, le statut et les supports.
- Les saisons sont des sections repliables. Chaque épisode possède une case vue/non vue.
- La fiche contient une barre générale `épisodes vus / épisodes totaux` et une barre par saison, avec pourcentage lisible.

## États

- Une série sans épisode vu est `À regarder`.
- Une série avec au moins un épisode vu mais incomplète est `En cours`.
- Une série dont tous les épisodes sont vus est `Terminée`.
- Le statut est calculé à partir de la progression, non modifié manuellement.

## Données et TMDB

- Le modèle local distingue `Film` et `Série` par `Media.type`.
- Les saisons et épisodes sont persistés localement avec leur numéro, titre et état vu.
- L'ajout de série recherche TMDB TV, récupère les détails, saisons et épisodes, puis crée la série avec tous les épisodes non vus.
- Les films existants et l'API de films restent inchangés.

## Vérification

- Tests des calculs de progression et de statut de série.
- Tests de création des épisodes depuis une réponse TMDB TV simulée.
- Test de régression du sélecteur Films/Séries et compilation Vite.
