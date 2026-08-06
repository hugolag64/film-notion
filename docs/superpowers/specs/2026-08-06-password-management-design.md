# Gestion des mots de passe Backstage

## Objectif

Permettre à chaque utilisateur de modifier son propre mot de passe, de demander un lien de réinitialisation envoyé à l’adresse e-mail enregistrée par l’administrateur, et permettre à un administrateur de définir directement le mot de passe d’un utilisateur.

## Parcours utilisateur

### Modification depuis un compte connecté

Dans le panneau Compte, l’utilisateur saisit son mot de passe actuel, le nouveau mot de passe et sa confirmation. Le serveur vérifie le mot de passe actuel, impose au moins 8 caractères pour le nouveau, remplace le hash et révoque toutes les sessions de l’utilisateur sauf la session courante.

### Mot de passe oublié

Depuis l’écran de connexion, l’utilisateur saisit son adresse e-mail. Le serveur répond de manière identique que l’adresse existe ou non afin d’éviter l’énumération des comptes. Si elle existe et correspond à un compte actif, un jeton aléatoire à usage unique est stocké sous forme de hash avec une expiration d’une heure, puis un e-mail Gmail SMTP contient un lien vers Backstage.

Le lien ouvre un écran de nouveau mot de passe. Après validation, le jeton est consommé, le hash est remplacé et toutes les sessions existantes de l’utilisateur sont révoquées.

### Réinitialisation par un administrateur

Dans la liste des utilisateurs, un administrateur peut saisir un nouveau mot de passe pour un compte. Le serveur hash le mot de passe, l’enregistre et révoque toutes les sessions de l’utilisateur. Le mot de passe n’est jamais renvoyé par l’API ni affiché après l’enregistrement.

## Architecture

- `AuthStore` ajoute une table `password_reset_tokens` additive pour les jetons de récupération.
- Les mots de passe continuent d’utiliser le format scrypt existant.
- Les jetons sont générés avec `secrets.token_urlsafe`, stockés uniquement sous forme de SHA-256 et consommés dans une transaction.
- Un service d’e-mail séparé construit le message et utilise `smtplib` avec STARTTLS sur Gmail (`smtp.gmail.com:587`).
- Les paramètres SMTP sont fournis par variables d’environnement Docker ; aucun secret ne va dans Git ou SQLite.
- Les liens utilisent l’origine publique configurée par `BACKSTAGE_PUBLIC_URL`.

## API prévue

- `POST /api/auth/change-password`
  - Authentifié.
  - Entrée : `current_password`, `new_password`, `password_confirmation`.
- `POST /api/auth/forgot-password`
  - Public.
  - Entrée : `email`.
  - Réponse générique `202` sans révéler l’existence du compte.
- `POST /api/auth/reset-password`
  - Public.
  - Entrée : `token`, `new_password`, `password_confirmation`.
- `PATCH /api/auth/users/{user_id}` étendu avec un champ `password` réservé aux administrateurs.

## Configuration Gmail

Variables Docker :

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=adresse-gmail-d-envoi@gmail.com
SMTP_PASSWORD=mot-de-passe-d-application-google
SMTP_FROM=adresse-gmail-d-envoi@gmail.com
BACKSTAGE_PUBLIC_URL=https://backstage.home.arpa
```

`SMTP_PASSWORD` est un mot de passe d’application Google, jamais le mot de passe Gmail principal. Les variables sensibles seront documentées dans `.env.example` sans valeur réelle et saisies dans Portainer.

## Sécurité et erreurs

- Minimum de 8 caractères pour tous les nouveaux mots de passe.
- Comparaison du mot de passe actuel avec le hash scrypt.
- Jeton de récupération à usage unique et valable une heure.
- Réponse identique pour une adresse inconnue ou connue sur la demande de récupération.
- Révocation des sessions après toute réinitialisation.
- L’administrateur ne peut pas lire les mots de passe existants.
- Les jetons expirés ou consommés sont supprimés périodiquement lors des opérations de récupération.
- Les erreurs de validation sont retournées sans exposer de secret.

## Interface

- Ajouter **Mot de passe oublié ?** sous le formulaire de connexion.
- Ajouter une vue de réinitialisation accessible avec `?token=...`.
- Ajouter une section **Changer mon mot de passe** dans le panneau Compte.
- Ajouter un formulaire **Définir le mot de passe** dans chaque ligne utilisateur de l’espace administrateur.
- Afficher un message générique après une demande de récupération : « Si un compte correspond, un e-mail vient d’être envoyé. »

## Tests et critères d’acceptation

- Un utilisateur peut changer son mot de passe avec son ancien mot de passe correct.
- Un ancien mot de passe incorrect est refusé.
- Un nouveau mot de passe de moins de 8 caractères est refusé.
- Le jeton de récupération est expiré après une heure et inutilisable une seconde fois.
- Une demande sur une adresse inconnue ne révèle pas l’existence d’un compte.
- Le lien de récupération met bien à jour le hash et révoque les sessions.
- Un administrateur peut définir le mot de passe d’un autre utilisateur, mais un utilisateur standard reçoit `403`.
- Le message e-mail contient le lien public configuré.
- Les tests Python, le lint et le build frontend passent.
