from .base import *  # noqa: F401, F403

DEBUG = True
SECRET_KEY = "dev-secret-key-not-for-production"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# DATABASES falls through to base.py:
# - SQLite (db.sqlite3) when DATABASE_URL is not set (local dev)
# - PostgreSQL via dj_database_url when DATABASE_URL is set
