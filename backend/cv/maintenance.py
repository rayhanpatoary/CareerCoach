"""Explicit scheduled expiry cleanup: python -m cv.maintenance. Never automatic."""
from dotenv import load_dotenv
from pathlib import Path
from interviews.database import get_engine
from .repository import CvRepository

if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    CvRepository(get_engine()).cleanup()
    print("Expired CV reviews removed.")
