from datetime import datetime

from backend.core.cinema_reminders import Reminder, compute_reminders

NOW = datetime(2026, 11, 26, 9, 0)


def _at(day, hour=20, month=11):
    return datetime(2026, month, day, hour, 0)


def test_tracked_film_arrives_once():
    showtimes = {1: [_at(26), _at(27)]}

    first = compute_reminders(showtimes, {1}, set(), NOW, first_run=False)
    again = compute_reminders(showtimes, {1}, {(1, "arrivee")}, NOW, first_run=False)

    assert first == [Reminder(1, "arrivee", _at(26), _at(27), post=True)]
    assert again == []


def test_untracked_film_never_reminds():
    showtimes = {1: [_at(26)], 2: [_at(30)]}

    assert compute_reminders(showtimes, set(), set(), NOW, first_run=False) == []


def test_first_run_records_arrival_silently_and_skips_end():
    showtimes = {1: [_at(26), _at(27)], 2: [_at(28), _at(1, month=12)]}

    reminders = compute_reminders(showtimes, {1}, set(), NOW, first_run=True)

    assert reminders == [Reminder(1, "arrivee", _at(26), _at(27), post=False)]


def test_end_when_programme_runs_two_days_past_last_showing():
    sent = {(1, "arrivee")}
    long_run = {1: [_at(26), _at(27, 14), _at(27, 21)], 2: [_at(29)]}
    short_run = {1: [_at(26), _at(27)], 2: [_at(28)]}

    assert compute_reminders(long_run, {1}, sent, NOW, first_run=False) == [
        Reminder(1, "fin", _at(26), _at(27, 21), post=True)
    ]
    assert compute_reminders(short_run, {1}, sent, NOW, first_run=False) == []
    assert compute_reminders(long_run, {1}, sent | {(1, "fin")}, NOW, first_run=False) == []


def test_far_preview_is_ignored():
    preview_only = {1: [_at(16, month=12)]}
    assert compute_reminders(preview_only, {1}, set(), NOW, first_run=False) == []

    # La séance lointaine du film 2 n'allonge pas la fenêtre : pas de « fin » pour le film 1.
    with_preview = {1: [_at(26), _at(27)], 2: [_at(28), _at(16, month=12)]}
    assert compute_reminders(with_preview, {1}, {(1, "arrivee")}, NOW, first_run=False) == []


def test_past_showtimes_do_not_count():
    showtimes = {1: [_at(25)], 2: [_at(30)]}

    assert compute_reminders(showtimes, {1}, set(), NOW, first_run=False) == []


def test_no_end_in_the_same_run_as_arrival():
    showtimes = {1: [_at(26)], 2: [_at(30)]}

    reminders = compute_reminders(showtimes, {1}, set(), NOW, first_run=False)

    assert [r.kind for r in reminders] == ["arrivee"]
