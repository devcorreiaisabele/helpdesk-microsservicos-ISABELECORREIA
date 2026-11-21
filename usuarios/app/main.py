"""Ponto de entrada do microsserviço de Usuários."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import rotas as rotas_auth
from app.cabecalhos import CabecalhosDeSeguranca
from app.carga_inicial import semear
from app.config import DOCS_ATIVA, DADOS_EXEMPLO
from app.database import Base, SessionLocal, engine
from app.erros import NaoEncontrado, RegraDeNegocio, SemPermissao
from app.usuarios import modelos  # noqa: F401  (registra a tabela antes do create_all)
from app.usuarios import rotas as rotas_usuarios


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    Base.metadata.create_all(engine)
    if DADOS_EXEMPLO:
        with SessionLocal() as db:
            semear(db)
    yield


app = FastAPI(
    title="HelpDesk TI - Usuários",
    lifespan=ciclo_de_vida,
    docs_url="/docs" if DOCS_ATIVA else None,
    redoc_url="/redoc" if DOCS_ATIVA else None,
    openapi_url="/openapi.json" if DOCS_ATIVA else None,
)
app.add_middleware(CabecalhosDeSeguranca)
app.include_router(rotas_auth.router)
app.include_router(rotas_usuarios.router)


@app.exception_handler(NaoEncontrado)
async def _nao_encontrado(_: Request, erro: NaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": str(erro)})


@app.exception_handler(RegraDeNegocio)
async def _regra_de_negocio(_: Request, erro: RegraDeNegocio):
    return JSONResponse(status_code=400, content={"detail": str(erro)})


@app.exception_handler(SemPermissao)
async def _sem_permissao(_: Request, erro: SemPermissao):
    return JSONResponse(status_code=403, content={"detail": str(erro)})


@app.get("/saude", include_in_schema=False)
def saude():
    """Verificação de saúde para o orquestrador de contêineres."""
    return {"status": "ok"}
