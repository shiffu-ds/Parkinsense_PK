"""Issue a single-use recovery code after a clinic has verified the account owner."""

import argparse
from getpass import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import init_db
from backend.production import issue_recovery_token
from backend.services import authenticate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Verified account UUID; do not submit patient names.")
    parser.add_argument("--identity-verified", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private local code file, never a public directory.")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        parser.error("Code output must be a new file in an existing private directory.")
    if args.output.parent.stat().st_mode & 0o077:
        parser.error("Code output directory must be private (chmod 700).")
    init_db()
    try:
        admin = authenticate(input("Administrator email: ").strip(), getpass("Administrator password: "))
        if admin["role"] != "admin":
            raise PermissionError("Administrator access is required.")
        code = issue_recovery_token(admin["id"], args.user_id, identity_verified=args.identity_verified)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(code + "\n")
    except (ValueError, LookupError, PermissionError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print("Recovery code written to the private file. It expires in 20 minutes and works once.")
    print("Deliver it to the verified owner through the clinic's established private channel; delete the file afterwards.")


if __name__ == "__main__":
    main()
