"""Password hashing, voter pseudonyms and the vote hash-chain."""
import hashlib
import hmac

from werkzeug.security import check_password_hash, generate_password_hash

GENESIS_HASH = "0" * 64
_DUMMY = None


def hash_password(password: str, iterations: int = 200000) -> str:
    # Salted PBKDF2-SHA256 (Werkzeug). Plaintext passwords are never stored or logged.
    return generate_password_hash(password, method=f"pbkdf2:sha256:{iterations}")


def verify_password(stored_hash: str, password: str) -> bool:
    return check_password_hash(stored_hash, password)


def burn_time(password: str, iterations: int = 200000) -> None:
    """Hash a dummy value so 'unknown user' and 'wrong password' take similar time
    (reduces user-enumeration via timing)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("dummy-password", iterations)
    check_password_hash(_DUMMY, password)


def voter_ref(voter_id: str, secret: str) -> str:
    """Pseudonymous reference stored in `votes` instead of the voter id (ballot secrecy)."""
    return hmac.new(secret.encode(), voter_id.encode(), hashlib.sha256).hexdigest()[:24]


def chain_hash(prev_hash: str, tx_id: str, ref: str, candidate_id: int, ts: str) -> str:
    """Each vote commits to the previous one => modifying history is detectable."""
    return hashlib.sha256(f"{prev_hash}|{tx_id}|{ref}|{candidate_id}|{ts}".encode()).hexdigest()
