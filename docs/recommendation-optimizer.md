# Mode « Choisir un film »

Le moteur utilise SQLite et isole les signaux par `backstage_user_id`.

- Utilisateur standard : 2 sessions par jour, avec remise a zero au changement de jour dans `Europe/Paris`.
- Administrateur : sessions illimitees.
- Gemini est optionnel : sans cle, le classement local reste fonctionnel.
- Une session utilise au maximum deux appels Gemini et cinq questions.
- Les identifiants de films sont toujours valides contre les candidats TMDB fournis par Backstage.
- Une erreur, une reponse invalide ou un quota Gemini revient au resultat local.

Variables :

```dotenv
RECOMMENDATION_DAILY_LIMIT=2
RECOMMENDATION_TIMEZONE=Europe/Paris
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_MAX_OUTPUT_TOKENS=256
```

SQLite conserve les evenements, les preferences par utilisateur et les compteurs de tokens/couts. Les sauvegardes restent volontairement reportees jusqu'a la reception du disque dedie.
