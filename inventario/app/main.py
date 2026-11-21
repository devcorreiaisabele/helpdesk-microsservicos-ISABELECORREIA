"""Ponto de entrada do microsserviço de Inventário."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import dados_exemplo_ativo, jwt_segredo
from app.database import SessionLocal, criar_tabelas
from app.erros import registrar_tratadores
from app.inventario.dados_exemplo import carregar_dados_exemplo
from app.inventario.rotas import router as router_inventario
from app.seguranca import CabecalhosDeSeguranca


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    jwt_segredo()  # falha cedo se JWT_SEGREDO não estiver definido
    criar_tabelas()
    if dados_exemplo_ativo():
        with SessionLocal() as db:
            carregar_dados_exemplo(db)
    yield


app = FastAPI(title="HelpDesk TI - Inventário", version="1.0.0", lifespan=ciclo_de_vida)
app.add_middleware(CabecalhosDeSeguranca)
registrar_tratadores(app)
app.include_router(router_inventario)


@app.get("/saude", tags=["Saúde"])
def saude() -> dict[str, str]:
    return {"status": "ok", "servico": "inventario"}
