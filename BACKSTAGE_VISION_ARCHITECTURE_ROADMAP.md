# Backstage — Vision produit, architecture cible et feuille de route

> Document de cadrage général destiné à être placé à la racine du dépôt Backstage.
> Il résume la vision validée pour transformer Backstage en une plateforme personnelle de type « Netflix maison », multi-utilisateur, intégrée à Jellyfin, Radarr, Sonarr et Seerr.

---

## 1. Vision générale

Backstage est une application personnelle de gestion de films et de séries permettant actuellement de :

- cataloguer les films vus, à voir ou conservés ;
- consulter une base personnelle de contenus ;
- lancer un contenu dans un lecteur Jellyfin intégré ;
- centraliser l’expérience autour d’une interface personnalisée.

L’objectif est de faire évoluer Backstage vers une plateforme domestique complète, utilisable par plusieurs personnes dans une colocation, tout en conservant une administration simple.

La plateforme doit permettre :

1. à Hugo de conserver sa propre collection permanente ;
2. aux colocataires d’utiliser Backstage avec leur propre compte ;
3. à chaque utilisateur d’avoir ses listes, son historique et sa progression ;
4. de demander automatiquement un film ou une série absente ;
5. de télécharger certains contenus sans validation manuelle préalable ;
6. de limiter la durée de conservation des contenus demandés par les colocataires ;
7. de permettre à Hugo de valider, en un clic, l’intégration définitive d’un contenu temporaire à la collection permanente.

Le système doit rester intuitif : les utilisateurs ne doivent jamais avoir à lancer de commandes ou manipuler directement Docker, Radarr, Sonarr ou Jellyfin.

---

## 2. Principe d’architecture

Backstage doit rester l’interface principale visible par les utilisateurs.

Les services techniques restent en arrière-plan.

```text
Utilisateur
    ↓
Backstage
    ├── comptes et rôles
    ├── catalogue commun
    ├── listes personnelles
    ├── lecteur Jellyfin intégré
    ├── demandes de contenus
    ├── locations temporaires
    └── interface administrateur
          ↓
        Seerr
          ↓
    Radarr / Sonarr
          ↓
    Client de téléchargement
          ↓
       Jellyfin
```

### Répartition des responsabilités

#### Backstage

Backstage gère :

- l’interface utilisateur ;
- les comptes et les rôles ;
- les tableaux de bord personnels ;
- le catalogue commun ;
- les listes personnelles ;
- les demandes de téléchargement ;
- les règles de location temporaire ;
- les demandes de conservation ;
- les validations administrateur ;
- les notifications et dates d’expiration ;
- l’intégration du lecteur Jellyfin.

#### Jellyfin

Jellyfin gère :

- la lecture vidéo ;
- les bibliothèques multimédias ;
- la progression de visionnage ;
- les reprises de lecture ;
- les historiques individuels ;
- les droits d’accès aux bibliothèques ;
- le transcodage lorsque nécessaire.

Chaque utilisateur de Backstage doit disposer de son propre compte Jellyfin.

#### Seerr

Seerr sert d’intermédiaire entre Backstage et Radarr/Sonarr.

Il gère notamment :

- les demandes de films et de séries ;
- les permissions par utilisateur ;
- l’approbation automatique ;
- les quotas ;
- la détection des contenus déjà disponibles ;
- la communication avec Radarr et Sonarr.

Backstage doit idéalement utiliser l’API de Seerr plutôt que communiquer directement avec tous les services.

#### Radarr

Radarr gère :

- la recherche des films ;
- le téléchargement ;
- l’import ;
- le renommage ;
- le classement des fichiers ;
- la suppression technique des films lorsque Backstage l’autorise.

#### Sonarr

Sonarr remplit le même rôle pour :

- les séries ;
- les saisons ;
- les épisodes.

La gestion temporaire des séries sera plus complexe que celle des films. Elle doit donc être réalisée après stabilisation du système temporaire pour les films.

---

## 3. Hébergement et déploiement

Le serveur cible est un HP ProDesk 600 G4 Mini équipé notamment de :

- processeur Intel Core i5-8500T ;
- 16 Go de mémoire vive ;
- SSD système de 500 Go ;
- connexion Ethernet ;
- disque de stockage multimédia séparé.

Le serveur sera installé sous Linux, avec Docker et Docker Compose.

### Organisation recommandée

```text
Ubuntu Server
│
├── Docker Engine
├── Docker Compose
├── Portainer
│
├── Stack Backstage
├── Stack Jellyfin
├── Stack Seerr
├── Stack Radarr
├── Stack Sonarr
├── Stack client de téléchargement
└── Stack éventuelle de supervision et sauvegarde
```

### Portainer

Portainer doit fournir une interface simple pour :

- démarrer une application ;
- arrêter une application ;
- redémarrer un conteneur ;
- consulter les journaux ;
- surveiller l’état des services ;
- redéployer une nouvelle version.

L’objectif est d’avoir de véritables « interrupteurs » pour les différentes applications.

---

## 4. Mise à jour de Backstage depuis GitHub

Backstage est un programme évolutif et régulièrement modifié.

Le développement doit continuer sur l’ordinateur principal. Le serveur ne doit pas servir d’environnement de développement.

### Organisation Git recommandée

```text
branche dev
    ↓
développement et tests locaux
    ↓
branche main
    ↓
version suffisamment stable pour le serveur
```

### Première méthode de déploiement

Pour commencer, la mise à jour peut rester manuelle :

```bash
cd /srv/apps/backstage
git pull
docker compose up -d --build
```

Cette méthode est simple à comprendre et à dépanner.

### Méthode cible

À terme, le déploiement doit être automatisé :

```text
Push ou fusion sur main
        ↓
GitHub Actions construit l’image Docker
        ↓
Image envoyée dans GitHub Container Registry
        ↓
Le serveur récupère la nouvelle image
        ↓
Docker redémarre uniquement Backstage
```

Exemple d’image :

```text
ghcr.io/<utilisateur-github>/backstage:stable
```

La mise à jour du serveur devient alors :

```bash
docker compose pull
docker compose up -d
```

Une automatisation complète pourra ensuite être ajoutée avec Portainer ou un mécanisme de webhook.

### Données persistantes

Les données ne doivent jamais être stockées uniquement à l’intérieur du conteneur.

```text
Code source        → GitHub
Application        → image Docker
Données utilisateurs → volume persistant
Secrets            → fichier .env hors GitHub
```

Exemples de données persistantes :

- base de données Backstage ;
- comptes utilisateurs ;
- listes et historiques ;
- demandes temporaires ;
- demandes de conservation ;
- paramètres ;
- images et affiches locales ;
- journaux importants ;
- sauvegardes.

---

## 5. Expérience multi-utilisateur

Backstage doit gérer plusieurs comptes sans dupliquer toute la base de films.

### Catalogue commun

Un film ou une série n’existe qu’une seule fois dans le catalogue global.

Exemple conceptuel :

```text
Film
├── identifiant interne
├── identifiant TMDb
├── titre
├── affiche
├── année
├── genres
├── présent dans Jellyfin
├── chemin du fichier
├── statut de conservation
└── métadonnées techniques
```

### Données propres à chaque utilisateur

Chaque utilisateur possède une relation personnelle avec le contenu.

```text
Utilisateur ↔ Film
├── à voir
├── vu
├── favori
├── note personnelle
├── date d’ajout
├── progression
├── date de dernière lecture
└── demande temporaire éventuelle
```

Les utilisateurs partagent donc le même catalogue, mais disposent chacun de :

- leur tableau de bord ;
- leur liste « à voir » ;
- leurs favoris ;
- leur historique ;
- leur progression ;
- leurs demandes ;
- leurs recommandations éventuelles.

### Rôles

#### Administrateur

L’administrateur peut :

- gérer tous les utilisateurs ;
- modifier le catalogue ;
- approuver ou refuser une conservation ;
- rendre un film permanent ;
- prolonger une location ;
- supprimer un contenu ;
- modifier les quotas ;
- consulter l’espace disque utilisé ;
- accéder aux outils de maintenance.

#### Utilisateur

Un utilisateur peut :

- consulter le catalogue ;
- lire les contenus disponibles ;
- créer ses listes ;
- demander un contenu absent ;
- suivre l’état de sa demande ;
- demander la conservation d’un contenu ;
- prolonger éventuellement une location dans les limites définies.

#### Invité, optionnel

Un rôle invité pourra être ajouté ultérieurement avec :

- accès en lecture uniquement ;
- absence de téléchargement ;
- accès limité à certaines bibliothèques.

---

## 6. Liaison entre Backstage et Jellyfin

Chaque utilisateur Backstage doit être associé à un utilisateur Jellyfin distinct.

```text
Compte Backstage
        ↕
Compte Jellyfin
```

Cette association garantit une séparation correcte de :

- la progression ;
- la reprise de lecture ;
- l’historique ;
- les contenus vus ;
- les préférences ;
- les droits d’accès.

Le lecteur Jellyfin intégré dans Backstage doit utiliser la session Jellyfin de l’utilisateur connecté.

Il ne faut pas utiliser un compte Jellyfin administrateur commun pour tous les utilisateurs.

---

## 7. Demande automatique d’un contenu

Lorsqu’un contenu est absent de la bibliothèque, l’utilisateur peut cliquer sur un bouton simple :

> Demander ce film

Le fonctionnement attendu est le suivant :

```text
L’utilisateur demande un film
        ↓
Backstage vérifie s’il est déjà disponible
        ↓
Backstage transmet la demande à Seerr
        ↓
La demande est automatiquement approuvée
        ↓
Seerr envoie la demande à Radarr
        ↓
Radarr lance le téléchargement
        ↓
Le fichier est importé
        ↓
Jellyfin détecte le film
        ↓
Backstage affiche « Disponible »
```

### Absence de validation administrateur préalable

Les demandes ordinaires des colocataires doivent être autonomes.

Hugo ne doit pas avoir à valider chaque téléchargement.

L’approbation automatique doit toutefois respecter des limites définies.

### Garde-fous recommandés

Pour une première version :

- 3 locations simultanées maximum par utilisateur ;
- qualité limitée à 1080p par défaut ;
- quota de stockage temporaire par utilisateur ;
- impossibilité de demander un doublon ;
- blocage des nouvelles demandes lorsque l’espace disque libre devient insuffisant ;
- limitation du nombre de demandes sur une période donnée ;
- possibilité de désactiver temporairement les demandes pour un utilisateur.

---

## 8. Système de location temporaire

Les contenus demandés par les colocataires ne doivent pas rester indéfiniment sur le disque.

Ils doivent être considérés comme des locations temporaires.

### Données d’une location

```text
Location temporaire
├── utilisateur demandeur
├── contenu
├── date de demande
├── date de disponibilité
├── date de première lecture
├── date de fin de lecture
├── date d’expiration
├── statut
├── taille du fichier
├── demande de conservation
└── décision administrateur
```

### Statuts possibles

```text
requested
downloading
available
watching
completed
keep_requested
permanent
expired
deletion_scheduled
deleted
failed
```

Les noms définitifs pourront être adaptés aux conventions déjà présentes dans le code.

---

## 9. Règles de durée proposées

### Avant la première lecture

Une fois le film disponible, l’utilisateur dispose de 21 jours pour commencer à le regarder.

```text
date d’expiration initiale =
date de disponibilité + 21 jours
```

### Après le début du film

À la première lecture, l’expiration est recalculée.

L’utilisateur dispose alors de 7 jours pour terminer le film.

```text
nouvelle expiration =
date de première lecture + 7 jours
```

### Après la fin du film

Une fois le film considéré comme terminé, sa suppression peut être programmée après 48 heures.

Ce délai laisse le temps :

- de revoir la fin ;
- de signaler un problème ;
- de demander sa conservation ;
- d’éviter une suppression trop brutale.

### Demande de conservation en attente

Lorsque l’utilisateur demande à conserver un contenu, la suppression doit être suspendue jusqu’à la décision de l’administrateur.

Un délai de sécurité peut néanmoins être prévu pour éviter qu’une demande reste indéfiniment en attente.

---

## 10. Demande de conservation

Sur la fiche d’un contenu temporaire, l’utilisateur voit un bouton :

> Demander à conserver

Ce bouton ne rend pas immédiatement le contenu permanent.

Il crée une demande à destination de l’administrateur.

### Pour l’utilisateur

Avant la demande :

```text
[ Regarder ] [ Demander à conserver ]
```

Après la demande :

```text
Demande de conservation envoyée
En attente de validation
```

### Pour l’administrateur

Une section dédiée doit apparaître dans le tableau de bord :

```text
Demandes de conservation
├── contenu
├── utilisateur demandeur
├── taille du fichier
├── date d’expiration actuelle
├── nombre d’utilisateurs intéressés
└── actions
```

Actions disponibles :

- Conserver définitivement ;
- Refuser ;
- Prolonger de 7 jours ;
- Ouvrir la fiche complète.

### Validation de la conservation

Lorsqu’Hugo clique sur « Conserver définitivement », Backstage doit :

1. passer le contenu de temporaire à permanent ;
2. supprimer sa date d’expiration ;
3. annuler toute suppression programmée ;
4. l’ajouter à la collection permanente ;
5. protéger son fichier contre le nettoyage automatique ;
6. enregistrer l’administrateur ayant validé la demande ;
7. notifier l’utilisateur demandeur.

Exemple conceptuel :

```text
Avant
storage_policy = temporary
expires_at = 2026-08-24
keep_requested = true

Après
storage_policy = permanent
expires_at = null
keep_requested = false
approved_by = <admin_id>
approved_at = <date>
```

### Refus

Un refus ne supprime pas immédiatement le film.

Le contenu reste disponible jusqu’à son expiration normale.

Le refus signifie uniquement qu’il ne rejoindra pas la collection permanente.

---

## 11. Règles de suppression sécurisée

Le nettoyage automatique ne doit jamais supprimer un contenu uniquement parce qu’une demande individuelle a expiré.

Avant toute suppression, Backstage doit vérifier :

1. le contenu est-il déjà permanent ?
2. une autre location active existe-t-elle ?
3. une demande de conservation est-elle en attente ?
4. un autre utilisateur est-il en train de le regarder ?
5. le contenu a-t-il été marqué manuellement comme protégé ?
6. le fichier est-il actuellement utilisé par un téléchargement ou un import ?
7. s’agit-il d’un film ou d’un élément appartenant à une série encore active ?
8. une erreur de synchronisation avec Jellyfin, Radarr ou Sonarr existe-t-elle ?

Le fichier ne peut être supprimé que lorsqu’aucune raison valide de le conserver n’existe.

### Exemple avec plusieurs utilisateurs

```text
Paul demande un film
→ expiration prévue le 10 août

Léa demande le même film le 7 août
→ expiration de Léa prévue le 28 août

Résultat :
le fichier reste présent au moins jusqu’au 28 août
```

La suppression doit dépendre de la dernière location active, et non de la première demande.

---

## 12. Interface utilisateur envisagée

### Carte d’un film temporaire

```text
┌─────────────────────────────────────────┐
│ Titre du film                           │
│                                         │
│ Disponible encore 12 jours              │
│                                         │
│ [ Regarder ] [ Demander à conserver ]   │
└─────────────────────────────────────────┘
```

### Après demande de conservation

```text
┌─────────────────────────────────────────┐
│ Titre du film                           │
│                                         │
│ Conservation demandée                   │
│ En attente de validation                │
│                                         │
│ [ Regarder ]                            │
└─────────────────────────────────────────┘
```

### Carte administrateur

```text
┌──────────────────────────────────────────────┐
│ Paul souhaite conserver ce film              │
│                                              │
│ Taille : 18,4 Go                             │
│ Expiration actuelle : dans 12 jours          │
│                                              │
│ [ Conserver ] [ Refuser ] [ +7 jours ]       │
└──────────────────────────────────────────────┘
```

### Tableau de bord administrateur

Le tableau de bord doit afficher :

- le nombre de demandes en attente ;
- les contenus arrivant prochainement à expiration ;
- l’espace de stockage disponible ;
- l’espace occupé par les locations ;
- les téléchargements en cours ;
- les erreurs de synchronisation ;
- les contenus programmés pour suppression ;
- les utilisateurs ayant atteint leur quota.

Aucune action courante ne doit nécessiter une ligne de commande.

---

## 13. Notifications

Des notifications doivent être prévues pour les événements importants.

### Pour les utilisateurs

- demande enregistrée ;
- téléchargement commencé ;
- contenu disponible ;
- échec du téléchargement ;
- expiration dans 3 jours ;
- expiration dans 24 heures ;
- conservation acceptée ;
- conservation refusée ;
- suppression programmée.

### Pour l’administrateur

- nouvelle demande de conservation ;
- espace disque faible ;
- échec de suppression ;
- incohérence entre Backstage et Jellyfin ;
- erreur Radarr/Sonarr ;
- demande anormalement volumineuse ;
- quota dépassé.

Le mécanisme exact pourra être choisi ultérieurement :

- notification interne Backstage ;
- courrier électronique ;
- Gotify ;
- notification mobile ;
- combinaison de plusieurs canaux.

---

## 14. Capacité du serveur

Le HP ProDesk devrait être suffisant pour un usage domestique de deux à trois utilisateurs simultanés, en particulier lorsque les clients utilisent la lecture directe.

### Cas favorable

En lecture directe :

- Jellyfin transmet le fichier sans conversion lourde ;
- la charge processeur reste faible ;
- plusieurs lectures 1080p simultanées sont réalistes ;
- plusieurs lectures locales 4K peuvent également être envisageables selon le débit réseau et les fichiers.

### Cas nécessitant une surveillance

Le transcodage sollicite davantage le serveur.

Le processeur Intel peut utiliser Quick Sync pour accélérer certains transcodages, à condition que :

- le périphérique graphique Intel soit exposé au conteneur Jellyfin ;
- l’accélération matérielle soit activée dans Jellyfin ;
- les codecs utilisés soient compatibles ;
- le stockage et le réseau suivent.

### Objectif de dimensionnement raisonnable

Le système doit viser :

- 3 lectures 1080p simultanées en lecture directe ;
- 2 à 3 transcodages 1080p matériels selon les fichiers ;
- 1 transcodage 4K vers 1080p comme cas ponctuel ;
- éviter plusieurs transcodages 4K lourds simultanés.

Le serveur doit être connecté en Ethernet Gigabit.

---

## 15. Stockage

Le SSD système de 500 Go doit rester réservé principalement à :

- Linux ;
- Docker ;
- Backstage ;
- Jellyfin ;
- Radarr ;
- Sonarr ;
- Seerr ;
- bases de données ;
- caches ;
- miniatures ;
- journaux ;
- modèles et services annexes.

Les films, séries et sauvegardes doivent être placés sur un disque séparé.

### Organisation indicative

```text
/srv/data/
├── media/
│   ├── movies/
│   ├── series/
│   └── temporary/
├── backstage/
│   ├── database/
│   ├── assets/
│   └── backups/
├── jellyfin/
├── downloads/
│   ├── incomplete/
│   └── complete/
└── backups/
```

Le classement réel devra tenir compte des contraintes de Radarr, Sonarr et Jellyfin.

### Politique de stockage

Chaque contenu doit posséder une politique explicite :

```text
permanent
temporary
protected
pending_deletion
```

La politique ne doit pas être déduite uniquement du dossier physique.

---

## 16. Sauvegardes

Une suppression automatique augmente l’importance des sauvegardes.

À sauvegarder régulièrement :

- base de données Backstage ;
- configuration Docker Compose ;
- fichiers `.env` dans un emplacement sécurisé ;
- configuration Jellyfin ;
- configuration Radarr ;
- configuration Sonarr ;
- configuration Seerr ;
- listes utilisateurs ;
- règles de location ;
- journaux d’administration essentiels.

Les fichiers vidéo récupérables ne nécessitent pas forcément la même stratégie de sauvegarde que les données personnelles ou la base de Backstage.

---

# 17. Feuille de route

## Phase 0 — Audit de l’existant

Objectif : comprendre précisément ce qui fonctionne déjà avant de modifier l’architecture.

- [ ] Cartographier la structure actuelle du dépôt.
- [ ] Identifier le framework, la base de données et le système d’authentification.
- [ ] Documenter l’intégration Jellyfin existante.
- [ ] Identifier les modèles de données actuels.
- [ ] Repérer les fonctionnalités déjà présentes mais non branchées.
- [ ] Inventorier les routes API existantes.
- [ ] Identifier les fichiers de configuration.
- [ ] Vérifier l’état actuel de la dockerisation.
- [ ] Vérifier les tests existants.
- [ ] Dresser la liste des travaux déjà terminés, partiellement terminés ou absents.

Livrable attendu :

```text
État actuel de Backstage
├── fonctionnel
├── partiellement fonctionnel
├── à corriger
├── non branché
└── à créer
```

---

## Phase 1 — Dockerisation stable

Objectif : exécuter Backstage proprement sur le serveur.

- [ ] Créer ou fiabiliser le Dockerfile.
- [ ] Créer le fichier Docker Compose.
- [ ] Configurer les variables d’environnement.
- [ ] Séparer les données persistantes du conteneur.
- [ ] Ajouter une politique de redémarrage.
- [ ] Ajouter un contrôle de santé.
- [ ] Tester l’arrêt et le redémarrage sans perte de données.
- [ ] Installer Backstage dans Portainer.
- [ ] Documenter le déploiement local et serveur.

Critère de réussite :

> Backstage peut être supprimé, reconstruit et redéployé sans perte de données.

---

## Phase 2 — Déploiement depuis GitHub

Objectif : simplifier les mises à jour.

### Étape initiale

- [ ] Cloner le dépôt sur le serveur.
- [ ] Tester `git pull`.
- [ ] Tester `docker compose up -d --build`.
- [ ] Documenter le retour à la version précédente.

### Étape cible

- [ ] Créer une image Docker versionnée.
- [ ] Mettre en place GitHub Actions.
- [ ] Publier l’image dans GitHub Container Registry.
- [ ] Déployer l’image depuis Docker Compose.
- [ ] Tester une mise à jour sans perte de données.
- [ ] Tester un retour arrière.
- [ ] Ajouter une stratégie `dev`, `stable` et éventuellement des versions numérotées.

Critère de réussite :

> Une fusion validée sur la branche stable permet de déployer une nouvelle version de Backstage sur le serveur sans intervention technique complexe.

---

## Phase 3 — Comptes et rôles

Objectif : créer la base multi-utilisateur.

- [ ] Ajouter les comptes utilisateurs.
- [ ] Ajouter les rôles administrateur et utilisateur.
- [ ] Protéger les routes administrateur.
- [ ] Ajouter une gestion de session sécurisée.
- [ ] Ajouter un tableau de bord propre à chaque utilisateur.
- [ ] Ajouter les listes personnelles.
- [ ] Ajouter les favoris personnels.
- [ ] Ajouter l’historique personnel.
- [ ] Prévoir la désactivation d’un compte.
- [ ] Ajouter un journal des actions administratives importantes.

Critère de réussite :

> Deux utilisateurs peuvent consulter le même catalogue sans partager leurs listes, favoris ou historique.

---

## Phase 4 — Comptes Jellyfin individuels

Objectif : séparer correctement les lectures.

- [ ] Associer chaque compte Backstage à un compte Jellyfin.
- [ ] Stocker cette association de manière sécurisée.
- [ ] Utiliser la session Jellyfin de l’utilisateur connecté.
- [ ] Synchroniser la progression.
- [ ] Synchroniser le statut vu/non vu.
- [ ] Vérifier la reprise de lecture.
- [ ] Gérer les erreurs de liaison.
- [ ] Prévoir une procédure de reconnexion Jellyfin.

Critère de réussite :

> Deux utilisateurs peuvent regarder le même film avec une progression indépendante.

---

## Phase 5 — Catalogue commun et données personnelles

Objectif : éviter les doublons et structurer correctement les relations.

- [ ] Unifier le modèle de contenu.
- [ ] Définir clairement les films et les séries.
- [ ] Ajouter une relation utilisateur-contenu.
- [ ] Gérer les statuts personnels.
- [ ] Détecter les doublons TMDb/Jellyfin.
- [ ] Synchroniser la disponibilité depuis Jellyfin.
- [ ] Gérer les contenus supprimés hors de Backstage.
- [ ] Gérer les métadonnées manquantes.

Critère de réussite :

> Un film n’existe qu’une fois dans le catalogue, mais chaque utilisateur peut lui associer ses propres informations.

---

## Phase 6 — Intégration Seerr, Radarr et Sonarr

Objectif : permettre les demandes autonomes.

- [ ] Installer Seerr.
- [ ] Relier Seerr à Jellyfin.
- [ ] Relier Seerr à Radarr.
- [ ] Relier Seerr à Sonarr.
- [ ] Configurer les comptes et permissions.
- [ ] Autoriser l’approbation automatique.
- [ ] Définir un profil de qualité 1080p.
- [ ] Ajouter les quotas.
- [ ] Intégrer les demandes depuis Backstage.
- [ ] Afficher les statuts de téléchargement.
- [ ] Gérer les erreurs et annulations.
- [ ] Empêcher les demandes en double.

Critère de réussite :

> Un utilisateur peut demander un film absent et le voir apparaître automatiquement dans Jellyfin sans validation manuelle préalable.

---

## Phase 7 — Locations temporaires pour les films

Objectif : gérer le cycle de vie temporaire des téléchargements des colocataires.

- [ ] Ajouter le modèle de location.
- [ ] Ajouter la politique `temporary`.
- [ ] Enregistrer la date de disponibilité.
- [ ] Calculer l’expiration initiale à 21 jours.
- [ ] Détecter la première lecture.
- [ ] Recalculer l’expiration à 7 jours.
- [ ] Détecter la fin de lecture.
- [ ] Programmer la suppression à 48 heures.
- [ ] Afficher le temps restant.
- [ ] Ajouter les avertissements d’expiration.
- [ ] Gérer plusieurs demandes sur le même film.
- [ ] Suspendre une suppression en cas de conflit.
- [ ] Ajouter un processus de nettoyage quotidien.
- [ ] Ajouter un mode simulation sans suppression réelle.
- [ ] Journaliser chaque décision de suppression.

Critère de réussite :

> Un film temporaire est automatiquement géré de sa demande jusqu’à sa suppression, sans risque de supprimer un contenu permanent ou encore utilisé.

---

## Phase 8 — Conservation définitive

Objectif : permettre à un utilisateur de proposer un contenu pour la collection permanente.

- [ ] Ajouter le bouton « Demander à conserver ».
- [ ] Créer le statut `keep_requested`.
- [ ] Suspendre l’expiration.
- [ ] Ajouter la file administrateur.
- [ ] Afficher la taille et la date d’expiration.
- [ ] Ajouter les boutons Conserver, Refuser et Prolonger.
- [ ] Transformer une location en contenu permanent.
- [ ] Annuler toute suppression programmée.
- [ ] Notifier l’utilisateur.
- [ ] Journaliser la décision.

Critère de réussite :

> Hugo peut rendre un film permanent en un seul clic depuis l’interface Backstage.

---

## Phase 9 — Quotas et protection du stockage

Objectif : empêcher le remplissage incontrôlé du disque.

- [ ] Limiter le nombre de locations simultanées.
- [ ] Limiter le volume temporaire par utilisateur.
- [ ] Définir un seuil minimal d’espace libre.
- [ ] Bloquer les nouvelles demandes sous ce seuil.
- [ ] Afficher l’espace temporaire utilisé.
- [ ] Afficher l’espace permanent utilisé.
- [ ] Ajouter des alertes administrateur.
- [ ] Permettre une exception manuelle.
- [ ] Définir des règles différentes selon les utilisateurs.

Critère de réussite :

> Aucun utilisateur ne peut saturer le disque sans avertissement ou blocage automatique.

---

## Phase 10 — Expérience administrateur

Objectif : administrer Backstage sans commandes.

- [ ] Ajouter un tableau de bord système.
- [ ] Ajouter les demandes de conservation.
- [ ] Ajouter les expirations proches.
- [ ] Ajouter les suppressions programmées.
- [ ] Ajouter les téléchargements en cours.
- [ ] Ajouter les erreurs.
- [ ] Ajouter l’état des services.
- [ ] Ajouter les quotas utilisateurs.
- [ ] Ajouter les actions rapides.
- [ ] Ajouter un historique d’administration.

Critère de réussite :

> Toutes les actions courantes sont réalisables depuis l’interface Backstage.

---

## Phase 11 — Notifications

Objectif : rendre le système compréhensible sans surveillance constante.

- [ ] Ajouter les notifications internes.
- [ ] Ajouter les notifications d’expiration.
- [ ] Ajouter les notifications de disponibilité.
- [ ] Ajouter les notifications de conservation.
- [ ] Ajouter les alertes de stockage.
- [ ] Choisir un canal externe éventuel.
- [ ] Permettre à chaque utilisateur de régler ses préférences.

---

## Phase 12 — Séries temporaires

Objectif : étendre le système aux séries après validation du modèle pour les films.

- [ ] Définir l’unité temporaire : série, saison ou épisode.
- [ ] Gérer les saisons en cours.
- [ ] Gérer les nouveaux épisodes automatiques.
- [ ] Éviter de supprimer une saison encore regardée.
- [ ] Gérer plusieurs utilisateurs sur une même série.
- [ ] Gérer les séries terminées et en cours de diffusion.
- [ ] Adapter les demandes de conservation.
- [ ] Tester la suppression via Sonarr.

Cette phase ne doit pas être commencée avant stabilisation complète des locations de films.

---

## Phase 13 — Tests, supervision et sauvegardes

Objectif : fiabiliser le système sur le long terme.

- [ ] Ajouter des tests unitaires.
- [ ] Ajouter des tests d’intégration.
- [ ] Ajouter des tests du cycle de location.
- [ ] Ajouter des tests multi-utilisateurs.
- [ ] Tester les erreurs Jellyfin.
- [ ] Tester les erreurs Seerr.
- [ ] Tester les erreurs Radarr/Sonarr.
- [ ] Tester les suppressions interrompues.
- [ ] Tester la restauration des données.
- [ ] Ajouter des sauvegardes automatisées.
- [ ] Ajouter une supervision des conteneurs.
- [ ] Ajouter une procédure de récupération après panne.

---

# 18. Priorités pour une première version utilisable

La première version réellement utile ne doit pas chercher à tout faire.

## MVP recommandé

1. Dockerisation stable de Backstage ;
2. comptes administrateur et utilisateurs ;
3. comptes Jellyfin distincts ;
4. catalogue commun avec listes personnelles ;
5. demande automatique de films via Seerr et Radarr ;
6. qualité limitée à 1080p ;
7. maximum de 3 locations simultanées par utilisateur ;
8. durée initiale de 21 jours ;
9. bouton « Demander à conserver » ;
10. validation administrateur en un clic ;
11. nettoyage automatique sécurisé ;
12. tableau de bord administrateur minimal ;
13. sauvegarde de la base de données.

## Hors MVP

À reporter après stabilisation :

- séries temporaires ;
- recommandations avancées ;
- application mobile native ;
- notifications complexes ;
- profils invités ;
- personnalisation poussée des règles ;
- statistiques avancées ;
- automatisation complète du déploiement ;
- accès distant public sans VPN.

---

# 19. Principes de conception à conserver

- Backstage reste l’unique interface principale.
- Les services techniques sont masqués aux utilisateurs.
- Les téléchargements ordinaires sont autonomes.
- La conservation définitive est contrôlée par l’administrateur.
- Un contenu temporaire ne doit jamais polluer indéfiniment le disque.
- Un contenu permanent ne doit jamais être supprimé automatiquement.
- Les données utilisateurs sont séparées du catalogue commun.
- Chaque utilisateur possède son compte Jellyfin.
- Les conteneurs sont remplaçables.
- Les données sont persistantes.
- Les secrets ne sont jamais stockés dans GitHub.
- Toute suppression doit être vérifiable, journalisée et réversible autant que possible.
- La version films doit être stabilisée avant de gérer les séries temporaires.
- L’interface doit éviter toute nécessité de ligne de commande.

---

# 20. Informations à compléter lors du prochain audit

Lors de la prochaine étape, compléter cette note avec :

- technologies exactes utilisées par Backstage ;
- arborescence actuelle du dépôt ;
- base de données actuelle ;
- système d’authentification actuel ;
- état de l’intégration Jellyfin ;
- fonctionnalités déjà terminées ;
- fonctionnalités partiellement terminées ;
- fonctionnalités perdues ou non branchées ;
- dette technique connue ;
- ports utilisés ;
- volumes Docker nécessaires ;
- variables d’environnement ;
- méthode actuelle de lancement ;
- tests existants ;
- captures de l’interface ;
- feuille de route historique du projet.

Ces informations permettront de transformer ce document de vision en plan d’implémentation précis, adapté au code déjà présent, sans recréer inutilement des fonctionnalités existantes.
