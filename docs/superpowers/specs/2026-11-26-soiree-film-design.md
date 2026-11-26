# Soirée film — design

Projet 4 de Backstage (« Social »), réduit à un seul besoin.

## Intention

Un soir, plusieurs colocs veulent regarder un film ensemble et personne ne sait quoi. Backstage les aide à trancher, **depuis le téléphone de chacun, dans le salon**, de deux façons :

- **Ciné ce soir** : sortir au Ciné Grand Sud, parmi les séances de ce soir ;
- **Coloc** : regarder un film à la coloc, présent sur le serveur ou non (s'il manque, on le demande).

La recommandation Gemini actuelle est individuelle. La soirée film est **collective** : elle combine les goûts et les réponses de tous les partants, puis le groupe vote.

## Buts

- Une soirée se lance, se joue et se termine entièrement dans le salon, sur téléphone.
- Les propositions tiennent compte de tous les partants, pas seulement de celui qui lance.
- Le choix final revient au groupe, par vote à la majorité.

## Non-buts

- Fil d'activité (« Thomas a loué Dune ») : retiré du projet 4.
- Recommander un film à un coloc : retiré du projet 4.
- Afficher les notes ou le journal des autres : les journaux restent privés (décision du projet 2).
- Les cinémas autres que le Grand Sud.

## Anti-buts (échec même si ça marche)

- La soirée révèle qui a vu ou noté quoi.
- Une personne peut bloquer seule le choix (pas de veto).
- Il faut quitter le salon pour participer (seule la fiche d'un film s'ouvre en surimpression).

## Approches considérées

- **A. Carte interactive dans le salon (choisie).** Le bot poste un message « soirée » avec des boutons ; la carte se met à jour chez tout le monde. Réutilise les messages du bot à `payload` du projet 3. Tout reste dans le chat. Coût : place limitée dans une bulle.
- B. Écran « Soirée » dédié, annoncé par un lien dans le salon. Plus de place, mais on quitte le chat et c'est un écran de plus.
- C. Commandes tapées (`@soirée`, `@vote 2`). Le plus simple à coder, pénible à plusieurs sur téléphone.

Choix de Hugo : **A**, avec la fiche du film qui s'ouvre au clic sur l'affiche.

## Déroulé (décidé avec Hugo)

1. **Lancer.** Quelqu'un lance une soirée depuis le salon et choisit « Coloc » ou « Ciné ce soir ». Le bot poste une carte de soirée.
2. **Rejoindre.** Chacun clique « Je suis partant » sur son téléphone et répond à 2 ou 3 questions rapides.
3. **Proposer.** Quand celui qui a lancé clique « On lance », Backstage propose **3 films**.
4. **Voter.** Chaque partant vote 👍 ou 👎 sur chaque film. **La majorité l'emporte, pas de veto.**
5. **Résultat.** La carte affiche le gagnant, avec l'action utile : réserver la séance (ciné), ouvrir la fiche (film sur le serveur) ou « Demander au serveur » (film absent).

Cliquer l'affiche d'une proposition ouvre sa fiche (résumé, durée, bande-annonce) par-dessus le salon.

## Décisions de l'assistant (à vérifier par Hugo)

- **Lancement** : un bouton 🍿 à côté du 🎬 dans le salon, et la commande `@soirée` dans le bot (avec son aide). Une seule soirée en cours à la fois ; en lancer une autre est refusé tant que la première n'est pas terminée ou expirée.
- **Questions aux partants** (boutons, une réponse chacune) :
  - humeur : « léger », « intense », « peu importe » ;
  - durée max : « 1 h 45 », « 2 h 15 », « peu importe ».
  En mode Ciné, pas d'autre question. En mode Coloc, aussi : « plutôt récent », « plutôt classique », « peu importe ».
- **Combinaison des goûts** : le profil de goûts de chaque partant (le même qu'aujourd'hui pour la recommandation individuelle) est moyenné. Les réponses se combinent ainsi : la durée la plus courte demandée l'emporte ; pour l'humeur et l'époque, la réponse majoritaire, « peu importe » ne comptant pas.
- **Films déjà vus** : un film vu par **au moins un** partant (journal ou état « vu » de la bibliothèque) est écarté, sans jamais dire par qui. Ce filtre ne s'applique qu'en mode Coloc ; au ciné on peut revoir un film.
- **Candidats Ciné** : les films du Grand Sud qui ont encore une séance aujourd'hui (heure de La Réunion) après l'heure actuelle, filtrés par la durée. S'il y en a moins de 3, on les propose tous ; s'il n'y en a aucun, le bot le dit et la soirée se termine.
- **Candidats Coloc** : films TMDB (même source que la recommandation actuelle) plus films de la bibliothèque, classés par le profil commun. Au moins une des 3 propositions vient du serveur quand un film du serveur fait partie des 15 premiers.
- **Choix des 3** : Gemini choisit 3 films parmi les 15 premiers du classement, avec une courte raison chacun (« parce que vous êtes d'humeur légère… »), sans citer de goût individuel. Sans Gemini (clé absente ou erreur), on prend les 3 premiers du classement local. Les soirées ne consomment pas le quota individuel de 5 recommandations par jour.
- **Vote** : score = 👍 − 👎 ; égalité → le film que Gemini a classé premier. Le vote se clôt quand tous les partants ont voté, ou quand celui qui a lancé clique « Clore le vote ». Un partant peut changer son vote tant que ce n'est pas clos.
- **Arrivée tardive** : après « On lance », un coloc peut encore rejoindre pour voter, mais ses goûts ne changent plus les propositions.
- **Expiration** : une soirée non terminée expire 3 h après son lancement ; la carte l'indique.
- **Rafraîchissement** : pendant qu'une carte de soirée active est visible, l'état est relu toutes les 3 s (le rythme actuel du salon ouvert).
- **« Demander au serveur »** : passe par la demande de film existante (Seerr), avec la même confirmation qu'ailleurs.

## Contraintes

- Même pile que le reste : FastAPI + SQLite `MediaStore`, React `proto-ui`.
- Réutiliser l'existant : messages du bot à `payload` (projet 3), profil de goûts et passerelle Gemini de la recommandation, séances du Grand Sud (projet 3), demande Seerr, fiche TMDB (`TMDBMoviePreview`).
- Tests sans réseau : TMDB, Gemini et le site du ciné sont simulés.
- Les journaux restent privés : aucune réponse d'API ne dit qui a vu un film.

## Laissé au constructeur

- Le schéma des tables (soirée, partants, réponses, propositions, votes) et les routes.
- La mise en page exacte de la carte dans la bulle du salon, dans le style actuel du chat.
- Le texte exact des messages du bot.
