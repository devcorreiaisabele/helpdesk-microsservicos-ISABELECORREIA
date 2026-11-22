from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import servico
from app.auth import usuario_atual
from app.database import get_db
from app.esquemas import NotificacaoSaida

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


@router.get("", response_model=list[NotificacaoSaida])
def minhas_notificacoes(
    apenas_nao_lidas: bool = False,
    usuario_id: int = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Cada usuário vê só as próprias notificações (mais recentes primeiro)."""
    return servico.listar(db, usuario_id, apenas_nao_lidas)


@router.patch("/{notificacao_id}/lida", response_model=NotificacaoSaida)
def marcar_como_lida(
    notificacao_id: int,
    usuario_id: int = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    aviso = servico.marcar_lida(db, notificacao_id, usuario_id)
    if aviso is None:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    return aviso
