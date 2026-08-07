from backend.config import Config


def test_active_config_exposes_media_server_and_not_notion_or_ai():
    assert hasattr(Config, "RADARR_URL")
    assert not hasattr(Config, "NOTION_TOKEN")
    assert not hasattr(Config, "ANTHROPIC_API_KEY")
    assert not hasattr(Config, "OMDB_API_KEY")
    assert Config.RECOMMENDATION_DAILY_LIMIT == 2
    assert Config.RECOMMENDATION_TIMEZONE == "Europe/Paris"
    assert Config.GEMINI_MODEL == "gemini-3.5-flash-lite"
    assert Config.GEMINI_MAX_OUTPUT_TOKENS == 256


def test_security_rate_limit_defaults_are_exposed():
    assert Config.AUTH_RATE_LIMIT_WINDOW_SEC == 300
    assert Config.AUTH_RATE_LIMIT_MAX_ATTEMPTS == 5
    assert Config.AUTH_RATE_LIMIT_BLOCK_SEC == 900


def test_requirements_include_timezone_database():
    from pathlib import Path

    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "tzdata" in requirements
