from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notificacao(Base):
    __tablename__ = "notificacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40))
    destinatario_id: Mapped[int] = mapped_column(index=True)
    chamado_id: Mapped[int | None] = mapped_column(default=None)
    mensagem: Mapped[str] = mapped_column(String(300))
    lida: Mapped[bool] = mapped_column(default=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
