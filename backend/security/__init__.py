"""Password hashing using the standard library's memory-hard scrypt."""

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not 10 <= len(password) <= 1024:
        raise ValueError("Use a password between 10 and 1024 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or len(password) > 1024:
        return False
    try:
        method, n, r, p, salt, expected = encoded.split("$")
        if method != "scrypt" or (n, r, p) != ("16384", "8", "1"):
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


# Consume the same hash workload for unknown and known accounts at login.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(24))
