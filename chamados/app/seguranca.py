"""Cabeçalhos de segurança aplicados a todas as respostas."""
from starlette.middleware.base import BaseHTTPMiddleware


class CabecalhosDeSeguranca(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resposta = await call_next(request)
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return resposta
