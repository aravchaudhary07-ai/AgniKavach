import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from database.connection import engine, Base, db_user, db_pass, db_host, db_port, db_name
import database.models  # Ensure models are imported for metadata creation


def initialize_database():
    print(f"Connecting to PostgreSQL server at {db_host}:{db_port} as user '{db_user}'...")
    
    # 1. Connect to default postgres DB to check/create agnikavach_db
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_pass,
        dbname="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';")
    exists = cur.fetchone()
    if not exists:
        print(f"Creating database '{db_name}'...")
        cur.execute(f"CREATE DATABASE {db_name};")
        print(f"Database '{db_name}' created successfully.")
    else:
        print(f"Database '{db_name}' already exists.")
    
    cur.close()
    conn.close()

    # 2. Connect to agnikavach_db and activate PostGIS
    print(f"Connecting to '{db_name}' to enable PostGIS extension...")
    db_conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_pass,
        dbname=db_name
    )
    db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    db_cur = db_conn.cursor()
    
    db_cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    db_cur.execute("SELECT PostGIS_Version();")
    postgis_ver = db_cur.fetchone()[0]
    print(f"PostGIS version {postgis_ver} is active on '{db_name}'.")
    
    db_cur.close()
    db_conn.close()

    # 3. Create all tables using SQLAlchemy ORM
    print("Creating spatial database tables (hotspots, infrastructure, baselines, alerts)...")
    Base.metadata.create_all(bind=engine)
    print("All tables successfully verified & created!")


if __name__ == "__main__":
    initialize_database()
