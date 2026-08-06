# Mode « Choisir un film »

Le moteur utilise SQLite et isole les signaux par `backstage_user_id`.

- Utilisateur standard : 2 sessions par jour, avec remise a zero au changement de jour dans `Europe/Paris`.
- Administrateur : sessions illimitees.
- Gemini est optionnel : sans cle, le classement local reste fonctionnel.
- Une session utilise au maximum deux appels Gemini et cinq questions.
- Le premier appel Gemini choisit un parcours d'axes (`movie_compare`, `mood`, `genre`, `era`).
- Les questions et leurs options sont generees localement ; les reponses sont envoyees ensemble au second appel Gemini.
- Les identifiants de films sont toujours valides contre les candidats TMDB fournis par Backstage.
- Une erreur, une reponse invalide ou un quota Gemini revient au resultat local.

Variables :

```dotenv
RECOMMENDATION_DAILY_LIMIT=2
RECOMMENDATION_TIMEZONE=Europe/Paris
RECOMMENDATION_RECENT_DAYS=30
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_MAX_OUTPUT_TOKENS=256
RADARR_DEFAULT_QUALITY_PROFILE_NAME=1080 FR - max 10go
RADARR_DEFAULT_ROOT_FOLDER=
```

SQLite conserve les evenements, les preferences par utilisateur et les compteurs de tokens/couts. Les sauvegardes restent volontairement reportees jusqu'a la reception du disque dedie.

Les films deja proposes sont memorises par utilisateur pendant `RECOMMENDATION_RECENT_DAYS` jours. Cette memoire evite de reproposer les memes choix entre deux sessions, y compris pour les questions suivantes d'une meme session. Si le catalogue restant est trop petit, le moteur relache uniquement ce delai pour eviter un ecran vide ; les films notes, vus ou explicitement rejetes restent exclus.

Le premier appel ne choisit jamais directement un film : il choisit seulement la maniere d'affiner la recherche. Le second appel recoit le profil local, les reponses de la session et uniquement les candidats TMDB eligibles. Sans Gemini, un parcours local alterne automatiquement les axes recents.

Depuis le resultat final, `Ajouter et telecharger` cree ou reutilise le film dans la bibliotheque, puis demande son acquisition avec le profil qualite administrateur. Une erreur Radarr/Seerr laisse le film dans la bibliotheque et permet une nouvelle tentative.
