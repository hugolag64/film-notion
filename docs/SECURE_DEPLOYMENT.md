# Deploiement securise de Backstage

Ce guide decrit le profil recommande pour un serveur familial ou LAN. Backstage est une application mono-instance : le rate limiter d'authentification est conserve en memoire du processus. Un deploiement avec plusieurs replicas necessitera un stockage partage pour les limites et les sessions.

## 1. Exposition reseau

Choisir un seul profil :

- LAN de confiance : publier Backstage uniquement sur le reseau prive.
- VPN : ne pas exposer le port directement sur Internet ; faire passer l'acces par le VPN.
- Reverse proxy HTTPS : terminer TLS devant Backstage et ne publier le port applicatif que sur le reseau interne.

Ne pas publier directement le port 8090 sur Internet. Le reverse proxy doit rediriger HTTP vers HTTPS, limiter les tailles de requete et transmettre uniquement les en-tetes necessaires.

## 2. Cookies et secrets

En production, utiliser :

    BACKSTAGE_COOKIE_SECURE=1
    BACKSTAGE_PUBLIC_URL=https://backstage.example.invalid

Conserver TMDB_API_KEY, les cles Radarr/Sonarr/Seerr/Jellyfin, SMTP_PASSWORD et les mots de passe hors Git. Utiliser un fichier .env protege, un secret manager ou des variables injectees par l'orchestrateur. Ne jamais copier un fichier .env ou une base contenant des tokens dans un ticket ou un log.

Rotation recommandee :

1. changer les cles des services externes ;
2. changer SMTP_PASSWORD ;
3. supprimer les anciennes sessions Backstage depuis l'administration ;
4. verifier que les anciennes cles ne sont plus presentes dans les sauvegardes accessibles.

## 3. Rate limiting

Les endpoints login et forgot-password appliquent une limite par identifiant et adresse IP. Les valeurs sont configurables :

    AUTH_RATE_LIMIT_WINDOW_SEC=300
    AUTH_RATE_LIMIT_MAX_ATTEMPTS=5
    AUTH_RATE_LIMIT_BLOCK_SEC=900

Ces limites sont locales au processus. Pour plusieurs replicas, utiliser un store partage et appliquer la meme politique au reverse proxy.

## 4. Donnees et sauvegardes

Le volume de donnees doit contenir la base active, mais BACKUP_DIR doit pointer vers un volume separe ou une destination externe. Une copie dans le meme volume ne protege pas contre sa perte.

Exemple :

    DB_PATH=/data/backstage.db
    BACKUP_DIR=/backup/backstage

Verifier :

- l'age de la derniere sauvegarde ;
- l'integrite SQLite ;
- la lisibilite du fichier ;
- l'espace disponible sur la destination ;
- l'absence de secrets en clair dans les logs.

## 5. Exercice de restauration

Faire un exercice au moins une fois par trimestre :

1. arreter ou isoler une instance de test ;
2. restaurer une copie de backstage.db dans un dossier vide ;
3. demarrer Backstage avec DB_PATH pointe vers cette copie ;
4. verifier login, catalogue, etats personnels, locations et recommandations ;
5. executer l'endpoint d'administration de verification ;
6. consigner la date, la sauvegarde utilisee et le resultat ;
7. ne remplacer la base de production qu'apres validation.

Une sauvegarde qui n'a jamais ete restauree n'est pas consideree comme validee.

## 6. Controle de sante et mise a jour

Avant une mise a jour :

- lancer la suite de tests et le build frontend ;
- creer une sauvegarde ;
- verifier les migrations SQLite ;
- conserver l'image precedente pour rollback ;
- verifier /health apres redemarrage ;
- consulter le statut des integrations media.

Apres une panne d'integration, l'interface doit afficher un statut indisponible et l'administration doit permettre de verifier la derniere synchronisation.

## 7. Checklist de production

- [ ] acces limite au LAN, VPN ou reverse proxy ;
- [ ] HTTPS actif ;
- [ ] BACKSTAGE_COOKIE_SECURE=1 ;
- [ ] secrets injectes hors Git ;
- [ ] BACKUP_DIR sur un volume externe ou separe ;
- [ ] restauration testee ;
- [ ] rate limiting configure ;
- [ ] sessions anciennes revoquees apres rotation ;
- [ ] healthcheck actif ;
- [ ] procedure de rollback disponible.
