import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Locate .env file in parent directory or current directory
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

db_user = "postgres"
db_pass = "arav123"
db_host = "localhost"
db_port = "5432"
db_name = "agnikavach_db"

if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "DB_USER": db_user = v
                elif k == "DB_PASSWORD": db_pass = v
                elif k == "DB_HOST": db_host = v
                elif k == "DB_PORT": db_port = v
                elif k == "DB_NAME": db_name = v

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
