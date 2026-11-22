"""Regras do módulo de notificações."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Notificacao


def notificar(
    db: Session, tipo: str, destinatario_id: int, mensagem: str, chamado_id: int | None = None
) -> Notificacao:
    """Registra um aviso. No mundo real, aqui seria enviado um e-mail ou SMS."""
    aviso = Notificacao(
        tipo=tipo,
        destinatario_id=destinatario_id,
        chamado_id=chamado_id,
        mensagem=mensagem[:300],
        lida=False,
        criada_em=datetime.now(),
    )
    db.add(aviso)
    db.commit()
    db.refresh(aviso)
    return aviso


def listar(
    db: Session, destinatario_id: int, apenas_nao_lidas: bool = False
) -> list[Notificacao]:
    consulta = (
        select(Notificacao)
        .where(Notificacao.destinatario_id == destinatario_id)
        .order_by(Notificacao.id.desc())
    )
    if apenas_nao_lidas:
        consulta = consulta.where(Notificacao.lida.is_(False))
    return list(db.scalars(consulta))


def marcar_lida(db: Session, notificacao_id: int, destinatario_id: int) -> Notificacao | None:
    """Só o dono da notificação pode marcá-la; para os outros ela 'não existe'."""
    aviso = db.get(Notificacao, notificacao_id)
    if aviso is None or aviso.destinatario_id != destinatario_id:
        return None
    aviso.lida = True
    db.commit()
    db.refresh(aviso)
    return aviso
