# Prompt — Audit UI/UX complet avant déploiement en colocation

> À coller tel quel dans une nouvelle session Claude Code ouverte à la racine du dépôt Backstage.

---

Tu es un auditeur UX/UI senior doublé d'un testeur QA. Ta mission : réaliser un **audit complet de l'interface et de l'expérience utilisateur de Backstage** avant son déploiement auprès de mes colocataires. Tu ne corriges rien pendant l'audit : tu observes, tu testes, tu documentes, tu priorises.

## 1. Contexte

- **Produit** : Backstage, un « Netflix maison » partagé. Catalogue films/séries commun, états personnels (favoris, watchlist, historique, notes), recommandations guidées, demandes via Jellyseerr/Radarr/Sonarr, lecture et reprise dans Jellyfin, notifications, locations/quotas, administration.
- **Stack** : backend FastAPI + SQLite (`main.py`, `backend/`), frontend React 19 + Vite + Tailwind (`proto-ui/src/`). Composants clés : `AuthGate.jsx`, `PasswordResetPage.jsx`, `AccountPanel.jsx`, `BackstagePrototype.jsx`, `components/DashboardHome.jsx`, `FilmDetailView.jsx`, `RecommendationFlow.jsx`, `NotificationBell.jsx`, `AdminCenter.jsx`, `UserManagement.jsx`.
- **Audits précédents** : `AUDIT_BACKSTAGE_COMPLET_2026-08-07.md`, `AUDIT_BACKSTAGE_2026-08.md`, `AUDIT_2_RECOMMANDATION.md`. Lis-les d'abord et vérifie pour chaque point UX signalé s'il est **corrigé, partiellement corrigé ou toujours présent**.
- **Public cible** : 3 à 5 colocataires, niveau technique hétérogène (certains n'ont jamais utilisé Jellyfin), usage surtout sur **téléphone** et **TV/ordinateur portable** le soir, souvent à plusieurs devant le même écran. Ils n'ont **aucune formation** : l'app doit être compréhensible seule.
- **Moi** : administrateur et seul développeur. Je dois pouvoir gérer les comptes, les demandes et les incidents sans friction.

## 2. Mise en place

1. Lance l'app en local (backend `python main.py` sur le port 8090, frontend `cd proto-ui && npm run dev`) et ouvre-la dans le navigateur intégré.
2. Crée ou utilise **uniquement des comptes de test** (un admin, deux utilisateurs standards dont un « tout neuf » sans historique). Jamais mes vrais identifiants ni ceux d'un service externe. Note les identifiants de test dans un fichier de seed/config d'exemple, pas dans le rapport.
3. Si une intégration (Jellyfin, Seerr, TMDB…) n'est pas joignable en local, **teste quand même l'état d'erreur** qu'elle produit dans l'UI : c'est exactement ce que verra un colocataire le jour où le serveur tombe.
4. Teste sur trois tailles d'écran au minimum : **mobile 375×812**, **tablette 768×1024**, **desktop 1440×900**, plus une vérification « TV » (1920×1080, lecture à 3 m : taille des textes, cibles, navigation clavier).

## 3. Parcours à dérouler de bout en bout

Pour chaque parcours, joue le rôle d'un colocataire qui découvre l'app. Chronomètre, compte les clics, note chaque hésitation.

| # | Parcours | Persona | Question clé |
|---|----------|---------|--------------|
| P1 | Recevoir son accès → première connexion → choix/création du profil | Nouveau coloc | Comprend-il en < 1 min ce qu'est l'app et quoi faire ensuite ? |
| P2 | Mot de passe oublié → réinitialisation → reconnexion | Coloc distrait | Le flux aboutit-il sans aide ? Messages clairs ? |
| P3 | Accueil → trouver un film précis par recherche | Coloc pressé | Résultat pertinent en ≤ 3 actions ? |
| P4 | « On regarde quoi ce soir ? » → recommandations guidées → choisir | Groupe indécis | Le flux aide-t-il vraiment à décider ? Quota compréhensible ? |
| P5 | Fiche média → lancer la lecture Jellyfin → revenir | Coloc lambda | Le lancement est-il fiable et le retour évident ? |
| P6 | Reprendre une série/un film en cours (épisode suivant) | Coloc régulier | La reprise est-elle visible dès l'accueil ? |
| P7 | Film absent → faire une demande → suivre son statut → notification de disponibilité | Coloc cinéphile | Sait-il où en est sa demande à chaque étape ? |
| P8 | Gérer favoris, watchlist, notes, historique | Coloc organisé | Les actions sont-elles réversibles et confirmées visuellement ? |
| P9 | Location / quota atteint | Coloc gourmand | Comprend-il pourquoi il est bloqué et quand ça se débloque ? |
| P10 | Admin : inviter un coloc, gérer comptes, traiter les demandes, voir la supervision | Moi | Puis-je tout faire sans ouvrir la base ou les logs ? |
| P11 | Déconnexion, session expirée, deux colocs sur le même appareil | Tous | Pas de fuite de données d'un profil à l'autre ? |

## 4. Grille d'évaluation

Évalue chaque écran et parcours selon ces axes. Cite toujours l'écran, l'action et le fichier/composant concerné.

1. **Compréhension & onboarding** : proposition de valeur claire, vocabulaire non technique (pas de « TMDB », « Seerr », « Radarr » exposés sans explication), état vide accueillant pour un nouveau compte.
2. **Heuristiques de Nielsen** : visibilité de l'état du système, correspondance avec le monde réel, contrôle et liberté (annuler, retour), cohérence, prévention des erreurs, reconnaissance plutôt que rappel, flexibilité, design minimaliste, messages d'erreur utiles, aide.
3. **Architecture de l'information & navigation** : hiérarchie, libellés, profondeur, retour arrière (bouton navigateur inclus), deep links partageables, persistance des filtres/tris/pagination.
4. **États de l'interface** : chargement (skeletons vs spinners), vide, erreur, partiel, hors-ligne, succès. Aucune action ne doit rester sans retour visuel.
5. **Design visuel & cohérence** : système de tokens (couleurs, espacements, typo), cohérence des boutons/cartes/modales, qualité des affiches et backdrops (images manquantes, recadrage), mode sombre, densité.
6. **Responsive & multi-appareil** : débordements horizontaux, cibles tactiles ≥ 44 px, modales utilisables sur mobile, clavier virtuel qui masque les champs, rendu TV.
7. **Accessibilité (WCAG 2.2 AA)** : contraste, focus visible, navigation 100 % clavier (Tab, Échap ferme les modales, focus piégé puis restitué), libellés ARIA, alternatives textuelles, `prefers-reduced-motion`, zoom 200 %.
8. **Performance perçue** : temps jusqu'au premier contenu utile, lenteurs ressenties > 1 s, poids du bundle, images non optimisées, recherches non « debouncées », re-rendus visibles. Relève les mesures réelles (onglet réseau, console).
9. **Fiabilité & erreurs** : erreurs console, requêtes en échec, double-clic qui duplique une action, comportement quand Jellyfin/Seerr/TMDB est indisponible, rate limiting d'auth compréhensible.
10. **Multi-utilisateur & confiance** : chaque coloc ne voit et ne modifie que ses données personnelles, les actions partagées (demandes, suppression, édition du catalogue) sont clairement attribuées et protégées, les actions destructrices demandent confirmation.
11. **Micro-copie** : ton cohérent en français, accents et typographie (espaces insécables, guillemets), pluriels, messages d'erreur actionnables.

## 5. Règles

- **Aucune modification de code** pendant l'audit. Si un bug bloque un parcours, documente-le et contourne-le si possible.
- **Preuves obligatoires** : pour chaque problème, une capture ou un extrait (console, réseau, DOM) et des étapes de reproduction.
- **Pas de supposition** : distingue clairement « constaté en testant » de « déduit en lisant le code ».
- Ne mets aucun identifiant, clé ou donnée personnelle dans le rapport.

## 6. Sévérité

- **P0 — Bloquant** : empêche un parcours essentiel (P1, P3, P5, P6, P11) ou expose des données d'un autre coloc. Interdit le déploiement.
- **P1 — Majeur** : parcours réalisable mais confus, frustrant ou nécessitant de m'appeler. À corriger avant déploiement.
- **P2 — Moyen** : gêne réelle mais contournable. Peut suivre dans la première semaine.
- **P3 — Mineur / polish** : cosmétique, cohérence, confort.

## 7. Livrable attendu

Rédige `docs/audits/AUDIT_UI_UX_PRE_DEPLOIEMENT_<date>.md` avec :

1. **Verdict go / no-go** pour le déploiement en colocation, justifié en 5 lignes max.
2. **Résumé exécutif** : 5 forces, 5 problèmes les plus graves, score /10 par axe de la grille (§4).
3. **Résultats par parcours** (P1 → P11) : réussi / réussi avec difficulté / échec, temps, nombre de clics, points de friction.
4. **Tableau des problèmes** : ID, sévérité, axe, écran, description, étapes de reproduction, preuve, fichier/composant probable, recommandation concrète, effort estimé (S/M/L).
5. **Suivi des audits précédents** : chaque point UX antérieur → corrigé / partiel / ouvert.
6. **Plan d'action priorisé** :
   - *Avant déploiement* (P0 + P1),
   - *Semaine 1* (P2 rapides),
   - *Plus tard* (P3, améliorations).
7. **Kit de lancement coloc** : ce qui manque pour que mes colocs s'en sortent seuls (message d'accueil, mini-guide en 5 étapes, FAQ des 5 questions qu'ils vont me poser, canal pour signaler un bug).
8. **Checklist de smoke test** de 10 minutes que je pourrai rejouer juste avant chaque mise en production.

Commence par lire les audits précédents et cartographier les écrans, puis présente-moi en 10 lignes ton plan de test avant de lancer les parcours.
