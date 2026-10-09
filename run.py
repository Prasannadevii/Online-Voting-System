"""Single-command launcher:  python run.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config


def main():
    from app import create_app
    from backend.database.seed import seed_database

    first_run = not os.path.exists(Config.DATABASE_PATH)
    if first_run:
        print("No database found - seeding development data (fictional)...")
        seed_database(Config.DATABASE_PATH, Config.SECRET_KEY, Config.HASH_ITERATIONS)
    app = create_app()
    url = f"http://{Config.HOST}:{Config.PORT}"
    print("=" * 62)
    print(" NetVote - Secure, Concurrent and Network-Aware Voting System")
    print(f" Open:   {url}")
    print(" DEV admin:  admin / Admin@123     DEV voters: 10001..10020 / Voter@123")
    print(" Stop with Ctrl+C")
    print("=" * 62)
    # threaded=True -> werkzeug creates one OS thread per connection (concurrent requests).
    # use_reloader=False keeps a single process, so the in-process vote lock is effective.
    app.run(host=Config.HOST, port=Config.PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    sys.exit(main())
