"""E-mail delivery for Backstage account recovery."""

import smtplib
from email.message import EmailMessage
from typing import Callable

from backend.config import Config


class EmailSender:
    def __init__(self, smtp_factory: Callable = smtplib.SMTP):
        self.smtp_factory = smtp_factory

    def send_password_reset(self, recipient: str, reset_url: str) -> None:
        if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD or not Config.SMTP_FROM:
            raise RuntimeError("SMTP non configuré")

        message = EmailMessage()
        message["From"] = Config.SMTP_FROM
        message["To"] = recipient
        message["Subject"] = "Réinitialisation de votre mot de passe Backstage"
        message.set_content(
            "Bonjour,\n\n"
            "Une demande de réinitialisation de votre mot de passe Backstage a été reçue.\n"
            f"Utilisez ce lien pour choisir un nouveau mot de passe :\n{reset_url}\n\n"
            "Ce lien est valable pendant 1 heure et ne peut être utilisé qu'une seule fois.\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n"
        )

        smtp = self.smtp_factory(Config.SMTP_HOST, Config.SMTP_PORT)
        try:
            smtp.starttls()
            smtp.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            smtp.send_message(message)
        finally:
            smtp.quit()
