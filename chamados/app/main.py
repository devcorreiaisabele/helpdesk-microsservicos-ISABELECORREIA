import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import config
from app.chamados.rotas import router as chamados_router
from app.database import Base, SessionLocal, engine
from app.erros import ErroAplicacao
from app.seguranca import CabecalhosDeSeguranca

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    if not config.JWT_SEGREDO:
        raise RuntimeError("A variável de ambiente JWT_SEGREDO é obrigatória.")
    from app.chamados import modelos  # noqa: F401  (registra as tabelas)
    Base.metadata.create_all(engine)
    if config.DADOS_EXEMPLO:
        from app.dados_exemplo import carregar
        with SessionLocal() as db:
            carregar(db)
    yield


app = FastAPI(title="HelpDesk TI - Chamados", lifespan=ciclo_de_vida)
app.add_middleware(CabecalhosDeSeguranca)


@app.exception_handler(ErroAplicacao)
async def tratar_erro_aplicacao(request: Request, erro: ErroAplicacao):
    cabecalhos = {"WWW-Authenticate": "Bearer"} if erro.status_code == 401 else None
    return JSONResponse(status_code=erro.status_code, content={"detail": erro.mensagem}, headers=cabecalhos)


@app.get("/saude", tags=["Saúde"])
def saude():
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "indisponivel", "servico": "chamados"})
    return {"status": "ok", "servico": "chamados"}


app.include_router(chamados_router)
