from backend.core import history as history_mod


def _use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(history_mod, "HISTORY_FILE", str(tmp_path / "history.jsonl"))


def test_record_and_read(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    history_mod.record("p1", "Dune", [{"field": "Réalisateur", "old": "—", "new": "DV"}], source="auto")
    history_mod.record("p2", "Arrival", [{"field": "Synopsis", "old": "—", "new": "..."}], source="manual")

    entries = history_mod.read_recent()
    assert len(entries) == 2
    # plus récent en premier
    assert entries[0]["title"] == "Arrival"
    assert entries[0]["source"] == "manual"
    assert entries[0]["fields"] == ["Synopsis"]


def test_record_ignores_empty_changes(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    history_mod.record("p1", "Dune", [], source="auto")
    assert history_mod.read_recent() == []


def test_read_recent_no_file(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert history_mod.read_recent() == []
