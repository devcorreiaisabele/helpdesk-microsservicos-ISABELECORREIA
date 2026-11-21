"""Configuração lida do ambiente."""
import os

JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"


def jwt_segredo() -> str:
    """Segredo compartilhado com o serviço `usuarios` (variável JWT_SEGREDO)."""
    segredo = os.environ.get("JWT_SEGREDO", "")
    if not segredo:
        raise RuntimeError("A variável de ambiente JWT_SEGREDO é obrigatória.")
    return segredo


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:////dados/inventario.db")


def dados_exemplo_ativo() -> bool:
    return os.environ.get("DADOS_EXEMPLO", "0") == "1"
