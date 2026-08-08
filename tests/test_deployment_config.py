from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_docker_compose_points_external_media_services_to_the_host_gateway_by_default():
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '${RADARR_URL:-http://host.docker.internal:7878}' in source
    assert '${RADARR_DEFAULT_QUALITY_PROFILE_NAME:-1080p FR - max 10 Go}' in source
    assert '${SONARR_URL:-http://host.docker.internal:8989}' in source
    assert '${JELLYFIN_URL:-http://host.docker.internal:8096}' in source
