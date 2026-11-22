import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import modelos  # noqa: F401  (registra a tabela no Base)
from app.consumidor import iniciar_consumidor
from app.database import Base, engine
from app.roteador import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    Base.metadata.create_all(engine)
    parar = threading.Event()
    thread = iniciar_consumidor(parar)
    yield
    parar.set()
    thread.join(timeout=5)


app = FastAPI(title="HelpDesk TI - Notificações", lifespan=ciclo_de_vida)


@app.get("/saude")
def saude():
    return {"status": "ok", "servico": "notificacoes"}


app.include_router(router)
