# Refonte du tableau de bord Backstage

## Objectif

Rendre l’accueil plus lisible et plus compact en supprimant la navigation redondante, en regroupant les actions utilisateur à droite et en affichant les reprises dans une rangée horizontale de six cartes maximum sur desktop.

## Design validé

- L’en-tête conserve le logo et le nom Backstage à gauche.
- La navigation principale devient `Accueil`, `Films`, `Séries`, sans bouton `Bibliothèque`.
- La recherche, l’ajout, l’administration, le mode sombre et le compte sont regroupés dans la zone utilitaire droite.
- Le mode sombre devient un bouton compact avec une icône, afin de ne pas concurrencer la navigation principale.
- `Continuer à regarder` devient une rangée horizontale compacte : six cartes visibles au maximum sur desktop, défilement horizontal si nécessaire, une ou deux cartes adaptées sur les petits écrans.
- `Pour vous` conserve son défilement horizontal et ses actions TMDB.
- Les sections activité et disponibilité restent sous les deux premières sections, sans modification de données.

## Contraintes

- Ne pas modifier les routes backend ni le modèle de données.
- Préserver les actions existantes : reprise, fiche média, ajout, administration, recherche et changement de collection.
- Préserver le mode sombre sur tous les éléments déplacés.
- Garder un parcours clavier accessible avec des boutons natifs et des libellés explicites.
