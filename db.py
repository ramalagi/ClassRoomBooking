import os
import psycopg2


DATABASE_URL = os.getenv("DATABASE_URL")


def _normalize_url(url):
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def get_db_connection():
    url = _normalize_url(DATABASE_URL)
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "roombooking"),
    )
