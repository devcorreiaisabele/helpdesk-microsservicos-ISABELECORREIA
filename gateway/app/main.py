# API Gateway do HelpDesk TI: único ponto de entrada (porta 8000).
# Serve a tela e encaminha cada rota para o serviço dono dela, sem conhecer regras
# de negócio. O token do usuário é repassado como está: quem confere é cada serviço.
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "5"))  # segundos, por chamada
TIMEOUT_SAUDE = 2.0
LIMITE_CORPO = 1_000_000  # 1 MB

SERVICOS = {
    "usuarios": {"nome": "Usuários", "url": os.getenv("USUARIOS_URL", "http://usuarios:8000")},
    "inventario": {"nome": "Inventário", "url": os.getenv("INVENTARIO_URL", "http://inventario:8000")},
    "chamados": {"nome": "Chamados", "url": os.getenv("CHAMADOS_URL", "http://chamados:8000")},
}

# primeiro segmento da URL -> serviço dono da rota
ROTAS = {
    "auth": "usuarios",
    "usuarios": "usuarios",
    "ativos": "inventario",
    "chamados": "chamados",
    "notificacoes": "chamados",
}

# só estes cabeçalhos atravessam o gateway (lista permitida, não lista de bloqueio)
CABECALHOS_PEDIDO = {"authorization", "content-type", "accept", "accept-language"}
CABECALHOS_RESPOSTA = {"content-type", "www-authenticate", "retry-after"}

WEB = Path(__file__).parent / "web"
ESTATICOS = {
    "/": "index.html",
    "/estilo.css": "estilo.css",
    "/app.js": "app.js",
    "/status.js": "status.js",
}

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    limites = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT), limits=limites, follow_redirects=False
    ) as cliente:
        app.state.cliente = cliente
        yield


# a documentação automática fica desligada: o gateway não expõe nada além das rotas acima
app = FastAPI(
    title="HelpDesk TI - API Gateway",
    docs_url=None, redoc_url=None, openapi_url=None,
    lifespan=ciclo_de_vida,
)

# >>> notificacoes (gerado por criar_notificacoes.py)
import os as _os

import httpx as _httpx
from fastapi import Request as _Request
from fastapi import Response as _Response

_NOTIFICACOES_URL = _os.getenv("NOTIFICACOES_URL", "http://notificacoes:8000")
_CABECALHOS_SALTADOS = {
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "te", "trailers", "proxy-authenticate", "proxy-authorization",
    "content-encoding",
}
_METODOS_NOTIF = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@app.api_route("/notificacoes", methods=_METODOS_NOTIF, include_in_schema=False)
@app.api_route("/notificacoes/{caminho:path}", methods=_METODOS_NOTIF, include_in_schema=False)
async def _encaminhar_notificacoes(request: _Request, caminho: str = ""):
    destino = f"{_NOTIFICACOES_URL}/notificacoes" + (f"/{caminho}" if caminho else "")
    cabecalhos = {
        k: v for k, v in request.headers.items() if k.lower() not in _CABECALHOS_SALTADOS
    }
    try:
        async with _httpx.AsyncClient(timeout=10) as cliente:
            resp = await cliente.request(
                request.method,
                destino,
                params=request.query_params,
                content=await request.body(),
                headers=cabecalhos,
            )
    except _httpx.HTTPError:
        return _Response(
            content='{"detail":"Serviço de notificações indisponível"}',
            status_code=503,
            media_type="application/json",
        )
    saida = {k: v for k, v in resp.headers.items() if k.lower() not in _CABECALHOS_SALTADOS}
    return _Response(content=resp.content, status_code=resp.status_code, headers=saida)
# <<< notificacoes


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "no-referrer")
    resposta.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path not in ESTATICOS:
        resposta.headers.setdefault("Cache-Control", "no-store")
    return resposta


def erro(status: int, detalhe: str, cabecalhos: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": detalhe}, status_code=status, headers=cabecalhos)


# --- tela -------------------------------------------------------------------

def _estatico(arquivo: str):
    async def entregar():
        return FileResponse(WEB / arquivo)
    return entregar


for _rota, _arquivo in ESTATICOS.items():
    app.add_api_route(_rota, _estatico(_arquivo), methods=["GET"], include_in_schema=False)


# --- saúde ------------------------------------------------------------------

@app.get("/saude", include_in_schema=False)
async def saude(request: Request):
    cliente: httpx.AsyncClient = request.app.state.cliente

    async def consultar(chave: str):
        try:
            r = await cliente.get(f"{SERVICOS[chave]['url']}/saude", timeout=TIMEOUT_SAUDE)
            return chave, "online" if r.status_code == 200 else "offline"
        except httpx.HTTPError:
            return chave, "offline"

    resultados = await asyncio.gather(*(consultar(c) for c in SERVICOS))
    return {"gateway": "online", "servicos": dict(resultados)}


# --- proxy reverso (sempre por último: captura todo o resto) -------------------

@app.api_route(
    "/{caminho:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def encaminhar(caminho: str, request: Request):
    chave = ROTAS.get(caminho.split("/", 1)[0])
    if chave is None:
        return erro(404, "Rota não encontrada.")
    if any(parte in (".", "..") for parte in caminho.split("/")):
        return erro(400, "Caminho inválido.")

    tamanho = request.headers.get("content-length", "")
    if tamanho.isdigit() and int(tamanho) > LIMITE_CORPO:
        return erro(413, "Corpo da requisição grande demais.")
    corpo = await request.body()
    if len(corpo) > LIMITE_CORPO:
        return erro(413, "Corpo da requisição grande demais.")

    servico = SERVICOS[chave]
    # o destino é sempre o host fixo do serviço; o caminho é re-codificado
    # para que "?" ou "#" vindos da URL não virem outra coisa no destino
    url = f"{servico['url']}/{quote(caminho, safe='/')}"
    if request.url.query:
        url += "?" + request.url.query
    cabecalhos = {k: v for k, v in request.headers.items() if k.lower() in CABECALHOS_PEDIDO}

    try:
        r = await request.app.state.cliente.request(
            request.method, url, headers=cabecalhos, content=corpo
        )
    except httpx.TransportError:  # inclui conexão recusada, DNS e tempo esgotado
        return erro(
            503,
            f"O serviço de {servico['nome']} está indisponível no momento. "
            "Tente novamente em instantes.",
            {"Retry-After": "5"},
        )
    except httpx.HTTPError:
        return erro(502, f"Resposta inválida do serviço de {servico['nome']}.")

    cab_resposta = {k: v for k, v in r.headers.items() if k.lower() in CABECALHOS_RESPOSTA}
    return Response(content=r.content, status_code=r.status_code, headers=cab_resposta)
