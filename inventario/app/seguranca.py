"""Cabeçalhos de segurança aplicados a todas as respostas."""
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# A UI do Swagger/ReDoc carrega scripts de CDN; a CSP restritiva não vale para elas.
_CAMINHOS_DOCS = ("/docs", "/redoc", "/openapi.json")


class CabecalhosDeSeguranca(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        resposta = await call_next(request)
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if not request.url.path.startswith(_CAMINHOS_DOCS):
            resposta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return resposta
