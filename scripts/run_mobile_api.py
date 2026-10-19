"""Start the native Android gateway; the existing web server is independent."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    import uvicorn
    load_dotenv(ROOT / ".env", override=False)
    host = os.getenv("PARKINSENSE_MOBILE_HOST", "127.0.0.1")
    port = int(os.getenv("PARKINSENSE_MOBILE_PORT", "8767"))
    if not 1 <= port <= 65535:
        raise ValueError("Use a valid mobile API port.")
    print(f"ParkinSense PK patient API listening on {host}:{port}.")
    uvicorn.run("backend.mobile_api:app", host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
