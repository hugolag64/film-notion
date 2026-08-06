from backend.core.store import MediaStore


def make_store(tmp_path):
    store = MediaStore(str(tmp_path / "backstage.db"))
    store.init_schema()
    return store


def test_recommendation_usage_and_daily_count_are_user_scoped(tmp_path):
    store = make_store(tmp_path)
    store.record_recommendation_usage_sync({
        "backstage_user_id": "hugo",
        "session_id": "s1",
        "model": "gemini-3.5-flash-lite",
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_estimate_usd": 0.0001,
        "created_at": "2026-08-06T10:00:00+00:00",
    })

    assert store.count_recommendation_sessions_sync(
        "hugo", "2026-08-06T00:00:00+00:00"
    ) == 0
    assert store.get_recommendation_usage_sync("s1")[0]["input_tokens"] == 100
