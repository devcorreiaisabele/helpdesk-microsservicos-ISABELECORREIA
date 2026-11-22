"""Consumidor da fila Redis: roda em uma thread de segundo plano.

Eventos esperados (JSON), publicados pelo serviço de chamados:
  {"tipo": "ChamadoAberto|ChamadoAtribuido|ChamadoResolvido",
   "chamado_id": 1, "titulo": "...", "destinatario_id": 7, "ocorrido_em": "..."}
"""
import json
import logging
import threading

import redis

from app import servico
from app.config import FILA, REDIS_URL
from app.database import SessionLocal

log = logging.getLogger("notificacoes.consumidor")

TEXTOS = {
    "ChamadoAberto": "Seu chamado #{id} foi aberto",
    "ChamadoAtribuido": "O chamado #{id} foi atribuído a você",
    "ChamadoResolvido": "Seu chamado #{id} foi resolvido",
}


def processar(bruto: str) -> None:
    evento = json.loads(bruto)
    tipo = evento.get("tipo")
    base = TEXTOS.get(tipo)
    destinatario_id = evento.get("destinatario_id")
    chamado_id = evento.get("chamado_id")
    if base is None or not isinstance(destinatario_id, int):
        log.warning("Evento descartado (inválido): %s", bruto[:200])
        return
    mensagem = base.format(id=chamado_id)
    if evento.get("titulo"):
        mensagem += f": {evento['titulo']}"
    with SessionLocal() as db:
        servico.notificar(db, tipo, destinatario_id, mensagem, chamado_id)
    log.info("Notificação criada (%s) para o usuário %s", tipo, destinatario_id)


def _laco(parar: threading.Event) -> None:
    while not parar.is_set():
        try:
            cliente = redis.Redis.from_url(
                REDIS_URL, decode_responses=True, socket_connect_timeout=3, socket_timeout=15
            )
            log.info("Consumidor conectado ao Redis, fila '%s'", FILA)
            while not parar.is_set():
                item = cliente.blpop([FILA], timeout=2)
                if item is None:
                    continue
                try:
                    processar(item[1])
                except Exception:  # um evento ruim nunca derruba o consumidor
                    log.exception("Falha ao processar evento")
        except redis.RedisError as erro:
            log.warning("Redis indisponível (%s); tentando de novo em 3s", erro)
            parar.wait(3)


def iniciar_consumidor(parar: threading.Event) -> threading.Thread:
    thread = threading.Thread(target=_laco, args=(parar,), name="consumidor-eventos", daemon=True)
    thread.start()
    return thread
