# Audit complet de Backstage — 7 août 2026

## 1. Résumé exécutif

Backstage est devenu un gestionnaire personnel et familial de films et séries, avec l’ambition d’être un « Netflix maison » connecté à Jellyfin, Jellyseerr/Seerr, Radarr et Sonarr. Le produit couvre presque toute la chaîne : découvrir, organiser, noter, demander, télécharger, regarder, suivre sa progression et administrer le serveur média.

Le socle métier est solide. La séparation entre le catalogue partagé (media) et les préférences utilisateur (user_media_state) est la bonne direction pour un produit multi-utilisateur. Les intégrations et la suite de tests backend donnent une base supérieure à celle d’un simple prototype.

Le prochain palier de qualité ne consiste pas à empiler des intégrations. Il consiste à rendre les fonctionnalités existantes prévisibles, rapides, accessibles et sûres.

### Verdict

- Valeur produit : forte — le parcours « découvrir → obtenir → regarder » est différenciant.
- Maturité fonctionnelle : intermédiaire à avancée — beaucoup de cas métier existent, mais certains sont encore dispersés.
- Maturité UX : intermédiaire — l’interface est riche, mais le détail média, le mobile, les modales et les états de chargement doivent être systématisés.
- Risque technique : moyen à élevé — surtout sur les autorisations, les opérations partagées, SQLite, les services externes et l’absence de tests frontend/E2E.
- Priorité recommandée : consolider avant d’élargir — sécurité et modèle de données, puis accueil/reprise, recommandations, acquisition transparente et qualité UX.

## 2. Périmètre et méthode

Audit réalisé en lecture du code, de la documentation, de la configuration, des tests et de l’état Git du dépôt.

Sources principales :

- branche main, commit courant 64469bc (feat: show TMDB user rating on film detail) ;
- modifications locales non commitées, distinguées du code déjà commité ;
- backend FastAPI/SQLite et frontend React/Vite ;
- intégrations TMDB, Jellyfin, Jellyseerr/Seerr, Radarr, Sonarr, Gotify et Uptime Kuma ;
- README.md, BACKSTAGE_OVERVIEW.md, BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md et les audits existants ;
- résultats de validation disponibles le 7 août 2026.

### Validation observée

- npm run lint : OK.
- npm run build : OK, avec un bundle principal d’environ 817 kB avant compression.
- Suite Python : 225 tests réussis sur 233 ; 8 échecs liés à ZoneInfo("Europe/Paris") et à l’absence de tzdata dans l’environnement de test.
- Aucun fichier de code n’a été modifié par cet audit.

## 3. Ce que le produit propose aujourd’hui

Backstage combine quatre produits :

1. un catalogue familial partagé ;
2. un espace personnel de suivi et de notation ;
3. un assistant de découverte et de recommandation ;
4. une interface de pilotage du serveur média local.

La chaîne de valeur est claire :

Découvrir → choisir → demander → télécharger/indexer → regarder → noter → améliorer les recommandations

Fonctionnalités présentes :

- authentification, sessions, rôles, récupération de mot de passe et gestion des utilisateurs ;
- catalogue de films et séries avec métadonnées TMDB ;
- recherche, filtres, favoris, watchlist, historique et note personnelle ;
- affichage de la note utilisateurs TMDB sur la fiche film ;
- disponibilité locale et bouton de lecture via Jellyfin ;
- suivi de progression ;
- demandes via Jellyseerr/Seerr, Radarr et Sonarr ;
- locations temporaires avec expiration, quotas et demande de conservation ;
- notifications d’activité et de disponibilité ;
- administration des utilisateurs, demandes, synchronisations, sauvegardes et activité ;
- synchronisation périodique avec les services média ;
- recommandations par profil, signaux locaux, questions adaptatives et Gemini optionnel ;
- sauvegarde SQLite et vérification d’intégrité ;
- supervision externe via Gotify et Uptime Kuma.

Références : [BACKSTAGE_OVERVIEW.md](BACKSTAGE_OVERVIEW.md), [backend/core/store.py](backend/core/store.py).

## 4. Forces à préserver

### Métier et architecture

- La relation entre catalogue commun et état personnel est une bonne décision structurante.
- Les intégrations couvrent un flux complet, pas uniquement un catalogue statique.
- Les états de disponibilité sont riches : disponible, en téléchargement, en indexation, demandé ou demandable.
- Les événements de recommandation permettent à terme de mesurer la qualité du moteur.
- Les sauvegardes, la vérification d’intégrité et les notifications traitent le logiciel comme un service durable.
- Le backend est nettement plus testé que le frontend.

### Expérience

- Le produit répond à une vraie friction : savoir quoi regarder, puis savoir immédiatement si le contenu est disponible.
- Le bouton de lecture et le statut d’acquisition réduisent la distance entre information et action.
- Les fonctions d’administration sont déjà adaptées à un petit foyer ou serveur personnel.
- L’ajout de la note TMDB améliore la décision sans remplacer la note personnelle.

## 5. Audit des parcours utilisateur

### Première connexion et onboarding

Authentification et récupération de mot de passe sont présentes. En revanche, un nouveau compte ne semble pas guidé vers la configuration de ses goûts, de ses services ou de sa première watchlist. Une bibliothèque vide peut donc donner l’impression que l’application ne propose rien.

Améliorations :

- onboarding en trois étapes : préférences, services disponibles, premiers films/séries ;
- import facultatif depuis une ancienne bibliothèque ou une liste TMDB ;
- écran d’introduction après la première connexion ;
- états vides utiles avec actions immédiates ;
- indicateur de configuration des intégrations.

### Accueil et bibliothèque

La bibliothèque, les filtres et les statuts sont présents, mais le catalogue est chargé de manière globale et l’interface principale porte beaucoup de responsabilités dans proto-ui/src/BackstagePrototype.jsx.

L’accueil doit devenir un tableau de bord personnel :

- Continuer à regarder ;
- Prochain épisode ;
- Ajoutés récemment ;
- Disponibles maintenant ;
- Locations bientôt expirées ;
- demandes en cours ;
- recommandations adaptées au temps disponible.

Il faut aussi persister les filtres dans l’URL, ajouter pagination ou chargement progressif, et déplacer la recherche et les filtres combinables côté SQL.

### Fiche film ou série

La fiche affiche visuels, statut, disponibilité, lecture, acquisition, note personnelle, note TMDB, synopsis, genres, casting et actions personnelles.

La friction principale est structurelle : le détail est partagé entre un composant léger et le monolithe principal. La hiérarchie et les états ne sont pas encore standardisés.

Améliorations :

- vraie modale accessible : role dialog, aria-modal, focus trap, Échap et retour du focus ;
- hiérarchie fixe : action principale, disponibilité, progression, informations, actions secondaires ;
- états explicites : chargement, indisponible, erreur réessayable, données absentes ;
- mobile en plein écran avec barre d’action persistante ;
- séries : progression par saison, épisode suivant, épisodes manquants ;
- section « Pourquoi cette recommandation ? » ;
- distinction claire entre note personnelle, note TMDB et note éditoriale.

### Découverte et recommandations

Le flux interactif est une bonne idée, mais l’audit de recommandation existant relève plusieurs points à consolider : ancien modèle de notation à migrer, pool de candidats limité, questions qui influencent parfois peu la recherche, comparaison insuffisamment exploitée et confusion possible entre « regarder maintenant » et « demander/télécharger ».

Améliorations à forte valeur :

- afficher 2 ou 3 raisons concrètes par suggestion ;
- proposer une alternative plus courte, plus récente, déjà disponible ou plus proche d’un film apprécié ;
- utiliser une pool de candidats paginée et dédoublonnée ;
- traiter la disponibilité comme un signal séparé ;
- mesurer sélection, rejet, démarrage et fin de lecture ;
- proposer un mode rapide et un mode approfondi ;
- distinguer déjà vu, pas envie de revoir, pas maintenant et à garder.

### Demande, téléchargement et lecture

Les intégrations sont présentes, mais l’utilisateur peut ne pas savoir pourquoi une demande bloque ou si le fichier est réellement lisible.

Créer une timeline unique :

Demande créée → acceptée → téléchargement → import → indexation → disponible → lisible

Chaque erreur devrait permettre de réessayer, annuler ou voir un détail technique repliable. Il faut distinguer demandé, téléchargé, disponible et lisible, puis rafraîchir uniquement la ressource concernée.

### Séries

Le suivi d’épisode doit être vérifié pour éviter un état watched partagé entre utilisateurs alors que la progression devrait être personnelle.

À terme :

- suivi par utilisateur au niveau saison/épisode ;
- reprise automatique de l’épisode suivant ;
- épisodes manquants ;
- choix de télécharger une série, une saison ou un épisode ;
- gestion de la diffusion en cours.

### Notifications et administration

Les notifications doivent devenir un centre d’action : priorité, catégorie, lien direct, lu/non lu, regroupement et « tout marquer comme lu ». Les alertes importantes sont disponibilité, erreur de synchronisation, location proche de l’expiration, demande refusée, quota atteint et sauvegarde échouée.

La centralisation dans AdminCenter va dans le bon sens. Il faut terminer la suppression des anciens chemins d’administration et afficher un tableau de santé : intégration, dernier succès, dernière erreur, durée, prochaine synchronisation, espace disque et âge de la dernière sauvegarde.

## 6. Accessibilité et cohérence visuelle

Constats :

- FilmDetailView.jsx utilise un overlay avec aria-label, mais sans preuve de vraie sémantique de dialogue ;
- focus, Échap et retour du focus ne sont pas systématiques ;
- boutons d’icônes et images doivent être vérifiés individuellement ;
- RecommendationFlow.jsx utilise parfois des images sans alternative descriptive ;
- plusieurs textes semblent présenter des problèmes d’encodage visibles, comme CrÃ©er ou SÃ©rie ;
- les états loading, error et données absentes ne suivent pas toujours un système partagé ;
- le monolithe frontend rend les régressions visuelles difficiles à isoler.

Plan recommandé :

1. créer des primitives partagées Modal, Button, IconButton, Toast, AsyncState et Rating ;
2. ajouter axe ou équivalent en CI ;
3. tester clavier seul, zoom 200 %, lecteur d’écran et contraste ;
4. corriger l’encodage UTF-8 ;
5. appliquer une checklist UI à chaque nouvelle vue.

## 7. Sécurité et autorisations

### Points positifs

- mots de passe hachés avec scrypt ;
- tokens de session stockés sous forme hachée ;
- cookies HttpOnly et SameSite ;
- dépendances d’administration présentes sur plusieurs routes ;
- secrets exclus du suivi Git.

### Risques prioritaires

#### S1 — mutations du catalogue partagé

Plusieurs routes de modification de médias sont protégées par l’authentification générale mais pas explicitement par require_admin, notamment la réassociation TMDB, la création depuis TMDB et PATCH /medias/{media_id}. Si le catalogue est partagé, ces routes doivent être administrateur uniquement ou séparées en commandes personnelles.

Références : [backend/api.py:374](backend/api.py#L374), [backend/api.py:1021](backend/api.py#L1021), [backend/api.py:1145](backend/api.py#L1145), [backend/api.py:1161](backend/api.py#L1161).

#### S2 — état d’épisode partagé

PATCH /episodes/{episode_id} semble modifier un état partagé alors que le suivi de lecture devrait être propre à l’utilisateur.

Référence : [backend/api.py:1005](backend/api.py#L1005).

#### S3 — lecture et droits de location

Les routes de playback et de disponibilité doivent vérifier explicitement le droit de lecture : contenu permanent, location active ou contenu autorisé. L’authentification seule ne suffit pas si les quotas et expirations sont des règles métier.

Référence : [backend/api.py:1600](backend/api.py#L1600) et [AUDIT_BACKSTAGE_2026-08.md](AUDIT_BACKSTAGE_2026-08.md).

#### S4 — protection des comptes

Ajouter rate limiting sur connexion, récupération de mot de passe et appels TMDB coûteux. Éviter aussi les différences observables de temps ou de message entre compte existant et compte inconnu.

#### S5 — déploiement

Le cookie sécurisé est configurable mais désactivé par défaut. Un profil de production doit imposer HTTPS, reverse proxy ou VPN, BACKSTAGE_COOKIE_SECURE=1, des secrets hors fichier partagé et une rotation documentée.

#### S6 — santé et secrets opérationnels

Les endpoints de santé doivent distinguer un état public minimal d’un état administrateur détaillé. Les sauvegardes et logs doivent être protégés comme la base.

## 8. Données et fiabilité

### SQLite et migrations

SQLite convient à un contexte domestique, mais les migrations conditionnelles exécutées au démarrage deviendront fragiles. Ajouter une table de version de schéma, des migrations numérotées, des tests de migration depuis plusieurs versions et une procédure de rollback.

Le manque de pagination et d’index devient un risque dès que le catalogue grandit. GET /medias s’appuie sur une récupération globale, notamment [backend/api.py:423](backend/api.py#L423).

### Sauvegardes

La copie SQLite et la vérification d’intégrité sont de bonnes bases. Une sauvegarde placée sur le même volume que la base ne protège toutefois pas contre la perte du volume.

Ajouter une destination externe ou séparée, chiffrement, test automatique de restauration, alerte d’âge maximal et rapport de sauvegarde dans l’administration.

### Services externes

TMDB, Jellyfin, Radarr, Sonarr et Seerr doivent avoir timeout explicite, retries limités avec backoff, cache TTL, circuit breaker ou état de service indisponible, métriques par intégration et distinction entre absence de données, panne réseau et erreur applicative.

Réduire les except Exception trop larges qui transforment une erreur de programmation en simple « service indisponible ».

## 9. Performance et architecture

Risques observés :

- frontend principal de plus de 2 000 lignes avec beaucoup d’état dans BackstagePrototype.jsx ;
- backend et store volumineux ;
- absence de pagination visible sur le catalogue ;
- synchronisation périodique potentiellement globale ;
- appels externes et tâches de fond dans le même processus que la requête web ;
- bundle frontend important ;
- rechargements complets après des actions ponctuelles ;
- absence de cache TMDB suffisamment centralisé.

Architecture cible progressive :

React par domaines
- Bibliothèque
- Fiche média
- Recommandations
- Acquisition / lecture
- Notifications
- Administration

API FastAPI
- commandes personnelles
- commandes administrateur
- lecture / progression
- synchronisation

Worker séparé
- Jellyfin / Seerr / Radarr / Sonarr
- notifications
- sauvegardes

Il n’est pas nécessaire de réécrire le projet. Il faut créer des frontières nettes, mesurer avant d’optimiser et déplacer en premier les tâches lentes ou non critiques hors du chemin de requête.

## 10. Tests, CI et documentation

### Tests

La couverture backend est un point fort. Les lacunes majeures sont :

- aucun socle frontend équivalent identifié ;
- pas de tests E2E navigateur sur les parcours critiques ;
- pas de tests d’accessibilité automatisés ;
- peu de tests de volumétrie, concurrence et panne d’intégration ;
- couverture à renforcer sur droits catalogue, réassociation TMDB, épisodes, lecture avec location expirée et migrations après suppression.

### CI minimale

1. installation reproductible incluant tzdata ;
2. lint frontend ;
3. build frontend ;
4. tests backend complets ;
5. tests E2E Playwright sur environnement mocké ;
6. audit axe sur écrans critiques ;
7. scan dépendances et secrets ;
8. vérification qu’aucun log ou fichier sensible n’est ajouté.

### Documentation

Le principal problème est la divergence entre le README V1 basé sur Notion/NiceGUI et la documentation V2 basée sur FastAPI/React/SQLite. Un nouvel utilisateur peut donc installer un produit différent de celui réellement déployé.

Faire de BACKSTAGE_OVERVIEW.md la source produit principale, réécrire README.md comme guide d’installation V2 et ajouter une matrice unique : livré / partiel / expérimental / abandonné.

## 11. Fonctionnalités recommandées

### P0 — avant les fonctionnalités de croissance

| Fonctionnalité | Valeur | Risque réduit | Effort |
|---|---:|---:|---:|
| Autorisations explicites catalogue/admin | Très forte | Très élevé | Faible à moyen |
| Suivi d’épisodes par utilisateur | Très forte | Élevé | Moyen |
| Rate limiting login/reset/TMDB | Forte | Élevé | Faible |
| tzdata reproductible et CI verte | Forte | Élevé | Faible |
| Sauvegarde externe + test de restauration | Très forte | Très élevé | Moyen |
| Modale et fiche média accessibles | Forte | Moyen | Moyen |
| README et roadmap alignés sur V2 | Moyenne | Moyen | Faible |

### P1 — expérience cœur

1. **Tableau de bord personnel** : continuer la lecture, prochain épisode, nouveautés disponibles, locations à surveiller, demandes en cours et recommandations adaptées au temps disponible.
2. **Timeline d’acquisition** : étapes, erreurs, dernier événement, réessai, annulation et statut réellement orienté utilisateur.
3. **Recommandations explicables** : raisons concrètes, alternatives et fidélité entre explication et calcul.
4. **Recherche et filtres avancés** : durée, année, genre, note, disponibilité, tri, pagination, vues sauvegardées et URL partageable.
5. **Centre de notifications actionnables** : catégories, priorités, liens directs, lu/non lu et préférences par canal.
6. **Gestion série supérieure** : progression personnelle, prochain épisode, épisodes manquants et diffusion en cours.
7. **Import et synchronisation disque → Backstage** : rattacher le contenu présent sans supprimer automatiquement les fichiers.

### P2 — différenciation

- profils familiaux séparés et contrôle parental ;
- 2FA et sessions/appareils visibles ;
- listes et collections collaboratives ;
- mode soirée à plusieurs avec vote ;
- playlists et collections éditoriales ;
- recherche sémantique ;
- PWA/mobile et cache de métadonnées ;
- import depuis TMDB, IMDb, Letterboxd ou Notion ;
- moteur de capacité disque et qualité de fichier ;
- règles de rétention configurables ;
- tableau de santé historique des intégrations ;
- métriques produit anonymisées de la découverte à la satisfaction.

## 12. Roadmap recommandée

### Sprint 1 — sécuriser et rendre fiable

- verrouiller les routes catalogue et épisodes ;
- séparer les états partagés et personnels ;
- ajouter rate limiting ;
- ajouter tzdata et rendre la suite verte ;
- vérifier les règles de lecture et de location ;
- documenter le profil de déploiement sécurisé.

### Sprint 2 — rendre l’usage quotidien évident

- construire le tableau de bord personnel ;
- ajouter reprise et prochain épisode ;
- ajouter la timeline d’acquisition ;
- fiabiliser les états loading/error/empty ;
- finaliser les notifications actionnables.

### Sprint 3 — améliorer la découverte

- migrer et normaliser les notes ;
- étendre le pool de recommandations ;
- exploiter comparaisons et alternatives ;
- afficher les explications ;
- mesurer sélection, lecture et satisfaction.

### Sprint 4 — industrialiser l’expérience

- extraire les domaines du monolithe React ;
- mettre en place les primitives accessibles ;
- ajouter Playwright et axe ;
- ajouter pagination, cache et index ;
- séparer progressivement worker et serveur web.

### Sprint 5 — différencier

- profils familiaux ;
- listes collaboratives ;
- import/export ;
- recherche sémantique ;
- gestion intelligente du stockage et des règles de rétention.

## 13. Les dix actions les plus rentables

1. Protéger toutes les mutations du catalogue par un rôle explicite.
2. Corriger le suivi d’épisode pour qu’il soit personnel.
3. Ajouter tzdata aux dépendances et faire passer les 233 tests.
4. Mettre en place une sauvegarde hors volume et un test de restauration.
5. Construire « Continuer à regarder » sur l’accueil.
6. Ajouter pagination, recherche serveur et cache TMDB.
7. Remplacer la fiche film actuelle par une modale accessible et responsive.
8. Afficher la timeline de demande et les erreurs réessayables.
9. Normaliser les notes et rendre les recommandations explicables.
10. Ajouter cinq parcours E2E : connexion, bibliothèque, fiche, recommandation, demande/lecture.

## Conclusion

Backstage possède déjà une vraie identité produit : il ne se contente pas de cataloguer des films, il relie découverte, décision, disponibilité et lecture dans un environnement personnel.

La meilleure stratégie est de passer d’un logiciel riche mais encore dispersé à un produit fiable et lisible : droits clairs, états compréhensibles, accueil orienté action, recommandations mesurables, séries correctement suivies et architecture frontend progressivement modulaire. Les fonctions collaboratives, sémantiques et intelligentes pourront ensuite apporter une différenciation forte sans augmenter la fragilité du logiciel.

