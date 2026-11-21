"""Questions and answer validation for the guided film selection."""

MOOD_GENRES = {
    "light": ("Comédie", "Animation", "Familial"),
    "intense": ("Thriller", "Action", "Horreur", "Guerre"),
    "moving": ("Drame", "Romance", "Musique"),
    "thoughtful": ("Science-Fiction", "Mystère", "Documentaire", "Histoire"),
}

_QUESTIONS = (
    ("mood", "De quelle ambiance as-tu envie ?", (
        ("light", "Léger ou drôle"), ("intense", "Prenant ou tendu"),
        ("moving", "Émouvant"), ("thoughtful", "Qui fait réfléchir"),
    )),
    ("genres", "Quel univers te tente ?", tuple(
        (genre, genre) for genre in (
            "Thriller", "Science-Fiction", "Comédie", "Drame", "Action", "Aventure",
            "Fantastique", "Horreur", "Romance", "Animation", "Documentaire", "Histoire",
        )
    )),
    ("runtime_max", "Combien de temps as-tu ?", (("90", "1 h 30 maximum"), ("120", "2 h maximum"))),
    ("discovery", "Tu as envie d’une valeur sûre ou d’une découverte ?", (
        ("familiar", "Dans mes goûts"), ("surprise", "Quelque chose qui change"), ("balanced", "Les deux"),
    )),
)

_REFINEMENTS = {
    "Thriller": ("Quel type de thriller te tente ?", (
        ("Mystère", "Une enquête"), ("Drame", "Du suspense psychologique"), ("Action", "De l’action"),
    )),
    "Science-Fiction": ("Quelle science-fiction te tente ?", (
        ("Aventure", "Une aventure"), ("Mystère", "Une énigme"), ("Drame", "Une histoire humaine"),
    )),
    "Comédie": ("Quelle touche en plus pour ta comédie ?", (
        ("Romance", "De la romance"), ("Aventure", "De l’aventure"), ("Drame", "De l’émotion"),
    )),
    "Drame": ("Quel type de drame te tente ?", (
        ("Histoire", "Une histoire d’époque"), ("Romance", "Une histoire d’amour"), ("Crime", "Une affaire criminelle"),
    )),
}


def guided_question(preferences: dict, index: int) -> dict | None:
    genres = preferences.get("genres", [])
    refinement = next((_REFINEMENTS[genre] for genre in genres if genre in _REFINEMENTS), None)
    if index < len(_QUESTIONS):
        axis, prompt, choices = _QUESTIONS[index]
    elif index == len(_QUESTIONS) and refinement:
        axis, (prompt, choices) = "refinement", refinement
    else:
        return None
    return {
        "axis": axis, "type": "choice", "prompt": prompt,
        "options": [{"answer": value, "label": label} for value, label in choices],
        "max_choices": 2 if axis == "genres" else 1, "question_index": index,
        "max_questions": 5 if refinement or index < 2 else 4,
    }


def apply_guided_answer(preferences: dict, question: dict, choices: list[str]) -> dict:
    allowed = {option["answer"] for option in question["options"]}
    if len(choices) > question["max_choices"] or len(set(choices)) != len(choices) or not allowed.issuperset(choices):
        raise ValueError("Choix de réponse invalide")
    axis = question["axis"]
    updated = dict(preferences)
    if choices:
        updated[axis] = int(choices[0]) if axis == "runtime_max" else choices if axis == "genres" else choices[0]
    updated["answers"] = [*preferences.get("answers", []), {"axis": axis, "choices": choices}]
    return updated
