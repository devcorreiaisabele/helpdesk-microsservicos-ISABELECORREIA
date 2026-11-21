"""Carga inicial: cria os usuários de exemplo que ainda não existem."""
from sqlalchemy.orm import Session

from app.config import SENHA_EXEMPLO, log
from app.usuarios import servico
from app.usuarios.esquemas import UsuarioCriar

USUARIOS_EXEMPLO = [
    ("Administrador", "admin@empresa.com", "admin"),
    ("Ana Souza", "ana@empresa.com", "solicitante"),
    ("Bruno Lima", "bruno@empresa.com", "solicitante"),
    ("Carla Mendes", "carla@empresa.com", "tecnico"),
    ("Diego Alves", "diego@empresa.com", "tecnico"),
]


def semear(db: Session) -> None:
    criados = 0
    for nome, email, perfil in USUARIOS_EXEMPLO:
        if servico.buscar_por_email(db, email):
            continue
        servico.criar(db, UsuarioCriar(nome=nome, email=email, perfil=perfil, senha=SENHA_EXEMPLO))
        criados += 1
    if criados:
        log.warning("Carga inicial: %d usuário(s) de exemplo criado(s). Não use isto em produção.", criados)
