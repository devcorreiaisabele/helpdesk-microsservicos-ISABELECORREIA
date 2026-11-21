"""Configurações lidas das variáveis de ambiente."""
import logging
import os
import secrets

log = logging.getLogger("usuarios")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./usuarios.db")

# Segredo usado para assinar os tokens JWT. Em produção, defina JWT_SEGREDO.
# Sem ele, um segredo aleatório é gerado a cada início (os logins expiram ao reiniciar).
# Atenção: outros serviços que validem estes tokens precisam receber o MESMO JWT_SEGREDO.
JWT_SEGREDO = os.getenv("JWT_SEGREDO") or ""
if len(JWT_SEGREDO) < 32:
    if JWT_SEGREDO:
        log.warning("JWT_SEGREDO tem menos de 32 caracteres; usando um segredo aleatório.")
    JWT_SEGREDO = secrets.token_urlsafe(48)

JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"
TOKEN_MINUTOS = int(os.getenv("TOKEN_MINUTOS", "60"))

# Proteção contra tentativas de adivinhar senhas
LOGIN_MAX_FALHAS = int(os.getenv("LOGIN_MAX_FALHAS", "5"))
LOGIN_JANELA_SEGUNDOS = int(os.getenv("LOGIN_JANELA_SEGUNDOS", "300"))

# Tamanho máximo do corpo de uma requisição (em bytes)
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024

DOCS_ATIVA = os.getenv("DOCS", "1") == "1"

# Carga inicial dos usuários de exemplo (só cria os que ainda não existem).
# Em produção, defina DADOS_EXEMPLO=0 ou troque SENHA_EXEMPLO.
DADOS_EXEMPLO = os.getenv("DADOS_EXEMPLO", "1") == "1"
SENHA_EXEMPLO = os.getenv("SENHA_EXEMPLO", "Helpdesk2026")
