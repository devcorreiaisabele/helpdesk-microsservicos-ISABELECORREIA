"""Banco SQLite próprio do serviço."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


_url = make_url(DATABASE_URL)
if _url.drivername.startswith("sqlite") and _url.database:
    try:
        Path(_url.database).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
