"""Carga inicial de ativos de exemplo (ativada por DADOS_EXEMPLO=1). Idempotente."""
from sqlalchemy.orm import Session

from app.inventario import servico
from app.inventario.esquemas import AtivoCriar
from app.inventario.modelos import Ativo
from app.inventario.repositorio import buscar_por_patrimonio, salvar

ATIVOS_EXEMPLO = [
    AtivoCriar(patrimonio="PAT-0001", tipo="computador", descricao="Desktop Dell OptiPlex 7090", setor="Financeiro"),
    AtivoCriar(patrimonio="PAT-0002", tipo="impressora", descricao="Impressora HP LaserJet Pro M404", setor="Recepção"),
    AtivoCriar(patrimonio="PAT-0003", tipo="notebook", descricao="Notebook Lenovo ThinkPad E14", setor="Comercial"),
]


def carregar_dados_exemplo(db: Session) -> None:
    for dados in ATIVOS_EXEMPLO:
        if buscar_por_patrimonio(db, dados.patrimonio) is None:
            salvar(db, Ativo(**dados.model_dump()))
