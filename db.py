import sqlite3
import os

def get_db_connection():
    db_path = os.getenv('DATABASE_URL', 'roombooking.db')
    return sqlite3.connect(db_path)