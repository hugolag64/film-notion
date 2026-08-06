# Expérience utilisateur centrée et recommandations personnalisées — Design

## Objectif

Faire de Backstage une expérience de découverte moderne et cohérente, sans mélanger la consultation des films avec l'administration technique.

Le périmètre comprend trois éléments liés :

- une fiche film centrale, large ou plein écran, qui remplace le panneau latéral ;
- un Centre d'administration unique pour piloter l'application et les services ;
- un mode « Choisir un film » personnalisé, interactif et limité à 5–10 questions.

## Architecture de navigation

La bibliothèque reste l'espace principal de l'utilisateur. La navigation expose séparément :

- Bibliothèque ;
- À voir, Favoris et Historique ;
- Choisir un film ;
- Administration, visible uniquement pour les administrateurs.

La fiche film s'ouvre au centre de l'écran, sous forme de vue large ou de page dédiée selon le contexte. Elle conserve le contexte de navigation afin que le retour ne perde ni les filtres ni la position dans la bibliothèque.

Le Centre d'administration constitue un espace distinct, avec les sections suivantes :

- Vue d'ensemble ;
- Activité serveur ;
- Demandes et locations ;
- Conservation définitive ;
- Utilisateurs et droits ;
- Stockage et quotas ;
- Services Jellyfin, Seerr, Radarr et Sonarr ;
- Paramètres.

Les sauvegardes seront rattachées ultérieurement à la maintenance, mais restent hors du périmètre immédiat.

## Fiche film

La fiche doit présenter une hiérarchie visuelle claire :

1. affiche, titre, année et informations principales ;
2. synopsis, genres, réalisateur, casting et métadonnées TMDB ;
3. progression, statut personnel, note et avis de l'utilisateur connecté ;
4. actions principales : Lire, Reprendre, Favori, À voir et Demander ;
5. état de la location ou de la demande lorsque cela s'applique.

La fiche doit gérer les états de chargement, d'erreur et de données manquantes. La version mobile devient une vue plein écran. Les séries réutilisent cette base, avec une section séparée pour les épisodes.

## Profil de goût individuel

Chaque utilisateur possède un profil de goût indépendant. Le profil agrège notamment :

- les films commencés, terminés, abandonnés et revus ;
- le temps et le pourcentage de visionnage ;
- les notes personnelles ;
- les favoris et les ajouts/retraits de la liste « À voir » ;
- les films ignorés ou refusés dans les recommandations ;
- les réactions explicites « Plus comme ça » et « Moins comme ça ».

Les métadonnées TMDB servent à relier ces signaux aux genres, mots-clés, années, durées, réalisateurs et acteurs. Les préférences durables sont séparées des préférences de session, comme l'envie ponctuelle de regarder quelque chose de léger.

## Mode interactif « Choisir un film »

Le mode utilise le profil existant, puis pose des questions adaptatives. Il s'arrête dès qu'un candidat est suffisamment précis, avec un plafond strict de 10 questions et une cible habituelle de 5 à 7 questions.

Les questions prennent la forme de cartes visuelles ou de comparaisons de films TMDB :

- « Tu préfères celui-ci ou l'autre ? » ;
- « Plus léger ou plus intense ? » ;
- « Récent ou classique ? » ;
- « Valeur sûre ou découverte ? » ;
- « Court ou grande épopée ? » ;
- « Surprise. »

Les réponses affinent le profil de session sans transformer automatiquement chaque choix ponctuel en préférence permanente.

Le moteur :

1. récupère des candidats depuis TMDB ;
2. exclut les films déjà vus par l'utilisateur ;
3. calcule l'affinité avec les genres et caractéristiques appréciés ;
4. ajoute un faible bonus aux films présents dans « À voir » ou les favoris ;
5. tient compte de la note et de la popularité TMDB avec un poids secondaire ;
6. favorise la nouveauté et la diversité ;
7. choisit parmi les meilleurs candidats avec une part de hasard contrôlé.

La disponibilité Jellyfin ne constitue pas un filtre du moteur. Un film recommandé peut donc être disponible, absent ou faire l'objet d'une future demande.

Le résultat affiche un film principal, quelques alternatives et une explication concise, par exemple : « Recommandé parce que tu apprécies les thrillers et que tu as bien noté ces films. »

## Direction visuelle

La gamification reste discrète et premium :

- interface sombre et cinématographique ;
- affiches au centre ;
- progression fine du type « 3 / 7 » ;
- transitions courtes et fluides ;
- boutons sobres ;
- aucun badge enfantin, confetti, classement ou couleur criarde.

L'expérience doit évoquer une recommandation éditoriale de plateforme de streaming, pas un quiz.

## Données et erreurs

Les signaux de lecture et les préférences restent isolés par utilisateur. Une indisponibilité de TMDB doit conserver le profil local et afficher une erreur compréhensible. Si le profil contient trop peu de données, le mode propose une courte phase de découverte basée sur quelques choix visuels, sans prétendre connaître les goûts de l'utilisateur.

## Critères de réussite

- La fiche film est centrée et ne se comporte plus comme un panneau latéral sur desktop.
- Un administrateur trouve toute l'activité et les paramètres dans un Centre d'administration unique.
- Deux utilisateurs ayant des historiques et des notes différents obtiennent des recommandations différentes.
- Le choix d'un film demande généralement moins de 7 interactions et jamais plus de 10.
- Chaque recommandation est compréhensible, personnalisée et relançable.
- L'interface reste sobre, rapide et utilisable sur mobile.
