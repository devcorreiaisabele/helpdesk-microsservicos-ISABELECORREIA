"""Banco próprio do serviço (SQLite)."""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import database_url

_url = make_url(database_url())

if _url.get_backend_name() == "sqlite" and _url.database and _url.database != ":memory:":
    Path(_url.database).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _url,
    connect_args={"check_same_thread": False} if _url.get_backend_name() == "sqlite" else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def criar_tabelas() -> None:
    # Importa os modelos para registrá-los no metadata antes do create_all.
    from app.inventario import modelos  # noqa: F401

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
