# Nettoyage du stockage média — Design

## Objectif

Permettre à un administrateur d’identifier et de supprimer des films volumineux du disque depuis Backstage, tout en conservant leur fiche Backstage et en retirant leur entrée Radarr pour qu’ils puissent être redemandés plus tard.

## Règles métier

- Seuls les administrateurs peuvent consulter et exécuter le nettoyage.
- La suppression est toujours manuelle et confirmée explicitement.
- Un film protégé ne peut pas être supprimé.
- Sont protégés par défaut : favoris, locations actives, ajoutés depuis moins de 14 jours, vus depuis moins de 30 jours et films marqués manuellement comme à conserver.
- La suppression retire le film de Radarr avec ses fichiers, mais conserve la fiche Backstage.
- Après suppression, Jellyfin et Backstage sont resynchronisés ; le film redevient demandable.
- Chaque suppression est journalisée avec l’administrateur, le titre, la taille et la date.

## Interface

Ajouter dans le centre d’administration une section « Libérer de l’espace » avec une table triable par taille décroissante. Chaque ligne affiche le statut de protection, la raison de protection ou de suggestion, la taille, la dernière lecture et la date d’ajout. Une confirmation récapitule le titre et l’espace libéré avant exécution.

## Architecture

Le backend interroge Radarr pour les films possédant un fichier, enrichit les entrées avec les protections Backstage et expose une route admin de candidats ainsi qu’une route admin de suppression. Le client Radarr fournit une opération dédiée de suppression avec `deleteFiles=true`. Le frontend ne manipule jamais de chemin de fichier directement.

## Sécurité et erreurs

- Toute route est protégée par `require_admin`.
- Une suppression échoue si Radarr ne possède pas l’entrée ciblée ou si le film est protégé.
- Les erreurs Radarr sont retournées sans exposer la clé API.
- Après une suppression réussie, l’état Backstage est invalidé et une synchronisation est lancée.
