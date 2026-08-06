# Design — Recommandation personnalisée hybride

Date : 2026-08-06
Statut : proposé pour validation

## Objectif

Proposer immédiatement le meilleur film possible pour l’utilisateur courant, apprendre ses goûts au fil des interactions, conserver une expérience moderne et limiter les appels Gemini.

Une session de recommandation est limitée à deux appels Gemini maximum pour un utilisateur normal. Les administrateurs sont illimités. Le moteur local doit rester fonctionnel sans Gemini.

## Architecture retenue

SQLite reste une base commune, avec isolation logique par `backstage_user_id`. Un fichier SQLite par utilisateur compliquerait les migrations, les sauvegardes et l’administration sans améliorer la personnalisation.

Le flux est le suivant :

1. Le moteur local construit un profil résumé depuis les états personnels, les notes, le visionnage, les événements et les réponses précédentes.
2. Il sélectionne localement 20 à 30 candidats TMDB, en excluant les films vus, les exclusions définitives et les films déjà montrés dans la session.
3. Gemini, appel 1, réduit la liste à 6 à 8 candidats et propose les axes de questions. Il ne peut utiliser que les IDs fournis.
4. Les questions sont posées localement, avec un maximum de 5 questions, en choisissant la question qui apporte le plus d’information.
5. Les réponses enrichissent le profil temporaire de la session.
6. Gemini, appel 2, choisit le film final parmi les candidats autorisés et renvoie uniquement un ID TMDB, une confiance et une justification courte.
7. En cas d’erreur ou de quota atteint, le moteur local fournit un résultat de secours.

Gemini reçoit un profil résumé et des métadonnées TMDB compactes, jamais l’historique brut complet. Sa sortie est JSON validée et limitée en tokens.

## Mémoire et signaux

Les événements restent la source de vérité. Le profil calculé peut être mis en cache et recalculé après une nouvelle note ou une nouvelle session.

Les réactions sont distinctes : `shown`, `picked`, `skipped`, `not_now`, `less_like_this`, `hard_reject`, `already_seen`, `session_completed`. Une réaction temporaire expire ; une exclusion définitive est la seule qui bloque durablement un film.

Les signaux positifs provenant d’une note ou d’un film terminé sont plus forts qu’un simple clic. Les signaux négatifs diminuent avec le temps. Les préférences de la session courante ont priorité sur le profil permanent.

Le classement local combine goût, préférence de session, nouveauté, Watchlist/Favoris et diversité. La disponibilité serveur reste un bonus faible, jamais une exclusion principale.

## Quota et suivi des coûts

Le quota est vérifié côté API, au fuseau `Europe/Paris` : deux sessions commencées par jour pour les utilisateurs normaux, aucune limite pour les administrateurs. Une session ne consomme le quota qu’au lancement effectif du parcours ; une erreur Gemini est remboursable.

Une table `ai_usage` conserve utilisateur, session, modèle, tokens d’entrée, tokens de sortie, coût estimé, résultat choisi et date. L’interface affiche le nombre de sessions restantes.

## Critères de réussite

- aucun film déjà montré n’est répété dans une même session ;
- les refus temporaires ne suppriment pas définitivement un film ;
- un utilisateur normal ne peut pas dépasser deux sessions par jour ;
- un administrateur n’est pas limité ;
- la recommandation fonctionne sans Gemini ;
- les IDs retournés par Gemini sont toujours validés contre les candidats TMDB ;
- les tests couvrent le profil, les refus, la diversité, le quota, le fallback et le suivi des tokens.
