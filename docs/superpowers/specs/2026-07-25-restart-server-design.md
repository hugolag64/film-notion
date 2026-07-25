# Relance locale du serveur

## Objectif

Fournir un script Windows `restart_server.bat` à la racine du projet pour arrêter le serveur occupant le port 8090 puis relancer Backstage localement.

## Comportement

Le script recherche les PID en écoute sur le port TCP 8090 avec `netstat`, les termine avec `taskkill /F`, puis démarre `main.py` via `.venv\\Scripts\\python.exe`. Il fixe `PORT=8090`, attend brièvement que le serveur démarre, puis ouvre `http://localhost:8090` dans le navigateur par défaut.

## Cas d'erreur

L'absence de processus sur le port ne doit pas interrompre le script. Si l'environnement virtuel est absent, le script affiche une erreur lisible et reste ouvert pour permettre le diagnostic.

## Vérification

Lancer le script lorsque le serveur est déjà actif, puis vérifier qu'un seul processus écoute sur 8090 et que l'URL locale répond.
