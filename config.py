import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("CAMPUSPRINT_SECRET_KEY", "campusprint-dev-secret-change-me")
DATABASE = os.path.join(BASE_DIR, "campusprint.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
