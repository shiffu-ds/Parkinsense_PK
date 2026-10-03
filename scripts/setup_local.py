"""Generate an ignored local PostgreSQL configuration without printing secrets."""

from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / ".env"
    if target.exists():
        print("Existing .env preserved.")
        return
    password = secrets.token_urlsafe(32)
    target.write_text(
        "POSTGRES_USER=parkinsense\nPOSTGRES_DB=parkinsense\n"
        f"POSTGRES_PASSWORD={password}\nPOSTGRES_PORT=55432\n"
        f"PARKINSENSE_DATABASE_URL=postgresql+psycopg://parkinsense:{password}@127.0.0.1:55432/parkinsense\n"
        "PARKINSENSE_STORAGE_ROOT=data/private\nPARKINSENSE_ALLOW_SQLITE=0\n"
        "PARKINSENSE_ICE_SERVERS=[]\n",
        encoding="utf-8",
    )
    target.chmod(0o600)
    print("Generated private .env. Run the database and bootstrap the first administrator.")


if __name__ == "__main__":
    main()
