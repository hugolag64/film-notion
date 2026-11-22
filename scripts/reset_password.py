"""Reset a Backstage account's password from the command line.

For when the admin is locked out (no email reset configured). The new password
is typed in a hidden prompt and is never printed. All the account's sessions
are signed out, and the account must change its password at next sign-in.

    python scripts/reset_password.py                 # lists the accounts, then asks
    python scripts/reset_password.py you@example.com
"""
import getpass
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import Config  # noqa: E402
from backend.core.auth import AuthStore  # noqa: E402


def main() -> int:
    db_path = Config.DB_PATH
    if not os.path.exists(db_path):
        print(f"Base introuvable : {db_path}")
        return 1

    with sqlite3.connect(db_path) as connection:
        accounts = connection.execute(
            "SELECT id, display_name, email, role FROM users ORDER BY role, display_name"
        ).fetchall()
    if not accounts:
        print("Aucun compte dans la base.")
        return 1

    email = sys.argv[1] if len(sys.argv) > 1 else None
    if not email:
        print(f"Comptes dans {db_path} :")
        for _, name, account_email, role in accounts:
            print(f"  [{role}] {name} <{account_email}>")
        email = input("Email du compte à réinitialiser : ").strip()

    match = next((row for row in accounts if row[2].lower() == email.lower()), None)
    if not match:
        print(f"Aucun compte avec l'email {email}.")
        return 1

    password = getpass.getpass("Nouveau mot de passe : ")
    if password != getpass.getpass("Confirme le mot de passe : "):
        print("Les deux mots de passe ne correspondent pas.")
        return 1

    store = AuthStore(db_path)
    try:
        store.set_password(match[0], password)
    except ValueError as error:
        print(f"Mot de passe refusé : {error}")
        return 1
    print(f"Mot de passe réinitialisé pour {match[1]} <{match[2]}>. "
          "Il faudra le changer à la prochaine connexion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
