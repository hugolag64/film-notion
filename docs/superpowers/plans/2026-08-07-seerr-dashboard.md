# Plan — demandes Seerr et finition de l’interface

## Étape 1 — Contrats et tests

- Ajouter les tests du client Seerr pour lister les demandes et gérer une réponse DELETE vide.
- Ajouter le test de normalisation des cartes de demandes dans le payload dashboard.
- Ajouter les tests de contrat frontend pour la section `Mes demandes`, l’action TMDB et l’en-tête.
- Exécuter ces tests et vérifier l’échec attendu avant toute implémentation.

## Étape 2 — Backend

- Étendre `SeerrClient` avec la lecture et l’annulation des demandes.
- Normaliser les statuts Seerr et les exposer dans `build_dashboard_payload`.
- Charger les demandes sans rendre le dashboard indisponible si Seerr est temporairement inaccessible.
- Ajouter les routes authentifiées de création et d’annulation depuis une fiche TMDB.

## Étape 3 — Frontend

- Ajouter les appels API de création et d’annulation.
- Ajouter `Mes demandes` à l’accueil avec état vide, progression et annulation.
- Remplacer l’action principale de la fiche TMDB par `Demander à Seerr`.
- Rafraîchir l’accueil après création ou annulation et conserver un retour utilisateur clair.

## Étape 4 — En-tête et vérification

- Centrer la navigation avec un positionnement indépendant des blocs gauche/droit.
- Supprimer le sous-titre de marque et le `+` de l’action d’ajout.
- Remplacer l’icône de thème par une lune SVG ronde et discrète.
- Exécuter les tests Python, le lint/build frontend, `git diff --check`, puis inspecter le diff avant commit.

## Hors périmètre

- La création automatique d’un média local dans la bibliothèque à l’instant où Seerr passe à `Disponible`. Elle reste couverte par la synchronisation média existante et pourra faire l’objet d’un sprint dédié.
