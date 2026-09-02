from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# This tells SQLAlchemy to create a database file named "land_records.db"
SQLALCHEMY_DATABASE_URL = "sqlite:///./land_records.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# This is a helper function we will use later to connect to the DB in our APIs
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()