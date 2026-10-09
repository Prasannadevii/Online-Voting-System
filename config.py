"""NetVote configuration.

Values come from environment variables / a .env file. No production secret is
hard-coded: if SECRET_KEY is empty a random key is generated once and stored
in instance/secret.key (which is git-ignored).
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env parser (avoids an extra dependency)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _get_secret_key() -> str:
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key
    key_file = BASE_DIR / "instance" / "secret.key"
    key_file.parent.mkdir(exist_ok=True)
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def _resolve(path_str: str) -> str:
    p = Path(path_str)
    return str(p if p.is_absolute() else BASE_DIR / p)


class Config:
    SECRET_KEY = _get_secret_key()
    DATABASE_PATH = _resolve(os.environ.get("DATABASE_PATH", "database/voting.db"))
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _get_int("PORT", 5000)
    DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")
    LOG_DIR = str(BASE_DIR / "logs")

    # --- Networking / rate limiting (application level, NOT TCP congestion control)
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_SENSITIVE = _get_int("RATE_LIMIT_SENSITIVE", 20)   # login/register/vote per IP
    RATE_LIMIT_GENERAL = _get_int("RATE_LIMIT_GENERAL", 300)      # other API calls per IP
    RATE_LIMIT_WINDOW = _get_int("RATE_LIMIT_WINDOW", 60)         # seconds

    # --- Security
    HASH_ITERATIONS = _get_int("HASH_ITERATIONS", 200000)         # PBKDF2-SHA256
    SESSION_MINUTES = _get_int("SESSION_MINUTES", 30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # --- Concurrency
    LOCK_TIMEOUT_S = 10.0          # max time a request waits for the vote lock
    MAX_CONCURRENCY_TEST = 500
