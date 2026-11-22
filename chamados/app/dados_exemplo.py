"""Carga inicial de chamados de exemplo (só roda com DADOS_EXEMPLO=1 e tabela vazia)."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chamados.modelos import Chamado, Comentario
from app.chamados.servico import calcular_prazo

log = logging.getLogger("chamados")

# (titulo, descricao, prioridade, status, solicitante, tecnico, ativo, horas_atras, [(autor, texto)])
EXEMPLOS = [
    ("Notebook não liga", "O notebook não liga nem com o carregador conectado.", "alta",
     "aberto", 3, None, 1, 1, []),
    ("Sem acesso à VPN", "Aparece erro de autenticação ao conectar na VPN.", "media",
     "em_atendimento", 4, 2, None, 5,
     [(2, "Resetei a senha da VPN, pode testar novamente?"), (4, "Testando agora.")]),
    ("Servidor de arquivos fora do ar", "Ninguém do financeiro acessa a pasta compartilhada.", "critica",
     "em_atendimento", 3, 2, 2, 10,
     [(2, "Identificado problema no disco; em andamento.")]),
    ("Instalar o pacote Office", "Preciso do Office instalado na máquina nova.", "baixa",
     "resolvido", 4, 2, 3, 30,
     [(2, "Instalação concluída."), (4, "Obrigado!")]),
    ("Impressora do 2º andar com papel enroscado", "Já tentei puxar o papel, sem sucesso.", "media",
     "fechado", 3, 2, 4, 70, []),
]


def carregar(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Chamado)):
        return
    agora = datetime.now()
    for titulo, descricao, prioridade, status, solic, tec, ativo, horas, comentarios in EXEMPLOS:
        criado = agora - timedelta(hours=horas)
        chamado = Chamado(
            titulo=titulo, descricao=descricao, prioridade=prioridade, status=status,
            solicitante_id=solic, tecnico_id=tec, ativo_id=ativo,
            criado_em=criado, prazo_sla=calcular_prazo(prioridade, criado),
        )
        for i, (autor, texto) in enumerate(comentarios, start=1):
            chamado.comentarios.append(Comentario(
                autor_id=autor, texto=texto, criado_em=criado + timedelta(minutes=10 * i)
            ))
        db.add(chamado)
    db.commit()
    log.info("Carga inicial: %d chamados de exemplo criados.", len(EXEMPLOS))
