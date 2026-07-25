# Bibliothèque React : gestion des films

## Objectif

Faire de React l'interface unique de Backstage et rendre la bibliothèque de films utilisable : affichage de marque, états cohérents, tri, filtres et ajout enrichi via TMDB.

## Interface

- L'en-tête React affiche `Logo.png` servi par l'application Python ; l'ancienne interface NiceGUI n'est plus utilisée.
- Chaque affiche ne conserve que les pastilles de support (Cinéma, Streaming, Serveur) et le favori. Le statut est affiché dans le pied de carte, à l'emplacement de l'actuel libellé `Watched` ou `À regarder`.
- Une barre au-dessus de la grille propose un tri, des filtres par genre, réalisateur, statut et support, et une action de réinitialisation. Les genres de la colonne latérale appliquent le même filtre de genre.

## États des films

- Les états stockés sont `À regarder` et `Terminé`.
- Passer à `À regarder` efface la note et marque le film non vu.
- Passer à `Terminé` marque le film vu et conserve sa note existante.
- La vue React ne s'appuie plus sur les alias contradictoires `watched` et `watchlist` ; une conversion de compatibilité est appliquée à la lecture des anciens enregistrements.

## Tri et filtrage

- Le tri par défaut est la date d'ajout, du plus récent au plus ancien.
- Les autres tris sont : titre, année et note, chacun dans les deux sens quand cela est pertinent.
- Les filtres se combinent avec la recherche texte sur le titre et le réalisateur.
- Les options de genre, réalisateur et support sont dérivées des films chargés, afin de ne jamais proposer de valeur sans résultat possible.

## Ajout via TMDB

1. Le bouton `+ Ajouter un film` ouvre une modale avec un champ de recherche.
2. L'utilisateur sélectionne un résultat TMDB.
3. Le backend récupère ses détails TMDB et crée le média local avec l'état `À regarder` et sans note.
4. Le frontend recharge la bibliothèque et sélectionne/affiche le film nouvellement créé.

## Frontend et API

- `proto-ui` est le seul frontend servi à la racine.
- L'API FastAPI expose une création de média TMDB dédiée, en plus de la recherche existante et des mises à jour.
- Les composants React conservent les contrôles de tri/filtre et la modale d'ajout, tandis que le backend reste responsable de la persistance et de l'enrichissement TMDB.

## Hors périmètre

L'onglet Séries et l'intégration Radarr/Sonarr sont prévus après ce lot. Ils demanderont leur propre conception pour les réglages de connexion, profils de qualité, files de téléchargement et traitement des erreurs externes.

## Vérification

- Tests Python pour les états, l'API de création et les règles de filtrage/tri.
- Vérification du composant React et compilation de `proto-ui`.
- Régression de la suite de tests existante.
