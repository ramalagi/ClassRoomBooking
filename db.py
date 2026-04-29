import os
import psycopg2
import psycopg2.extras

def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url)

    host = os.getenv('PGHOST', 'localhost')
    database = os.getenv('PGDATABASE', 'RoomBooking')
    user = os.getenv('PGUSER')
    password = os.getenv('PGPASSWORD')
    port = os.getenv('PGPORT', '5432')

    conn_params = f"host={host} dbname={database} port={port}"
    if user and password:
        conn_params += f" user={user} password={password}"

    return psycopg2.connect(conn_params)