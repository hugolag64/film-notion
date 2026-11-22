# Audit UI/UX avant déploiement en colocation — 22 novembre 2026

## 1. Verdict : NO-GO, pour l'instant

Sur téléphone, l'en-tête se chevauche : **« Films », « Séries », le menu du compte (et donc la déconnexion) et le mode sombre ne peuvent pas être touchés**. Toucher « Films » ouvre « Louer un film ». Le téléphone étant l'appareil principal des colocs, c'est un bloquant à lui seul.
Le reste du socle est sain : comptes isolés, droits admin protégés côté serveur, changement de mot de passe imposé, états vides accueillants.
**Il faut corriger 1 point P0 et environ 10 points P1 (dont la récupération de mot de passe à vérifier en prod), soit environ 2 à 3 jours de travail, avant d'ouvrir l'accès.**

---

## 2. Méthode et limites

- **Environnement** : backend lancé localement (`.venv`, port 8090) sur une **copie de la base** (`backstage.db` → base d'audit avec les comptes vidés). Radarr, Sonarr et Seerr ont été **volontairement désactivés** pour ne déclencher aucun vrai téléchargement. Frontend compilé (`npm run build`) et servi par le backend, comme en production.
- **Comptes de test** : 1 admin et 2 colocs (créés via l'écran d'administration). Aucun identifiant réel n'a été utilisé.
- **Appareils simulés** : mobile 375×812, tablette 768×1024, ordinateur 1024 px et plus. La « TV » a été évaluée par la navigation au clavier et la taille des textes.
- **Preuves** : les captures du navigateur intégré étaient peu fiables (cadrage partiel). Les preuves sont donc des **mesures du DOM** (`getBoundingClientRect`, `elementFromPoint`), des journaux réseau et console, et des extraits de code. Chaque constat précise s'il a été **[testé]** dans l'interface ou **[lu]** dans le code.
- **Non vérifié** (à faire sur l'installation réelle) :
  - la lecture effective dans Jellyfin (serveur injoignable en local, fenêtre surgissante bloquée par le navigateur d'audit) ;
  - la reprise d'un film ou d'une série réellement en cours ;
  - une demande Seerr réelle et son suivi jusqu'à « disponible » ;
  - l'envoi réel de l'e-mail de réinitialisation ;
  - un vrai lecteur d'écran ;
  - un vrai téléviseur.

### Observation pendant l'audit

Environ une minute après le démarrage du serveur d'audit (base sans admin), **un compte administrateur a été créé avec ton adresse e-mail par quelqu'un d'autre que moi**, probablement toi depuis ton navigateur habituel. Le serveur écoute sur toutes les interfaces (LAN, Tailscale). Leçon pour le déploiement : **ne jamais exposer une instance neuve avant d'avoir créé l'admin**, car le premier venu sur le réseau peut devenir administrateur via `/api/auth/setup`. En production la base contient déjà un admin, donc pas de risque immédiat.

---

## 3. Résumé exécutif

### 5 forces

1. **Isolation des données personnelles** [testé] : le coloc 2 ne voit ni les favoris, ni les notes, ni la watchlist du coloc 1. Toute modification du catalogue partagé (`DELETE` ou `PATCH /api/medias`, `/api/admin/*`, liste des utilisateurs) renvoie **403** pour un coloc.
2. **Premier accès sécurisé** [testé] : le mot de passe provisoire impose un changement, et le serveur refuse toute API tant que ce n'est pas fait (403 « Vous devez définir votre mot de passe personnel »).
3. **États vides accueillants** [testé] : « Aucun programme en cours. Commence un film… » avec un bouton d'action, ainsi que « Aucune location en cours » et « Aucune notification pour l'instant ».
4. **Recherche combinée bibliothèque + TMDB** [testé] : rapide, résultats « Dans ma bibliothèque » distingués des résultats « Disponible sur TMDB », et « Aucun titre trouvé. Essaie un autre nom. » en cas d'échec.
5. **Progrès depuis août** : bundle passé de 817 kB à **371 kB** (100 kB gzip) ; cloche de notifications avec compteur de non-lus ; modales de location et de recommandation avec `role="dialog"` ; disponibilité fournie aux non-admins (`/api/library/available`) ; blocage après 5 échecs de connexion.

### 5 problèmes les plus graves

1. **P0 — En-tête cassé sur mobile** : la navigation et le compte sont inaccessibles (UX-01).
2. **P1 — Bouton retour du téléphone** : il quitte l'app au lieu de fermer la fiche, car l'URL ne change jamais (UX-04).
3. **P1 — Session expirée = clics silencieux** : rien ne se passe, aucun message (UX-03).
4. **P1 — Jargon technique exposé aux colocs** : « Demander via Seerr », « script JavaScript Injector », « TMDB sera connecté »… (UX-07).
5. **P1 — Fausses informations** : durée « 120 min » affichée pour tous les films, titre en arabe en tête des recommandations (UX-05, UX-08).

### Score par critère (/10)

| Critère | Score | Commentaire |
|---|---|---|
| 1. Compréhension et prise en main | 5 | Pas d'écran d'accueil ni de visite guidée ; concept de location dense ; jargon |
| 2. Règles d'ergonomie (Nielsen) | 5 | Erreurs silencieuses, pas de retour arrière, messages techniques |
| 3. Organisation et navigation | 4 | Pas d'URL ni d'historique ; le bouton « Choisir un film » de la barre latérale disparaît à 1024 px |
| 4. États de l'interface | 6 | États vides bons ; catalogue sans état chargement/erreur (U1 toujours ouvert) |
| 5. Design visuel et cohérence | 6 | Deux identités visuelles (connexion beige vs app blanche/violette) ; emojis comme icônes |
| 6. Responsive et multi-appareil | **2** | En-tête mobile inutilisable ; cibles tactiles de 11 à 24 px |
| 7. Accessibilité | 4 | `lang="en"`, champs sans nom accessible, focus non piégé, Échap incohérent |
| 8. Performance perçue | 6 | Recommandations en 1,5 s ; mais 249 affiches chargées d'un coup |
| 9. Fiabilité et erreurs | 5 | Erreurs avalées, `[object Object]`, reset mot de passe « envoyé » sans e-mail |
| 10. Multi-utilisateur et confiance | 7 | Bonne isolation ; « Mon activité » montre celle des autres |
| 11. Textes | 5 | Tu et vous mélangés, anglais résiduel, genres en anglais |

---

## 4. Résultats par parcours

| # | Parcours | Résultat | Constat |
|---|---|---|---|
| P1 | Premier accès (admin crée le compte, coloc se connecte, change son mot de passe) | ✅ Réussi avec difficulté | ~6 actions, < 1 min. Mais **aucun écran d'accueil** expliquant l'app ; le mot de passe provisoire peut être réutilisé comme définitif ; pas de bouton de déconnexion sur l'écran de changement forcé |
| P2 | Mot de passe oublié | ⚠️ Faux succès | L'interface affiche « un e-mail vient d'être envoyé », mais le serveur a levé `RuntimeError: SMTP non configuré`. Ton `.env` local ne contient aucune variable `SMTP_*` → **à vérifier en prod** |
| P3 | Trouver un film précis | ✅ Réussi (ordinateur) / ❌ Échec (mobile) | 2 actions au clavier sur ordinateur. Sur mobile, le champ de recherche recouvre le menu du compte. Aucune tolérance aux fautes (« inteqstellar » → 0 résultat) ; 5 résultats bibliothèque au maximum (« nolan » ne remonte ni Inception ni Interstellar) |
| P4 | « On regarde quoi ? » → recommandations | ✅ Réussi avec difficulté | 5 questions, résultats en **1,5 s**. 1ʳᵉ suggestion : « أوسكار: عودة الماموث » (titre arabe) ; explications génériques sans lien avec les réponses ; « Sonic 3 » pour « science-fiction + énigme » ; bouton « Demander via Seerr » |
| P5 | Fiche → Lire → revenir | ⚠️ Non vérifiable | Le clic ouvre une fenêtre surgissante (bloquée ici). Message prévu si elle est bloquée : bon. Si Jellyfin ne répond pas : **25 s sans retour visuel**, puis un message pour développeur. La fiche affiche « Disponible… Lecture immédiate » même quand Jellyfin est injoignable |
| P6 | Reprendre un contenu en cours | ⚠️ Non vérifiable | Section « Continuer à regarder » bien placée en tête de l'accueil ; pas de progression réelle disponible en local |
| P7 | Demander un film absent | ❌ Échec (attendu, Seerr coupé) | Message « Seerr n'est pas configuré », toast de 4 s sans `aria-live`. **Pour une série, aucun chemin** : le bouton « Louer » est masqué pour les colocs dans Séries |
| P8 | Favoris, watchlist, note | ✅ Réussi (ordinateur) | Les actions s'appliquent. Étoiles de 11×22 px, inutilisables au doigt ; noter un film retire silencieusement la watchlist ; cœur de 24×24 px sans libellé dans la grille |
| P9 | Location et quota | ✅ Compréhensible | « LOCATIONS · 0/5 » et règles expliquées sur l'accueil (texte dense, 12 px, faible contraste). Quota de recommandations affiché (« 4 sur 5 sélections ») |
| P10 | Admin : créer des colocs, gérer | ✅ Réussi | Création en 4 champs, message clair sur le mot de passe provisoire, confirmation avant suppression. Toast « Jellyfin est indisponible » sans contexte ; Échap ne ferme pas le centre d'admin ; la bibliothèque reste cliquable derrière |
| P11 | Déconnexion, session expirée, isolation | ⚠️ Partiel | Isolation ✅. Session expirée : **le clic sur ♡ ne fait rien, sans message ni retour à la connexion** |

---

## 5. Tableau des problèmes

Effort : S = moins d'une demi-journée, M = 1 jour, L = plus.

### P0 — Bloquant

| ID | Critère | Écran | Description et reproduction | Preuve | Fichier | Recommandation | Effort |
|---|---|---|---|---|---|---|---|
| UX-01 ✅ corrigé le 22/11 (barre d'onglets en bas sous 1024 px, recherche dépliable, grille `auto 1fr auto` ; vérifié à 375, 768, 1024, 1280 et 1440 px) | Responsive | En-tête, mobile et tablette | Sur un écran de 375 px, ouvrir l'accueil et toucher « Films » ouvre **« Louer un film »**. « Séries », le menu du compte (déconnexion, profil) et le mode sombre sont recouverts par le champ de recherche. En tablette (768 px), « Louer un film » est recouvert par la recherche. | [testé] `elementFromPoint` : Films → « Louer un film » ; compte et mode sombre → champ de recherche. Boîtes : logo x24–204, Accueil x42–95, Louer x109–205, sur la même ligne | `BackstagePrototype.jsx:1217` (`grid-cols-[1fr_auto_1fr]` sans breakpoint, recherche `w-56 min-w-[10rem]`) | Sous `md` : logo + cloche + compte en haut, **barre d'onglets en bas** (Accueil / Films / Séries / Rechercher), recherche en plein écran derrière une icône, « Louer » dans l'accueil | M |

### P1 — À corriger avant le déploiement

| ID | Critère | Écran | Description et reproduction | Preuve | Fichier | Recommandation | Effort |
|---|---|---|---|---|---|---|---|
| UX-02 ✅ corrigé le 22/11 (sans SMTP, l'API répond 503 avec « demande à l'administrateur un mot de passe provisoire » ; message de secours après envoi ; le SMTP de prod reste à vérifier) | Fiabilité | Mot de passe oublié | Saisir son e-mail : « un e-mail vient d'être envoyé », mais rien n'est envoyé si le SMTP manque | [testé] journal : `RuntimeError: SMTP non configuré` ; `.env` local sans `SMTP_*` | `auth_api.py` (forgot-password), `core/email.py:16` | Vérifier le SMTP en prod **avant** l'ouverture. Sinon, afficher « Demande à l'admin de réinitialiser ton mot de passe » (le bouton « Définir et exiger un changement » existe déjà côté admin) | S |
| UX-03 ✅ corrigé le 22/11 (`apiFetch` commun : un 401 renvoie à la connexion avec « Ta session a expiré » ; les autres erreurs affichent un toast) | Erreurs | Partout | Laisser la session expirer (ou se déconnecter dans un autre onglet), puis cliquer ♡ : rien ne se passe | [testé] coeur inchangé, aucun toast, pas d'écran de connexion | `api.js:62` (401 géré seulement par `fetchCurrentUser`) ; `BackstagePrototype.jsx:807` (`catch` → `console.error`) | Fonction `request()` commune : un 401 déconnecte et affiche « Ta session a expiré, reconnecte-toi » ; toute autre erreur affiche un toast | S |
| UX-04 ✅ corrigé le 22/11 (le retour ferme la fiche ou la modale du dessus ; chaque fiche a son adresse `/film/<id>` ou `/serie/<id>`, servie par `main.py` ; un lien partagé ouvre la fiche après connexion ; bouton « Partager » (partage du téléphone, sinon copie du lien) ; vérifié : lien direct → fiche, retour → `/` sans recharger) | Navigation | Fiches, vues | Ouvrir une fiche puis faire le geste retour Android : on **quitte l'app**. Impossible de partager le lien d'un film à un coloc | [testé] `location.href` reste `/` ; `history.length` = 1 | `BackstagePrototype.jsx` (vues en état local) | Routes simples (`/films`, `/series`, `/film/:id`) via `history.pushState`, ou au minimum un `pushState` à l'ouverture d'une fiche et la fermeture sur `popstate` | M |
| UX-05 ✅ corrigé le 22/11 (durée TMDB réelle, « 2 h 49 », sinon rien) | Confiance | Fiche film | Toutes les fiches affichent « • 120 min » | [testé] Interstellar « 120 min » (le vrai : 169) ; [lu] valeur codée en dur | `BackstagePrototype.jsx:118` (`runtime: '120 min'`) | Utiliser la durée TMDB (déjà fournie par `/api/tmdb/movies/{id}` : Paddington « 95 min »), sinon ne rien afficher | S |
| UX-06 ✅ corrigé le 22/11 (`useLayer` commun : `role="dialog"`, focus initial et piégé, Échap ferme la couche du dessus, retour du focus ; pas d'`inert` sur le fond) | Accessibilité, clavier | Modales | Échap ne ferme ni l'aperçu TMDB, ni le centre d'admin, ni le panneau compte, ni « Choisir un film ». Pire : Échap sur l'aperçu TMDB **ferme la modale située dessous** (« Louer un film ») et laisse l'aperçu ouvert. La fiche film et l'admin n'ont pas `role="dialog"`, le focus n'y entre pas et revient sur `<body>` à la fermeture | [testé] ; [lu] seuls `FilmDetailView.jsx:5`, `NotificationBell.jsx:35` et l'ajout `:1045` gèrent Échap | `TMDBMoviePreview.jsx`, `AdminCenter.jsx`, `AccountPanel.jsx`, `RecommendationFlow.jsx` | Un composant `Modal` unique (`role="dialog"`, `aria-modal`, focus initial, piège du focus, Échap qui ferme **la modale du dessus**, retour du focus, `inert` sur le fond) utilisé partout | M |
| UX-07 ✅ corrigé le 22/11 (passe sur les textes côté coloc ; détails techniques réservés à l'admin) | Textes | Fiches, recommandations, toasts, accueil | Termes techniques montrés aux colocs : « Demander via Seerr », « Seerr n'est pas configuré », « Disponible sur TMDB », « ⚙️ STATUT & SUPPORT DE STOCKAGE », « Mets à jour le script JavaScript Injector », « Jellyfin indisponible », « Synchronisation indisponible », « Les recommandations seront disponibles dès que TMDB sera connecté » (affiché dès que la liste est vide, même quand TMDB marche) | [testé] | `RecommendationFlow.jsx:41`, `BackstagePrototype.jsx:335`, `DashboardHome.jsx:235` | Glossaire côté coloc : TMDB → (rien) ou « catalogue mondial » ; Seerr → « Demander ce film » ; Jellyfin → « le lecteur ». Erreurs : « Le lecteur ne répond pas, réessaie dans quelques minutes ou préviens l'admin ». Détails techniques réservés à l'admin | S |
| UX-08 ✅ corrigé le 22/11 (titres non latins écartés ; explications construites à partir des réponses ; les films déjà sur le serveur, y compris ceux qu'il suffit de louer (location immédiate), passent en tête — 2 au maximum — avec le badge « À regarder ce soir · déjà sur le serveur » ; testé par `tests/test_guided_results.py`. Non revu en conditions réelles : il faut un Jellyfin joignable pour qu'un film compte comme disponible) | Recommandations | Choisir un film | 1ʳᵉ suggestion au titre arabe ; explications interchangeables (« C'est une piste ciblée, pas un choix au hasard ») qui ne citent ni le genre ni l'ambiance choisis ; aucune suggestion déjà disponible dans la bibliothèque | [testé] réponses « Prenant ou tendu / SF / Une énigme » → Sonic 3, Backrooms, War Machine… | `backend/core/recommendation_explanations.py`, pool `tmdb.discover_movies` | Écarter les candidats dont le titre FR n'est pas en alphabet latin (ou retomber sur `original_title` latin) ; explications construites à partir des réponses (« Tu voulais de la SF à énigme : … ») ; intercaler 1 à 2 films **déjà disponibles** (« à regarder ce soir ») | M |
| UX-09 ✅ corrigé le 22/11 (message « les séries sont ajoutées par l'administrateur » dans Séries) | Fonctionnalité | Séries (coloc) | Un coloc ne peut pas demander une série : le bouton de l'en-tête disparaît dans Séries et aucune alternative n'est proposée | [testé] en-tête coloc dans Séries : Accueil / Films / Séries / 🔔 / compte | `BackstagePrototype.jsx:1268` (`isAdmin \|\| collection !== 'Séries'`) | Soit « Demander une série » (Seerr gère les séries), soit un message « Pour une série, demande à l'admin » | S |
| UX-10 ✅ corrigé le 22/11 (5 étoiles de 44 px, re-toucher retire ½ ; cœur de 44 px avec `aria-label`/`aria-pressed`) | Tactile, accessibilité | Fiche, notation | Les demi-étoiles mesurent 11×22 px, sans nom accessible (seul un `title`) ; cœur de la grille 24×24 px, nommé uniquement par l'emoji « 🤍 » | [testé] mesures DOM | `BackstagePrototype.jsx:1977-1995`, `:1532` | Note sur 5 étoiles entières de 44 px (½ étoile via appui long ou curseur), `aria-label="Noter 4 sur 5"` ; cœur à 44 px avec `aria-label`/`aria-pressed` | S |
| UX-11 ✅ corrigé le 22/11 (lots de 48 au défilement + « Afficher plus », `loading="lazy"` ; une seule requête SQL pour les états perso) | Performance | Bibliothèque | 249 affiches et 277 boutons rendus d'un coup ; côté serveur, `/api/medias` fait une requête SQL **par film** | [testé] ; [lu] `api.py:550` → `_media_for_user` → `get_user_media_state` × 252 | `BackstagePrototype.jsx` (grille), `backend/api.py:520-551` | Pagination ou défilement progressif (lots de 40) + `loading="lazy"` ; une seule requête `list_user_media_states` fusionnée en mémoire | M |

### P2 — Première semaine

| ID | Critère | Écran | Description | Preuve | Fichier | Recommandation | Effort |
|---|---|---|---|---|---|---|---|
| UX-12 ✅ corrigé le 22/11 (tutoiement partout : connexion, accueil, fiche, e-mail, messages serveur) | Textes | Global | Tu et vous mélangés : « Pour vous », « Votre espace », « Connectez-vous », « Saisissez » vs « Tu ne sais pas… », « Loue jusqu'à… » | [testé] | `DashboardHome.jsx`, `AuthGate.jsx` | Choisir le **tu** (ton coloc) partout | S |
| UX-13 ✅ corrigé le 22/11 (section renommée « Quoi de neuf », eyebrow « VIDÉOTHÈQUE ») | Confiance | Accueil | « Mon activité récente » liste les ajouts et demandes **de tout le catalogue** (« The Last Viking — Demande en cours ») | [testé] dashboard du coloc 2 neuf | `backend/core/dashboard.py:156` | Renommer en « Nouveautés de la vidéothèque », ou filtrer sur l'utilisateur | S |
| UX-14 ✅ corrigé le 22/11 (toutes les erreurs passent par `errorDetail` ; messages du compte traduits côté serveur) | Erreurs | Création admin, formulaires | Une erreur de validation 422 s'affiche « [object Object] » ; « administrator already exists » en anglais | [testé] | `api.js:29` (`body.detail` est un tableau pydantic) ; `core/auth.py:195` | Normaliser `detail` (tableau → premier `msg`) ; traduire les `ValueError` | S |
| UX-15 ✅ corrigé le 22/11 (repli réservé au premier admin ; test ajouté) | Confiance | Bibliothèque (2ᵉ admin) | Un admin sans état personnel voit les notes, favoris et « vus » hérités du catalogue (98 vus et 2 favoris pour un admin tout neuf) | [testé] | `backend/api.py:522-525` | Réserver ce repli au propriétaire d'origine, ou migrer ces états vers son `user_media_state` | S |
| UX-16 ✅ corrigé le 22/11 (« Réessaie dans 15 minutes », calculé depuis le délai réel ; test ajouté) | Erreurs | Connexion | Après 5 échecs : « Trop de tentatives. Réessayez plus tard. » sans durée (le serveur renvoie `retry-after: 900`) | [testé] | `auth_api.py:130` | « Réessaie dans 15 minutes » (à partir de `retry-after`) | S |
| UX-17 ✅ corrigé le 22/11 (`aria-label` sur tous les champs, listes et zones de texte) | Accessibilité | Connexion, création admin, filtres | Les `<label>` ne sont pas reliés aux champs (champs sans nom accessible) ; création d'utilisateur nommée seulement par des placeholders ; listes Genre/Statut sans label | [testé] arbre d'accessibilité : `textbox` sans nom | `AuthGate.jsx:45-50`, `UserManagement.jsx`, filtres de la bibliothèque | `htmlFor`/`id` ou `<label>` englobant ; `aria-label` sur les `<select>` | S |
| UX-18 ✅ corrigé le 22/11 (toast « Ouverture du lecteur… », abandon après 10 s avec un message simple ; la fiche interroge `/api/media-server/health` (ping Jellyfin mis en cache 30 s) et affiche « Serveur de lecture hors ligne — réessaie dans quelques minutes » à la place de « Prêt à regarder » ; l'accueil traduit « Jellyfin indisponible » en mots simples pour les colocs) | Lecture | Fiche | Si Jellyfin ne répond pas : 25 s sans aucun retour, puis un message pour développeur. La fiche dit « Lecture immédiate » sans vérifier le serveur | [lu] `BackstagePrototype.jsx:333-336` ; [testé] Jellyfin injoignable | `BackstagePrototype.jsx:283-341` | Toast « Ouverture du lecteur… » immédiat, délai de 10 s, message simple ; badge « serveur hors ligne » si la dernière synchro a échoué | S |
| UX-19 ✅ corrigé le 22/11 (genres TV traduits, « Créateur » pour les séries, puces de genre réelles et cliquables) | Textes | Barre latérale, Séries | Genres en anglais (« #Horror #Sci-Fi », « War & Politics », « Action & Adventure ») ; « Réalisateur » / « Réalisateur inconnu » pour les séries | [testé] | barre latérale de la bibliothèque, mapping TMDB TV | Table de traduction des genres ; « Créateur » pour les séries | S |
| UX-20 ✅ corrigé le 22/11 (`lang="fr"`, textes d'aide en `opacity-75`, 12 px minimum, `h1` masqué sur l'accueil) | Accessibilité | Global | `<html lang="en">` (U7 toujours ouvert) ; textes d'aide `opacity-60` ≈ **2,3:1** de contraste ; titres de section en 10 px ; pas de `h1` sur l'accueil | [testé] mesure de contraste ; `index.html:2` | `proto-ui/index.html`, classes `opacity-60`/`text-[10px]` | `lang="fr"` ; textes d'aide ≥ 4,5:1 ; minimum 12 px (14 px pour la TV) | S |
| UX-21 ✅ corrigé le 22/11 (sans accents, 1 à 2 fautes tolérées selon la longueur du mot, mots à moitié tapés ; résultats classés ; bouton « Voir les N films dans la bibliothèque » ; même recherche dans la grille ; tests `npm test`) | Recherche | En-tête | Aucune tolérance aux fautes ; 5 résultats bibliothèque au maximum (« nolan » ne remonte pas ses films) | [testé] | recherche de l'en-tête | Recherche sans accents et tolérante (distance d'édition 1–2) ; section « Voir tous les résultats » | M |
| UX-22 ✅ corrigé le 22/11 (connexion aux couleurs de l'app, même logo) | Design | Connexion → app | Connexion en beige et sobre, application en blanc et violet avec un autre logo : on croit changer de site | [testé] captures | `App.css` (auth-card) vs Tailwind de l'app | Aligner les jetons (couleur, police, logo) | S |
| UX-23 ✅ corrigé le 22/11 (mot de passe provisoire refusé, lien « Se déconnecter » ; vérifié dans le navigateur) | Sécurité, UX | Changement forcé | Le mot de passe provisoire est accepté comme mot de passe définitif ; pas de bouton « Se déconnecter » sur cet écran | [testé] | `core/auth.py:369` | Refuser un mot de passe identique au provisoire ; ajouter un lien de déconnexion | S |
| UX-24 ✅ corrigé le 22/11 (squelettes au chargement, bloc d'erreur « Réessayer ») | États | Bibliothèque | Pas d'état de chargement ni d'erreur du catalogue : `const [, setLoading]` et `const [, setError]` ne sont jamais lus (U1 toujours ouvert) | [lu] `BackstagePrototype.jsx:141-142` | idem | Squelettes pendant le chargement ; bloc d'erreur « Réessayer » | S |

### P3 — Plus tard

- **UX-25** : la bibliothèque reste interactive derrière le centre d'admin (pas d'`inert`) ; l'admin ne se ferme pas avec Échap. ✅ 22/11 — tout ce qui est hors de la fenêtre ouverte (fiche, admin, compte, dialogues) passe en `inert` ; Échap ferme déjà la fenêtre du dessus.
- **UX-26** : le toast « Jellyfin est indisponible » apparaît à la création d'un utilisateur, sans dire ce que ça implique (association Jellyfin à faire plus tard). ✅ 22/11 — plus de toast : un encadré dans « Utilisateurs » explique que les comptes marchent et que l'association Jellyfin se fera plus tard.
- **UX-27** : anneau de focus du navigateur (1 px), trop discret pour la TV, et pas de lien d'évitement. Ajouter un `:focus-visible` de 3 px. ✅ 22/11 — anneau `:focus-visible` de 3 px sur tous les contrôles, lien « Aller au contenu » au premier Tab.
- **UX-28** : emojis utilisés comme icônes (🎬 👁️ 📌 🔖 ❤️ ⚙️ 🔔), rendus différemment selon les appareils et lus à voix haute. Les remplacer par des SVG avec `aria-hidden`. ✅ 22/11 — composant `Icon` (SVG `aria-hidden`) dans la barre de filtres, les toasts, les cartes, la fiche et la cloche ; plus d'emoji dans l'interface.
- **UX-29** : à 1024 px, le bouton « ✨ Choisir un film » de la barre latérale est masqué (taille 0) ; l'accès ne passe que par l'accueil. ✅ 22/11 — la barre latérale est masquée à toutes les tailles ; bouton « Choisir un film » ajouté en haut de la vue Films (vérifié à 1024 px : 146×44 px).
- **UX-30** : noter un film le passe en « Terminé » et retire la watchlist sans le dire. Ajouter un toast « Noté 4/5, marqué comme vu ». ✅ 22/11 — toast « Noté 4 / 5 — marqué comme vu et retiré de ta watchlist ».

---

## 6. Suivi des audits précédents (UX)

| Point d'août | État au 22/11 | Commentaire |
|---|---|---|
| U1 Catalogue sans chargement ni erreur | ❌ Ouvert | `BackstagePrototype.jsx:141-142` inchangé → UX-24 |
| U2 Disponibilité invisible pour les non-admins | ✅ Corrigé | `refreshAvailabilityByMedia` réservé à l'admin + `/api/library/available` pour tous |
| U3 Session expirée non gérée | ❌ Ouvert | → UX-03 |
| U4 Pool de recommandations étroit, axe « era » | 🟡 Partiel | Le flux est plus riche (5 questions, sous-questions de genre) ; la qualité et la langue posent encore problème → UX-08 |
| U5 Fiche plein écran (clic interne, dialog, focus) | 🟡 Partiel | Échap fonctionne, le clic interne ne ferme plus ; toujours ni `role="dialog"` ni piège du focus → UX-06 |
| U6 Compteurs admin non cliquables | 🟡 Partiel | La carte « Utilisateurs » est cliquable ; « Erreurs 5 » et « Téléchargements 5 » ne mènent pas directement à l'action |
| U7 `lang="en"`, aria, contraste, cibles | ❌ Ouvert | → UX-17, UX-20, UX-10 |
| U8 Pas de pagination (252 affiches) | ❌ Ouvert | → UX-11 |
| U9 Notifications peu visibles | ✅ Corrigé | Cloche dans l'en-tête avec compteur de non-lus et libellé accessible |
| Accessibilité (complet 07/08) : encodage « CrÃ©er » | ✅ Corrigé | Aucun texte mal encodé trouvé dans `src/` |
| Onboarding (complet 07/08) | ❌ Ouvert | Aucun écran d'introduction → kit de lancement ci-dessous |

---

## 7. Plan d'action priorisé

### Avant le déploiement (≈ 2 à 3 jours)

1. **UX-01** : en-tête mobile (barre d'onglets en bas).
2. **UX-02** : SMTP configuré et testé en prod, ou message de repli.
3. **UX-03** : gestion commune des 401 et des erreurs.
4. **UX-04** : bouton retour qui ferme la fiche (au minimum `pushState` et `popstate`).
5. **UX-05** : durée réelle ou rien.
6. **UX-07** : glossaire côté coloc (une passe sur les textes).
7. **UX-09** : chemin pour demander une série (ou message).
8. **UX-10** : étoiles et cœurs tactiles.
9. **UX-06** : composant `Modal` commun (au moins Échap et focus).
10. **UX-08** : filtrer les titres non latins et rendre les explications concrètes.
11. **UX-11** : défilement progressif de la bibliothèque (si le test réel sur téléphone montre de la lenteur).

### Semaine 1

UX-12 à UX-24 (presque tous en S) : tutoiement, activité renommée, `[object Object]`, repli admin, durée du blocage, labels, lecture, genres FR, `lang`/contraste, recherche tolérante, cohérence visuelle, mot de passe provisoire, état de chargement.

### Plus tard

UX-25 à UX-30, et un vrai test avec lecteur d'écran et sur TV.

---

## 8. Kit de lancement coloc

### Message d'accueil (à envoyer avec l'accès)

> Salut ! Je vous ouvre **Backstage**, notre Netflix maison 🍿
> 👉 Adresse : `<URL de prod>`, ton e-mail : `<email>`, mot de passe provisoire : `<transmis à part>`
> À la première connexion, tu choisis ton propre mot de passe. Tes favoris, notes et ta liste « à voir » ne sont visibles que par toi.
> Un souci ? Écris dans `<canal>` avec une capture d'écran.

### Mini-guide en 5 étapes

1. **Connecte-toi** et choisis ton mot de passe.
2. **Accueil** : « Continuer à regarder » reprend là où tu t'es arrêté.
3. **Rechercher** un film : s'il est « Dans ma bibliothèque », clique sur **Lire**. Sinon, **Louer** pour qu'il soit ajouté (quelques minutes à quelques heures).
4. **Tu ne sais pas quoi regarder ?** « Choisir un film » : 5 questions, quelques idées (5 par jour).
5. **Note et ♡** les films : les suggestions s'améliorent.

### FAQ (les 5 questions qu'on va te poser)

1. *« J'ai cliqué sur Lire et rien ne se passe. »* → Autorise les fenêtres surgissantes pour Backstage ; si le lecteur ne s'ouvre pas, le serveur est peut-être éteint : préviens l'admin.
2. *« Le film que je veux n'est pas là. »* → Recherche-le puis « Louer ce film ». Il apparaît dans « Mes locations » puis devient lisible. Location : 21 jours (7 jours après la 1ʳᵉ lecture), 5 à la fois.
3. *« Et les séries ? »* → (selon UX-09) demande à l'admin / bouton « Demander une série ».
4. *« J'ai oublié mon mot de passe. »* → « Mot de passe oublié ? » ; si l'e-mail n'arrive pas, l'admin peut te donner un nouveau mot de passe provisoire.
5. *« Les autres voient ce que je regarde ? »* → Non : tes notes, favoris et ta liste sont personnels. Le catalogue (les films présents) est commun.

### Signaler un bug

Un canal unique (groupe WhatsApp ou Discord « Backstage-bugs »), avec un modèle : *ce que je voulais faire / ce que j'ai fait / ce qui s'est passé / capture d'écran / téléphone ou ordinateur*.

---

## 9. Vérification rapide de 10 minutes avant chaque mise en production

À faire sur un **téléphone réel** et sur un ordinateur, avec un compte coloc de test :

1. [ ] Connexion avec un mauvais mot de passe → « Identifiants invalides » ; puis bonne connexion.
2. [ ] **Mobile** : toucher Accueil, Films, Séries, la cloche et le compte → chacun ouvre la bonne chose.
3. [ ] Rechercher un film de la bibliothèque → la fiche s'ouvre ; la durée affichée est réelle.
4. [ ] **Lire** → le lecteur Jellyfin démarre en moins de 10 s ; revenir dans Backstage.
5. [ ] Geste ou bouton **retour** sur la fiche → la fiche se ferme, on reste dans l'app.
6. [ ] ♡ et note 4/5 → visibles après rechargement ; invisibles depuis un 2ᵉ compte coloc.
7. [ ] « Choisir un film » → suggestions en moins de 5 s, titres en français, au moins une explication cohérente avec les réponses.
8. [ ] Rechercher un film absent → « Louer ce film » → il apparaît dans « Mes locations ».
9. [ ] Mot de passe oublié sur le compte de test → **l'e-mail arrive** et le lien fonctionne.
10. [ ] Se déconnecter, puis vérifier que la console ne contient pas d'erreur rouge inattendue (hors 401 initial).
