from backend.config import Config


def test_active_config_exposes_media_server_and_not_notion_or_ai():
    assert hasattr(Config, "RADARR_URL")
    assert not hasattr(Config, "NOTION_TOKEN")
    assert not hasattr(Config, "ANTHROPIC_API_KEY")
    assert not hasattr(Config, "OMDB_API_KEY")
