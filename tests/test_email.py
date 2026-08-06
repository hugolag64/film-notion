from email.message import EmailMessage

import pytest

from backend.config import Config
from backend.core.email import EmailSender


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.credentials = None
        self.messages: list[EmailMessage] = []
        self.__class__.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.messages.append(message)

    def quit(self):
        return None


def test_password_reset_email_uses_configured_gmail_smtp(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(Config, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(Config, "SMTP_PORT", 587)
    monkeypatch.setattr(Config, "SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setattr(Config, "SMTP_PASSWORD", "google-app-password")
    monkeypatch.setattr(Config, "SMTP_FROM", "sender@gmail.com")

    sender = EmailSender(smtp_factory=FakeSMTP)
    sender.send_password_reset("user@example.com", "https://backstage.home.arpa/reset-password?token=abc")

    smtp = FakeSMTP.instances[0]
    message = smtp.messages[0]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert smtp.started_tls
    assert smtp.credentials == ("sender@gmail.com", "google-app-password")
    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Réinitialisation de votre mot de passe Backstage"
    assert "https://backstage.home.arpa/reset-password?token=abc" in message.get_content()


def test_password_reset_email_requires_smtp_credentials(monkeypatch):
    monkeypatch.setattr(Config, "SMTP_USERNAME", "")
    monkeypatch.setattr(Config, "SMTP_PASSWORD", "")
    monkeypatch.setattr(Config, "SMTP_FROM", "")

    with pytest.raises(RuntimeError, match="SMTP non configuré"):
        EmailSender(smtp_factory=FakeSMTP).send_password_reset(
            "user@example.com", "https://backstage.home.arpa/reset-password?token=abc"
        )
