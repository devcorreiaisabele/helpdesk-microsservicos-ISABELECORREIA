"""Configuração lida das variáveis de ambiente."""
import os

# Obrigatória: mesmo segredo usado pelo serviço de usuários para assinar o JWT.
JWT_SEGREDO = os.environ["JWT_SEGREDO"]
JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////dados/notificacoes.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
FILA = os.getenv("FILA_EVENTOS", "helpdesk:eventos")
