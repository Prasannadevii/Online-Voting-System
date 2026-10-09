"""Convenience wrapper:  python database/seed.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.database.seed import main  # noqa: E402

if __name__ == "__main__":
    main()
