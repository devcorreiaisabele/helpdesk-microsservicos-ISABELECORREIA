from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    destinatario_id: int
    chamado_id: int | None = None
    mensagem: str
    lida: bool
    criada_em: datetime
