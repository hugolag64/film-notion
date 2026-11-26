# Bibliothèque nettoyée — design court

Date : 2026-11-26 · Statut : approuvé

## Intention

La bibliothèque Films est partagée entre colocs. Aujourd'hui elle mélange les films présents sur le serveur et les films seulement demandés, avec des badges de support (Serveur / Physique / Streaming / Cinéma) peu utiles. Pour l'utilisateur, la bibliothèque = « ce qui est sur le serveur ou demandé au serveur » ; il veut voir d'un coup d'œil ce qui est prêt, ce qui arrive (souvent parce que le film est au cinéma), et retrouver vite ses propres locations.

Premier de cinq projets (suivants : journal « Vu » + listes partagées, cinéma + agenda, social, quotidien).

## Objectifs

- Grille principale = films présents sur le serveur uniquement.
- Rangée « En route » au-dessus de la grille, visible par tous, pour les films demandés pas encore disponibles.
- Un seul badge visible et coloré par film, qui dit l'essentiel.
- Filtre « Mes locations » pour qu'un coloc retrouve ses films loués.

## Non-objectifs

- Vraie programmation en salle (projet 3).
- Journal « Vu », listes (projet 2).
- Changement du modèle de données (seul `/library/available` est élargi).

## Approche retenue

Une seule approche sensée : **l'essentiel côté interface, plus un petit élargissement d'un endpoint existant**. `rentalsByMedia` (locations de l'utilisateur courant) est déjà chargé pour tous. En revanche `availabilityByMedia` (état par film) ne l'est que pour l'admin (`/media-server/activity` est réservé à l'admin) ; les colocs ne reçoivent que `/library/available` → liste des ids prêts sur Jellyfin. On élargit donc `/library/available` pour renvoyer aussi, pour tous, l'état et le pourcentage de chaque film suivi (lecture seule, sans chemins ni erreurs détaillées). Écartés : ouvrir `/media-server/activity` aux colocs (expose des détails d'admin) ; un état « au cinéma » calculé côté serveur via TMDB (relève du projet 3).

« Sur le serveur » = prêt sur Jellyfin (`jellyfin_id`), le même critère que « ▶ Disponible maintenant ». Un film `available` / `imported` côté Radarr mais pas encore vu par Jellyfin reste « En route » avec le badge « Bientôt prêt » (mon choix).

## Design

**Répartition** (film de la vue Films) :
- Prêt sur Jellyfin → grille principale.
- Suivi par le serveur mais pas prêt (`requested`, `searching`, `downloading`, `error`, ou `available`/`imported` sans Jellyfin) → rangée « En route ».
- Aucun état de disponibilité (ni sur le serveur ni demandé, ex. ancien « Physique ») → reste dans la grille, sans badge, en attendant le journal « Vu ».

**Badges de la grille** : uniquement liés à la location de l'utilisateur courant — « Ta location · J-x » (location active, via `rentalExpiryLabel`) ou « Gardé » (`kept` / `keep_requested`). Pas de badge sinon. Les badges de support Serveur / Physique / Streaming / Cinéma (vers `BackstagePrototype.jsx:1779-1794`) sont supprimés de la carte.

**Badges « En route »** (un seul, coloré) :
- `requested` avec `release_date` dans le futur → « Sort le JJ/MM ».
- `requested` avec `release_date` il y a moins de 4 mois → « Au cinéma ».
- `requested` sinon → « Demandé ».
- `searching` → « Recherche » ; `downloading` → « Téléchargement NN % » ; `error` → « Erreur ».

**Rangée « En route »** : défilement horizontal, cartes plus petites, masquée si vide. Respecte la recherche texte et les filtres de genre / tri déjà présents.

**Filtre « Mes locations »** : pastille à côté de « ▶ Disponible maintenant » ; ne garde (grille et En route) que les films ayant une location de l'utilisateur dans un statut non terminé (pas `expired` / `cancelled`). Cumulable avec les autres filtres.

## Laissé au builder

- Couleurs exactes des badges (cohérentes avec la palette existante, `#635bff`, rose pour erreur).
- Extraction éventuelle de la logique de répartition / libellés dans un module testable (ex. `library.js`) — recommandé.
- Le seuil « 4 mois » est un choix de ma part, à mettre en constante.

## À part

« Dans la ligne de mire » apparaît en double sur la capture : probable doublon en base, à vérifier séparément.
