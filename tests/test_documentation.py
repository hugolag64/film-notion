from pathlib import Path


def test_secure_deployment_guide_covers_production_guardrails():
    guide = (Path(__file__).parents[1] / "docs" / "SECURE_DEPLOYMENT.md").read_text(encoding="utf-8")
    for required in (
        "BACKSTAGE_COOKIE_SECURE=1",
        "HTTPS",
        "VPN",
        "BACKUP_DIR",
        "restauration",
        "mono-instance",
    ):
        assert required in guide
