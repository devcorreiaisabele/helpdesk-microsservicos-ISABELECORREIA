"""Banco SQLite próprio do serviço de Chamados."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


_url = make_url(config.DATABASE_URL)
if _url.get_backend_name() == "sqlite" and _url.database:
    try:
        Path(_url.database).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # em contêiner o volume /dados já existe; o erro aparecerá ao conectar

engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
