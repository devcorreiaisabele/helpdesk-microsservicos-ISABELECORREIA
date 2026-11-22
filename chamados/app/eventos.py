"""Publicação de eventos de chamados no Redis (gerado por criar_notificacoes.py).

Regra de ouro: NADA aqui pode derrubar ou atrasar o serviço de chamados.
 - a publicação roda em segundo plano (thread) depois que a resposta já foi montada;
 - qualquer falha (Redis fora do ar, timeout, JSON estranho) vira só um log de aviso.

Os eventos são detectados observando as respostas bem-sucedidas das rotas:
    POST  /chamados                      -> ChamadoAberto
    POST|PUT|PATCH /chamados/{id}/atribuir  -> ChamadoAtribuido
    POST|PUT|PATCH /chamados/{id}/resolver  -> ChamadoResolvido
Se as suas rotas tiverem outros nomes, ajuste ACOES_* abaixo. Os campos do JSON
de resposta também são procurados por vários nomes comuns (CAMPOS_*).
"""
import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone

import redis
from fastapi import FastAPI, Request, Response

log = logging.getLogger("chamados.eventos")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
FILA = os.getenv("FILA_EVENTOS", "helpdesk:eventos")

METODOS = {"POST", "PUT", "PATCH"}
ACOES_ATRIBUIR = {"atribuir", "atribuicao", "atribuição", "atribuido", "atribuído"}
ACOES_RESOLVER = {"resolver", "resolvido", "concluir", "fechar", "status"}
STATUS_RESOLVIDO = {"resolvido", "resolvida", "fechado", "fechada", "concluido", "concluído"}

CAMPOS_ID = ("id", "chamado_id")
CAMPOS_TITULO = ("titulo", "assunto", "resumo", "descricao")
CAMPOS_SOLICITANTE = (
    "solicitante_id", "usuario_id", "criado_por_id", "autor_id",
    "aberto_por_id", "cliente_id", "solicitante", "usuario",
)
CAMPOS_TECNICO = (
    "tecnico_id", "atribuido_a_id", "responsavel_id", "atendente_id",
    "atribuido_a", "responsavel", "tecnico",
)

_ROTA = re.compile(r"/chamados(?:/(?P<id>\d+)(?:/(?P<acao>[\w-]+))?)?/?$")
_cliente: "redis.Redis | None" = None


def _como_id(valor):
    if isinstance(valor, dict):
        valor = valor.get("id")
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return None


def _primeiro_id(corpo: dict, campos):
    for campo in campos:
        achado = _como_id(corpo.get(campo))
        if achado is not None:
            return achado
    return None


def _usuario_do_token(autorizacao: str | None):
    """Lê o 'sub' do JWT sem revalidar (a validação é responsabilidade das rotas)."""
    try:
        payload = autorizacao.split(" ", 1)[1].split(".")[1]
        dados = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return _como_id(dados.get("sub")) or _como_id(dados.get("usuario_id"))
    except Exception:
        return None


def classificar(metodo: str, caminho: str, corpo: dict) -> str | None:
    achado = _ROTA.search(caminho)
    if not achado or metodo not in METODOS:
        return None
    acao = (achado["acao"] or "").lower()
    if achado["id"] is None:
        return "ChamadoAberto" if metodo == "POST" else None
    if acao in ACOES_ATRIBUIR:
        return "ChamadoAtribuido"
    if acao in ACOES_RESOLVER:
        return "ChamadoResolvido"
    if not acao and metodo in {"PUT", "PATCH"}:
        if str(corpo.get("status", "")).lower() in STATUS_RESOLVIDO:
            return "ChamadoResolvido"
    return None


def montar_evento(tipo: str, corpo: dict, autorizacao: str | None) -> dict | None:
    if tipo == "ChamadoAtribuido":
        destinatario = _primeiro_id(corpo, CAMPOS_TECNICO)
    elif tipo == "ChamadoAberto":
        destinatario = _primeiro_id(corpo, CAMPOS_SOLICITANTE) or _usuario_do_token(autorizacao)
    else:
        destinatario = _primeiro_id(corpo, CAMPOS_SOLICITANTE)
    chamado_id = _primeiro_id(corpo, CAMPOS_ID)
    if destinatario is None or chamado_id is None:
        log.warning("Evento %s ignorado: não achei chamado/destinatário na resposta", tipo)
        return None
    titulo = next((corpo[c] for c in CAMPOS_TITULO if isinstance(corpo.get(c), str)), None)
    return {
        "tipo": tipo,
        "chamado_id": chamado_id,
        "titulo": (titulo or "")[:120],
        "destinatario_id": destinatario,
        "ocorrido_em": datetime.now(timezone.utc).isoformat(),
    }


def publicar_evento(evento: dict) -> bool:
    """Empurra o evento na fila. Nunca levanta exceção."""
    global _cliente
    try:
        if _cliente is None:
            _cliente = redis.Redis.from_url(
                REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5
            )
        _cliente.rpush(FILA, json.dumps(evento, ensure_ascii=False))
        return True
    except Exception as erro:
        log.warning("Não consegui publicar %s no Redis: %s", evento.get("tipo"), erro)
        return False


def instalar_publicador(app: FastAPI) -> None:
    tarefas: set = set()

    @app.middleware("http")
    async def _publicar_eventos(request: Request, call_next):
        resposta = await call_next(request)
        if request.method not in METODOS or not 200 <= resposta.status_code < 300:
            return resposta
        if not _ROTA.search(request.url.path):
            return resposta

        corpo_bytes = getattr(resposta, "body", None) or b"".join([parte async for parte in resposta.body_iterator])
        nova = Response(
            content=corpo_bytes,
            status_code=resposta.status_code,
            headers=dict(resposta.headers),
        )
        try:
            corpo = json.loads(corpo_bytes or b"null")
            if isinstance(corpo, dict):
                tipo = classificar(request.method, request.url.path, corpo)
                if tipo:
                    evento = montar_evento(tipo, corpo, request.headers.get("authorization"))
                    if evento:
                        tarefa = asyncio.create_task(asyncio.to_thread(publicar_evento, evento))
                        tarefas.add(tarefa)
                        tarefa.add_done_callback(tarefas.discard)
        except Exception as erro:
            log.warning("Falha ao preparar evento: %s", erro)
        return nova
