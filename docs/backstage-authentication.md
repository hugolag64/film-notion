# Authentification Backstage

## Première installation

Après le premier démarrage, ouvrir :

```text
http://192.168.1.5:8090
```

L’écran de première installation demande le nom affiché, l’adresse email et un mot de passe d’au moins 8 caractères. Le premier compte devient automatiquement administrateur.

Le mot de passe est haché dans SQLite. Il n’est pas nécessaire et il ne faut pas le placer dans GitHub, `.env` ou les variables Portainer.

## Connexion et appareil mémorisé

Lors de la connexion, cocher **Se souvenir de cet appareil** pour conserver la session pendant 30 jours. Le navigateur reçoit un cookie `HttpOnly`; le jeton brut n’est pas accessible à JavaScript.

Depuis le menu du compte, il est possible de :

- voir les appareils actifs ;
- révoquer un appareil ;
- révoquer tous les autres appareils ;
- se déconnecter ;
- pour un administrateur, créer, activer ou désactiver des utilisateurs et modifier leur rôle.

## Liaison avec Jellyfin

Avec une clé API Jellyfin configurée, un administrateur peut associer les comptes depuis **Compte → Utilisateurs** :

1. ouvrir le sélecteur Jellyfin à droite du compte Backstage ;
2. choisir le compte Jellyfin correspondant ;
3. laisser **Jellyfin : Non associé** pour retirer la liaison.

Un compte Jellyfin ne peut être associé qu’à un seul compte Backstage. Cette association ne crée, ne supprime et ne modifie aucun compte Jellyfin. Elle prépare la personnalisation future du suivi de lecture.

### Progression Jellyfin par utilisateur

Après association, Backstage synchronise la progression du compte Jellyfin correspondant et affiche **Reprendre la lecture**, les **prochains épisodes** et les médias **récemment terminés**. Les données sont séparées par compte Backstage : la progression d’Hugo n’est jamais affichée à Ophélie.

La synchronisation se lance à l’ouverture de l’application et peut être relancée avec **Actualiser**. Une indisponibilité temporaire de Jellyfin ne bloque pas le catalogue local.

## Déploiement Portainer

La stack doit utiliser la branche `main` et conserver le volume :

```text
/srv/data/backstage:/data
```

Avant un redéploiement, vérifier que la base est présente :

```bash
sudo ls -lh /srv/data/backstage/backstage.db
```

Pour publier une nouvelle version :

1. pousser les commits sur GitHub ;
2. ouvrir la stack `backstage` dans Portainer ;
3. cliquer sur **Pull and redeploy** ;
4. attendre l’état `running` ;
5. vérifier `http://192.168.1.5:8090/health`.

Les tables `users` et `auth_sessions`, ainsi que la colonne de liaison Jellyfin, sont ajoutées automatiquement. Elles ne modifient pas les tables `media`, `episode` et `media_availability`.

## Récupération d’une session

Si un appareil mémorisé pose problème, ouvrir le site dans une fenêtre privée ou supprimer les cookies du site, puis se reconnecter. La révocation depuis un autre appareil invalide immédiatement la session concernée.

Ne pas supprimer `/srv/data/backstage/backstage.db` pour résoudre un problème de connexion : cette base contient aussi le catalogue média.
## Gestion des mots de passe

Chaque utilisateur peut modifier son mot de passe depuis **Compte → Changer mon mot de passe**. Les autres appareils sont alors déconnectés.

Depuis l’écran de connexion, **Mot de passe oublié ?** envoie un lien à l’adresse e-mail enregistrée pour le compte. Le lien est valable une heure et ne peut être utilisé qu’une seule fois.

Un administrateur peut aussi définir directement le mot de passe d’un utilisateur depuis la liste **Utilisateurs**. Les mots de passe existants ne sont jamais lisibles.

### Configuration Gmail dans Portainer

Active la validation en deux étapes sur le compte Gmail d’envoi, puis crée un **mot de passe d’application Google**. Il ne faut pas utiliser le mot de passe Gmail principal.

Dans la stack `backstage`, ajoute ces variables d’environnement :

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=adresse-gmail-d-envoi@gmail.com
SMTP_PASSWORD=mot-de-passe-d-application-google
SMTP_FROM=adresse-gmail-d-envoi@gmail.com
BACKSTAGE_PUBLIC_URL=https://backstage.home.arpa
```

`SMTP_PASSWORD` reste uniquement dans Portainer. Après le déploiement, teste avec **Mot de passe oublié ?** sur un compte non administrateur.
