# Refonte graphique de Backstage — Design

Date : 2026-07-05

## Contexte et motivation

L'interface actuelle (`frontend/ui.py`, ~420 lignes monolithiques) a un look "SaaS générique" (fond gris clair, accent indigo, cards blanches) qui ne reflète pas le sujet de l'app (vidéothèque de films/séries). Deux problèmes concrets s'ajoutent au manque de personnalité :

- La navigation par onglets Quasar (`ui.tabs()` / `ui.tab_panels()`) est limitante pour faire évoluer chaque section indépendamment.
- La liste "à traiter" est un tableau texte brut sans aucune information visuelle (pas d'affiche, pas de repère rapide).

Le backend (`backend/core/*`) n'est pas concerné : cette refonte est 100% côté `frontend/`.

## Direction visuelle

- **Palette — Ivoire & Bordeaux** : fond ivoire chaleureux (`#faf6ef`), accent bordeaux profond (`#7a2331`), texte anthracite chaud (`#2b2420`), touche secondaire or/ambre (`#c9a35c`) pour badges et éléments d'accent (genres, ratings). Ambiance "salle de projection feutrée", intemporelle.
- **Typographie — serif éditorial + sans discret** : titres et éléments de marque en serif classique (Georgia / Times New Roman), texte courant et métadonnées en sans-serif neutre (Arial/Helvetica). Registre "magazine cinéma papier".
- **Mode sombre** : hors scope pour cette refonte, mais les couleurs sont posées en variables CSS (design tokens) dans `theme.py` pour permettre un futur toggle sans réécrire les composants.

## Architecture de code

Découpage du fichier monolithique `frontend/ui.py` en modules par responsabilité :

```
frontend/
  theme.py          → tokens (couleurs, typo, radius, ombres) + injection CSS (une fois, via ui.add_head_html)
  ui.py             → orchestrateur : top bar, sous-navigation, routing entre sections
  pages/
    dashboard.py    → section "À traiter" (bandeau résumé + grille de cards)
    wizard.py       → résolution d'ambiguïté (page plein écran)
    stats.py        → tableau de bord (donut / courbe / barres)
    history.py      → timeline chronologique
    ai.py           → reco IA (restyle léger, structure inchangée)
  components.py     → éléments partagés (rendu affiche/placeholder, badge, bouton pill)
```

Tokens exposés par `theme.py` (variables CSS) :

```css
--bg: #faf6ef;
--surface: #ffffff;
--border: #ece4d6;
--text: #2b2420;
--text-muted: #8a8578;
--accent: #7a2331;
--accent-gold: #c9a35c;
--font-display: Georgia, 'Times New Roman', serif;
--font-body: Arial, Helvetica, sans-serif;
--radius: 10px;
```

Aucun test existant ne référence `frontend/` (vérifié dans `tests/`) : ce découpage n'a pas d'impact sur la suite de tests en place.

## Navigation

Remplacement de `ui.tabs()` / `ui.tab_panels()` par une **top bar** :
- Logo "🎬 Backstage" (serif) à gauche.
- Liens de sous-navigation à droite (À traiter · Statistiques · Historique · Reco IA), section active soulignée en bordeaux.
- Chaque section est une vue gérée par l'état applicatif (le conteneur racine est vidé/repeuplé selon la section active), permettant à chaque page une mise en page libre au lieu d'être contrainte dans un tab-panel Quasar.

## Section "À traiter" (dashboard)

- **Bandeau résumé** sous la top bar : nombre de fiches en attente + horodatage de la dernière synchro à gauche ; CTA principal "Lancer l'enrichissement" (pill bordeaux) + bouton secondaire "Dry-run" (outline bordeaux) à droite.
- **Grille de cards** responsive (3-4 colonnes) sous le bandeau : chaque card affiche l'affiche TMDB (si `cover_url` disponible) ou un **placeholder élégant** (silhouette de pellicule/clap sur dégradé ivoire/or) si absente, le titre en serif, et l'année/type en badge bordeaux.
  - Pas d'appel TMDB anticipé pour peupler les affiches manquantes — le placeholder est la solution retenue, aucune donnée supplémentaire à aller chercher.
- Switch "Forcer le re-traitement" conservé, discret, sous le bandeau.
- État vide ("Tout est à jour") : icône + message centré, restylé aux nouveaux tokens.

## Wizard (résolution d'ambiguïté)

- Passe d'une **dialog modale** à une **page plein écran** dédiée.
- En-tête : titre de la fiche en cours + barre de recherche manuelle (titre + année), fonctionnellement inchangée.
- Corps : **galerie d'affiches** en grille (façon planche de recherche) — chaque candidat est une vignette cliquable (affiche, année, type film/série) ; la sélection est mise en évidence par une bordure bordeaux.
- **Panneau de détail** du candidat sélectionné sous la galerie : réalisateur, synopsis, note IMDb, tags suggérés, bouton "Confirmer ce titre".
- Bouton "Ignorer cette fiche" conservé en bas de page.
- La phase auto (progress bar + journal d'activité) et l'écran de fin restent des étapes de cette même page plein écran, restylées aux tokens (progress bar bordeaux, iconographie cohérente).

## Statistiques

Restructuration en véritable tableau de bord :
- Ligne de stat-tiles chiffrées (Total, Enrichis %, Notés, Sans réalisateur), restylées.
- **Donut chart** pour la répartition par support.
- **Courbe de progression** du taux d'enrichissement dans le temps, dérivée de `history.jsonl` déjà écrit sur disque (agrégation par jour) — aucune nouvelle collecte de donnée nécessaire.
- **Barres** pour le top genres (remplace la liste texte actuelle).
- Bloc "doublons potentiels" conservé tel quel en bas de page.

## Historique

Remplacement de la liste de cards par une **timeline verticale** :
- Fil chronologique vertical, un point coloré par entrée (couleur selon la source auto/manuel).
- Chaque point affiche titre, source, champs modifiés, horodatage relatif ("il y a 4 min", "hier à 21:14").

## Reco IA

Pas de restructuration : restyle léger uniquement (cards, bouton, typographie cohérents avec le reste de l'app), logique et structure inchangées.

## Hors scope

- Aucune modification du backend (`backend/core/*`).
- Aucun nouvel appel API (TMDB, Notion, Anthropic) au-delà de l'existant.
- Pas de mode sombre fonctionnel dans cette refonte (seulement les tokens qui le permettront plus tard).
- Pas de bibliothèque de composants extensive : seuls les éléments réellement dupliqués (rendu affiche/placeholder) sont extraits dans `components.py`.
