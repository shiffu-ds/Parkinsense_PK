"""Create the first administrator interactively; never ship default credentials."""

from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import init_db
from backend.services import bootstrap_admin


def main():
    init_db()
    name = input("Administrator full name: ").strip()
    email = input("Administrator email: ").strip()
    password = getpass("Password (at least 10 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")
    try:
        bootstrap_admin(name, email, password)
    except (ValueError, PermissionError) as exc:
        raise SystemExit(str(exc)) from None
    print("Administrator created. Log in to manage care-team accounts.")


if __name__ == "__main__":
    main()
