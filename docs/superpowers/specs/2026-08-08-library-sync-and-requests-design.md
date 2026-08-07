# Design — file Seerr, synchronisation et bibliothèque

## Objectif

Rendre Backstage cohérent avec l’état réel du serveur média, alléger l’interface et rapprocher la bibliothèque d’une expérience de catalogue Netflix.

## Décisions

- Une demande Seerr disponible est supprimée de la file active et de Seerr ; le film reste dans Backstage.
- `Mes demandes` ne montre que les demandes en attente, en recherche, en téléchargement ou en erreur.
- Un clic sur `Mes demandes` ouvre une fenêtre de gestion listant le titre, la date, le statut et l’action de suppression.
- La synchronisation serveur importe les médias connus par Radarr/Sonarr mais absents de Backstage, puis hydrate leur affiche et leurs métadonnées via TMDB.
- La synchronisation est idempotente : un média déjà lié n’est pas recréé.
- La fiche film supprime toute mention de machine (`HP ProDesk`, URL locale ou nom de serveur), conserve un bouton d’action contextuel (`Lire` si disponible, sinon `Demander ce film`) et place le favori dans la barre d’action principale.
- La bibliothèque masque la sidebar flottante et ajoute une navigation de catégories sous forme de rails horizontaux et de puces sélectionnables.
- L’en-tête conserve Accueil/Films/Séries centrés dans un espace réservé et réduit les utilitaires pour éviter tout recouvrement.

## Architecture

Le backend garde Seerr comme source de vérité des demandes et normalise seulement les états actifs pour le dashboard. La suppression d’une demande disponible est best-effort : si Seerr l’a déjà retirée, la file reste correcte et le film local est conservé.

L’import bidirectionnel s’appuie sur les bibliothèques Radarr/Sonarr, car elles exposent l’identifiant TMDB fiable et l’état de fichier. Les nouveaux médias sont créés localement, puis `TMDBClient.get_details()` fournit titre, affiche, synopsis, genres et casting lorsque les données distantes le permettent.

## UX

- `Mes demandes` devient une section compacte avec l’action `Gérer les demandes`.
- La fenêtre de gestion affiche une liste dense, triée par date de modification, avec badge de statut et suppression par ligne.
- Les cartes de bibliothèque sont organisées par rails de genres quand aucun filtre précis n’est actif ; les contrôles de tri restent disponibles pour les recherches ciblées.
- La fiche utilise un bandeau d’action neutre et visuel, sans information d’infrastructure.

## Erreurs et compatibilité

- Une panne TMDB ne bloque jamais l’import : le média est créé avec son titre Radarr/Sonarr et une affiche de secours.
- Une panne Seerr ne bloque pas le dashboard ; elle vide uniquement la file distante pour cette réponse.
- Les suppressions Seerr non autorisées ou déjà supprimées sont remontées comme erreur utilisateur, sans supprimer le média local.

## Hors périmètre

Le scan arbitraire de tous les dossiers du disque en dehors des bibliothèques Radarr/Sonarr n’est pas activé : il ne fournit pas toujours de TMDB ID fiable et risquerait de créer des doublons.
