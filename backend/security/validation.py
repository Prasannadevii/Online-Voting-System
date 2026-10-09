"""Input validation (server side - never trust the browser)."""
import re

from backend.utils.helpers import ApiError

VOTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")


def json_body(request) -> dict:
    """Parse JSON or raise 400 (malformed request)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("MALFORMED_REQUEST", "Request body must be a valid JSON object.", 400)
    return data


def require_fields(data: dict, *fields):
    missing = [f for f in fields if f not in data or data[f] in (None, "")]
    if missing:
        raise ApiError("MISSING_FIELDS", "Missing required field(s): " + ", ".join(missing), 400,
                       fields=missing)


def clean_str(value, name, min_len=1, max_len=200) -> str:
    if not isinstance(value, str):
        raise ApiError("INVALID_FIELD", f"{name} must be text.", 400)
    value = value.strip()
    if not (min_len <= len(value) <= max_len):
        raise ApiError("INVALID_FIELD", f"{name} must be {min_len}-{max_len} characters.", 400)
    return value


def validate_registration(data: dict) -> dict:
    require_fields(data, "voter_id", "name", "email", "password", "confirm_password")
    voter_id = clean_str(data["voter_id"], "Voter ID", 3, 20)
    if not VOTER_ID_RE.match(voter_id):
        raise ApiError("INVALID_VOTER_ID", "Voter ID may contain letters, digits, '-' and '_' (3-20).", 400)
    name = clean_str(data["name"], "Full name", 2, 80)
    email = clean_str(data["email"], "Email", 5, 320).lower()
    if not EMAIL_RE.match(email):
        raise ApiError("INVALID_EMAIL", "Please enter a valid email address.", 400)
    password = data["password"]
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        raise ApiError("WEAK_PASSWORD", "Password must be 8-128 characters.", 400)
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise ApiError("WEAK_PASSWORD", "Password must contain at least one letter and one digit.", 400)
    if password != data["confirm_password"]:
        raise ApiError("PASSWORD_MISMATCH", "Passwords do not match.", 400)
    return {"voter_id": voter_id, "name": name, "email": email, "password": password}


def validate_candidate(data: dict) -> dict:
    require_fields(data, "name", "party")
    color = data.get("color") or "#2456e6"
    if not re.match(r"^#[0-9a-fA-F]{6}$", str(color)):
        raise ApiError("INVALID_FIELD", "Colour must look like #2456e6.", 400)
    return {"name": clean_str(data["name"], "Name", 2, 80),
            "party": clean_str(data["party"], "Party", 2, 80),
            "symbol": clean_str(data.get("symbol") or "*", "Symbol", 1, 8),
            "color": color,
            "description": clean_str(data.get("description") or "", "Description", 0, 300)}


def parse_int(value, name) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError("INVALID_FIELD", f"{name} must be an integer.", 400)
    try:
        return int(value)
    except ValueError:
        raise ApiError("INVALID_FIELD", f"{name} must be an integer.", 400)
