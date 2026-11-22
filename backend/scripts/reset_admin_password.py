"""Reset the password of a local Backstage admin account.

Usage (from the project root):
    .venv/Scripts/python.exe -m backend.scripts.reset_admin_password

Lists the admin accounts of DB_PATH, asks which one to reset and the new
password (typed without echo), then revokes its open sessions.
"""
import getpass
import sqlite3
import sys
from datetime import datetime, timezone

from backend.config import Config
from backend.core.auth import hash_password


def main() -> int:
    with sqlite3.connect(Config.DB_PATH) as connection:
        admins = connection.execute(
            "SELECT id, display_name, email FROM users WHERE role = 'admin' ORDER BY display_name"
        ).fetchall()
        if not admins:
            print(f"Aucun compte admin dans {Config.DB_PATH}.")
            return 1
        for index, (_, name, email) in enumerate(admins, start=1):
            print(f"  {index}. {name} <{email}>")
        choice = input("Compte à réinitialiser [1] : ").strip() or "1"
        if not choice.isdigit() or not 1 <= int(choice) <= len(admins):
            print("Choix invalide.")
            return 1
        user_id, name, email = admins[int(choice) - 1]

        password = getpass.getpass("Nouveau mot de passe (8 caractères min.) : ")
        if len(password) < 8:
            print("Mot de passe trop court.")
            return 1
        if getpass.getpass("Confirme le mot de passe : ") != password:
            print("Les deux saisies diffèrent.")
            return 1

        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
            (hash_password(password), now, user_id),
        )
        connection.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )
    print(f"Mot de passe mis à jour pour {name} — connecte-toi avec {email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
