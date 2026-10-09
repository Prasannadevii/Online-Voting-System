"""Seed the database with FICTIONAL development data.

Run:  python database/seed.py      (resets database/voting.db)
DEV ONLY credentials:  admin / Admin@123   |   voters 10001..10020 / Voter@123
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config                                            # noqa: E402
from backend.concurrency.vote_lock import InstrumentedLock           # noqa: E402
from backend.database.database import db, init_db                    # noqa: E402
from backend.security.hashing import hash_password                   # noqa: E402
from backend.services import voting_service                          # noqa: E402
from backend.utils.helpers import now_iso                            # noqa: E402

CANDIDATES = [
    ("Anika Rao", "Civic Future Party", "🏛", "#2456e6", "Public services, transparent budgeting and civic technology."),
    ("Marcus Bell", "People's Development Party", "🌾", "#c0562c", "Rural infrastructure, local jobs and affordable housing."),
    ("Leena Fernandes", "National Reform Party", "⚖", "#7a4fd1", "Legal and administrative reform with faster public services."),
    ("Tomas Wright", "Green Progress Party", "🌱", "#12805c", "Clean energy, public transport and climate resilience."),
    ("Priya Menon", "Digital Citizens Party", "💡", "#b7791f", "Digital literacy, open data and privacy-first technology."),
]
NAMES = ["Aarav Nair", "Diya Kapoor", "Kabir Shah", "Meera Iyer", "Rohan Das", "Sana Khan", "Vikram Rao",
         "Isha Verma", "Arjun Pillai", "Nisha Menon", "Dev Malhotra", "Tara Joshi", "Yash Gupta",
         "Zoya Ali", "Harsh Patel", "Lakshmi Raman", "Neel Bose", "Pooja Singh", "Samar Qureshi", "Uma Devi"]


def seed_database(db_path, ref_secret, iterations=200000, voters=20, pre_voted=5, reset=True):
    if reset:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(str(db_path) + suffix)
            except FileNotFoundError:
                pass
    init_db(db_path)
    voter_pw = hash_password("Voter@123", iterations)
    with db(db_path) as conn:
        conn.execute("INSERT INTO admins(username,password_hash,created_at) VALUES (?,?,?)",
                     ("admin", hash_password("Admin@123", iterations), now_iso()))
        for i in range(voters):
            conn.execute("INSERT INTO voters(voter_id,name,email,password_hash,created_at) VALUES (?,?,?,?,?)",
                         (str(10001 + i), NAMES[i % len(NAMES)], f"voter{10001 + i}@example.test", voter_pw, now_iso()))
        for name, party, symbol, color, desc in CANDIDATES:
            conn.execute("INSERT INTO candidates(name,party,symbol,color,description) VALUES (?,?,?,?,?)",
                         (name, party, symbol, color, desc))
        conn.execute("INSERT INTO election_config(election_name,start_time,status,total_registered,total_votes) "
                     "VALUES (?,?,?,?,0)", ("Civic Council Election 2026 (fictional)", now_iso(), "ACTIVE", voters))
    lock = InstrumentedLock("seed", 30)
    for i in range(pre_voted):                                  # go through the REAL vote path
        voting_service.cast_vote(db_path, str(10001 + i), (i % len(CANDIDATES)) + 1,
                                 f"REQ-2026-SEED{i:04d}", "127.0.0.1", "seed", lock=lock,
                                 ref_secret=ref_secret, audit=False)
    return {"voters": voters, "candidates": len(CANDIDATES), "votes": pre_voted}


def main():
    info = seed_database(Config.DATABASE_PATH, Config.SECRET_KEY, Config.HASH_ITERATIONS)
    print(f"Seeded {Config.DATABASE_PATH}: {info}")
    print("DEV credentials -> admin: admin / Admin@123 | voters: 10001..10020 / Voter@123")


if __name__ == "__main__":
    main()
