"""Serviço notificacoes: eventos que chegam pelo Redis viram avisos, e cada pessoa só vê os seus.

O Redis é o RedisFalso (em memória). O consumidor do serviço é iniciado quando o TestClient sobe o app.
Se o formato dos seus eventos for diferente, ajuste EVENTO_ABERTO abaixo.
"""
import pytest

from apoio_testes import TIPOS_TOKEN_INVALIDO, entregar_evento, esperar_ate, token_invalido

EVENTO_ABERTO = {"tipo": "ChamadoAberto", "chamado_id": 1, "usuario_id": 2, "destinatario_id": 2,
                 "titulo": "PC não liga", "mensagem": "Chamado #1 aberto."}


def listar(cliente, contas, quem):
    return cliente.get("/notificacoes", headers=contas[quem]["headers"])


def test_saude(cliente):
    assert cliente.get("/saude").status_code == 200


# ---------- autenticação ----------

def test_sem_token_retorna_401(cliente):
    assert cliente.get("/notificacoes").status_code == 401


@pytest.mark.parametrize("tipo", TIPOS_TOKEN_INVALIDO)
def test_token_invalido_retorna_401(cliente, contas, tipo):
    headers = {"Authorization": f"Bearer {token_invalido(tipo)}"}
    assert cliente.get("/notificacoes", headers=headers).status_code == 401


# ---------- regras ----------

@pytest.mark.parametrize("quem", ["admin", "ana", "carla"])
def test_qualquer_perfil_lista_os_proprios_avisos(cliente, contas, quem):
    r = listar(cliente, contas, quem)
    assert r.status_code == 200 and r.json() == []


def test_evento_do_redis_vira_notificacao(cliente, contas, redis_falso):
    entregar_evento(redis_falso, EVENTO_ABERTO)
    avisos = esperar_ate(lambda: listar(cliente, contas, "ana").json())
    assert avisos and avisos[0]["tipo"] == "ChamadoAberto"


def test_notificacoes_sao_so_do_proprio_usuario(cliente, contas, redis_falso):
    entregar_evento(redis_falso, EVENTO_ABERTO)  # destinatária: Ana
    assert esperar_ate(lambda: listar(cliente, contas, "ana").json())
    assert listar(cliente, contas, "bia").json() == []
    assert listar(cliente, contas, "carla").json() == []
