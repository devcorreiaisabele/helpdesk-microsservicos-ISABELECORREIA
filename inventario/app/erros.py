"""Erros de domínio e seus tratadores HTTP."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RegraDeNegocio(Exception):
    """Violação de regra de negócio (HTTP 400)."""


class NaoEncontrado(Exception):
    """Recurso inexistente (HTTP 404)."""


def registrar_tratadores(app: FastAPI) -> None:
    @app.exception_handler(RegraDeNegocio)
    async def _regra(_: Request, exc: RegraDeNegocio) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(_: Request, exc: NaoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
