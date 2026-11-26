from datetime import datetime

import pytest

from backend.core.party_logic import (
    QUESTIONS, average_profiles, combine_answers, is_expired, tally, validate_answers,
)
from backend.core.recommendations import TasteProfile


def test_questions_follow_the_spec():
    assert [q["key"] for q in QUESTIONS["coloc"]] == ["mood", "runtime", "era"]
    assert [q["key"] for q in QUESTIONS["cinema"]] == ["mood", "runtime"]
    runtime = QUESTIONS["coloc"][1]
    assert [(o["value"], o["label"]) for o in runtime["options"]] == [
        ("105", "1 h 45"), ("135", "2 h 15"), ("any", "Peu importe"),
    ]


def test_validate_answers_rejects_unknown_value():
    with pytest.raises(ValueError):
        validate_answers("coloc", {"mood": "sad", "runtime": "any", "era": "any"})
    with pytest.raises(ValueError):
        validate_answers("coloc", {"mood": "light", "runtime": "any"})


def test_validate_answers_cinema_ignores_era():
    assert validate_answers("cinema", {"mood": "light", "runtime": "105"}) == {"mood": "light", "runtime": "105"}
    assert validate_answers("cinema", {"mood": "light", "runtime": "105", "era": "recent"}) == {
        "mood": "light", "runtime": "105",
    }


def test_combine_takes_shortest_runtime():
    answers = [{"runtime": "135"}, {"runtime": "105"}, {"runtime": "any"}]
    assert combine_answers(answers)["runtime_max"] == 105
    assert combine_answers([{"runtime": "any"}, {"runtime": "any"}])["runtime_max"] is None


def test_combine_mood_majority_ignores_any():
    moods = [{"mood": m} for m in ("light", "light", "intense", "any")]
    assert combine_answers(moods)["mood"] == "light"
    assert combine_answers([{"mood": "light"}, {"mood": "intense"}])["mood"] == "any"
    assert combine_answers([])== {"mood": "any", "runtime_max": None, "era": "any"}


def test_average_profiles_fills_missing_keys_with_zero():
    merged = average_profiles([
        TasteProfile(genre_affinity={"Comédie": 1.0}, confidence=0.4),
        TasteProfile(genre_affinity={"Drame": 0.5}, confidence=0.2),
    ])
    assert merged.genre_affinity == {"Comédie": 0.5, "Drame": 0.25}
    assert merged.confidence == pytest.approx(0.3)
    assert average_profiles([]) == TasteProfile()


def _votes(rank, up, down):
    return [{"user_id": f"u{rank}+{i}", "rank": rank, "value": 1} for i in range(up)] + [
        {"user_id": f"u{rank}-{i}", "rank": rank, "value": -1} for i in range(down)
    ]


PROPOSALS = [{"rank": 1}, {"rank": 2}, {"rank": 3}]


def test_tally_majority_wins_without_veto():
    result = tally(PROPOSALS, _votes(1, 2, 1) + _votes(2, 1, 0))
    assert result["winner_rank"] == 1
    assert result["scores"][1] == {"up": 2, "down": 1}
    assert result["scores"][3] == {"up": 0, "down": 0}


def test_tally_tie_goes_to_best_rank():
    result = tally(PROPOSALS, _votes(1, 0, 1) + _votes(2, 1, 0) + _votes(3, 1, 0))
    assert result["winner_rank"] == 2
    assert tally([], [])["winner_rank"] is None


def test_is_expired_after_three_hours():
    party = {"status": "joining", "created_at": datetime(2026, 11, 26, 18, 0)}
    assert is_expired(party, datetime(2026, 11, 26, 20, 59)) is False
    assert is_expired(party, datetime(2026, 11, 26, 21, 0)) is True
    assert is_expired({**party, "status": "done"}, datetime(2026, 11, 27)) is False
