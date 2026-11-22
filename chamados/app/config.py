"""Configuração do serviço, lida das variáveis de ambiente."""
import os

JWT_SEGREDO = os.environ.get("JWT_SEGREDO", "")
JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"

USUARIOS_URL = os.environ.get("USUARIOS_URL", "http://usuarios:8000").rstrip("/")
INVENTARIO_URL = os.environ.get("INVENTARIO_URL", "http://inventario:8000").rstrip("/")
TIMEOUT_HTTP = 3.0  # segundos

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////dados/chamados.db")
DADOS_EXEMPLO = os.environ.get("DADOS_EXEMPLO", "0") == "1"
