"""Serviço chamados: SLA, fluxo de status, permissões por perfil e eventos publicados no Redis.

Os outros serviços (inventario/usuarios) e o Redis são simulados por `servicos` e `redis_falso`.
"""
from datetime import datetime

import pytest

from apoio_testes import TIPOS_TOKEN_INVALIDO, token_invalido

ROTAS_PROTEGIDAS = [("get", "/chamados"), ("get", "/chamados/1"), ("get", "/chamados/painel"),
                    ("post", "/chamados"), ("patch", "/chamados/1/atribuir"), ("patch", "/chamados/1/status"),
                    ("post", "/chamados/1/comentarios")]


def abrir(cliente, contas, quem="ana", prioridade="alta", **extra):
    dados = {"titulo": "PC não liga", "descricao": "Nada acontece", "prioridade": prioridade, "ativo_id": 1, **extra}
    return cliente.post("/chamados", headers=contas[quem]["headers"], json=dados)


def atribuir(cliente, contas, cid, tecnico="carla", quem="carla"):
    return cliente.patch(f"/chamados/{cid}/atribuir", headers=contas[quem]["headers"],
                         json={"tecnico_id": contas[tecnico]["id"]})


def publicou(redis_falso, tipo):
    return any(tipo in evento for evento in redis_falso.eventos)


def test_saude(cliente):
    assert cliente.get("/saude").status_code == 200


# ---------- autenticação ----------

@pytest.mark.parametrize("metodo,rota", ROTAS_PROTEGIDAS)
def test_sem_token_retorna_401(cliente, metodo, rota):
    assert getattr(cliente, metodo)(rota).status_code == 401, rota


@pytest.mark.parametrize("tipo", TIPOS_TOKEN_INVALIDO)
def test_token_invalido_retorna_401(cliente, contas, tipo):
    headers = {"Authorization": f"Bearer {token_invalido(tipo)}"}
    assert cliente.get("/chamados", headers=headers).status_code == 401


# ---------- abertura ----------

def test_abrir_calcula_sla_consulta_inventario_e_publica_evento(cliente, contas, servicos, redis_falso):
    r = abrir(cliente, contas, prioridade="critica")
    assert r.status_code == 201
    c = r.json()
    assert c["solicitante_id"] == contas["ana"]["id"]
    horas = (datetime.fromisoformat(c["prazo_sla"]) - datetime.fromisoformat(c["criado_em"])).total_seconds() / 3600
    assert round(horas) == 4
    assert any(servicos.servico_de(req) == "inventario" for req in servicos.chamadas)
    assert publicou(redis_falso, "ChamadoAberto")


def test_abrir_com_ativo_inexistente(cliente, contas):
    assert abrir(cliente, contas, ativo_id=999).status_code == 404


def test_nao_da_para_abrir_chamado_em_nome_de_outro(cliente, contas):
    r = abrir(cliente, contas, solicitante_id=contas["bia"]["id"])
    assert r.status_code == 422  # campo extra é recusado


def test_titulo_grande_demais(cliente, contas):
    assert abrir(cliente, contas, titulo="x" * 500).status_code == 422


def test_requisicao_grande_demais(cliente, contas):
    corpo = '{"titulo": "' + "x" * 70000 + '"}'
    r = cliente.post("/chamados", headers={**contas["ana"]["headers"], "Content-Type": "application/json"},
                     content=corpo)
    assert r.status_code == 413


# ---------- atribuição e fluxo de status ----------

def test_atribuir_muda_status_e_publica_evento(cliente, contas, redis_falso):
    cid = abrir(cliente, contas).json()["id"]
    r = atribuir(cliente, contas, cid)
    assert r.status_code == 200 and r.json()["status"] == "em_atendimento"
    assert publicou(redis_falso, "ChamadoAtribuido")


def test_so_tecnico_pode_ser_atribuido(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    assert atribuir(cliente, contas, cid, tecnico="ana").status_code == 422  # ana é solicitante


def test_atribuir_a_usuario_inexistente(cliente, contas, servicos):
    cid = abrir(cliente, contas).json()["id"]
    r = cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["carla"]["headers"], json={"tecnico_id": 999})
    assert r.status_code in (404, 422)


def test_fluxo_completo_de_status(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    tec = contas["carla"]["headers"]
    atribuir(cliente, contas, cid)
    assert cliente.patch(f"/chamados/{cid}/status", headers=tec, json={"status": "resolvido"}).status_code == 200
    # o próprio solicitante confirma e fecha
    r = cliente.patch(f"/chamados/{cid}/status", headers=contas["ana"]["headers"], json={"status": "fechado"})
    assert r.json()["status"] == "fechado"


def test_transicao_invalida(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    r = cliente.patch(f"/chamados/{cid}/status", headers=contas["carla"]["headers"], json={"status": "fechado"})
    assert r.status_code == 422


def test_iniciar_atendimento_sem_tecnico(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    r = cliente.patch(f"/chamados/{cid}/status", headers=contas["carla"]["headers"],
                      json={"status": "em_atendimento"})
    assert r.status_code == 422


# ---------- comentários e painel ----------

def test_comentar_usa_o_usuario_logado(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    r = cliente.post(f"/chamados/{cid}/comentarios", headers=contas["carla"]["headers"],
                     json={"texto": "Verificando a fonte."})
    assert r.status_code == 201 and r.json()["autor_id"] == contas["carla"]["id"]
    assert len(cliente.get(f"/chamados/{cid}", headers=contas["ana"]["headers"]).json()["comentarios"]) == 1


def test_nao_da_para_comentar_em_nome_de_outro(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    r = cliente.post(f"/chamados/{cid}/comentarios", headers=contas["ana"]["headers"],
                     json={"texto": "oi", "autor_id": contas["carla"]["id"]})
    assert r.status_code == 422


def test_painel(cliente, contas):
    abrir(cliente, contas)
    abrir(cliente, contas, prioridade="baixa")
    p = cliente.get("/chamados/painel", headers=contas["carla"]["headers"]).json()
    assert p["total"] == 2 and p["por_status"] == {"aberto": 2}


# ---------- permissões por perfil ----------

def test_solicitante_nao_ve_chamado_de_outra_pessoa(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    assert cliente.get(f"/chamados/{cid}", headers=contas["bia"]["headers"]).status_code == 404
    assert cliente.get("/chamados", headers=contas["bia"]["headers"]).json() == []


def test_solicitante_nao_atribui_nem_resolve(cliente, contas):
    cid = abrir(cliente, contas).json()["id"]
    assert atribuir(cliente, contas, cid, quem="ana").status_code == 403
    r = cliente.patch(f"/chamados/{cid}/status", headers=contas["ana"]["headers"], json={"status": "em_atendimento"})
    assert r.status_code == 403


@pytest.mark.parametrize("quem", ["carla", "admin"])
def test_equipe_ve_todos_os_chamados(cliente, contas, quem):
    abrir(cliente, contas, quem="ana")
    abrir(cliente, contas, quem="bia")
    assert len(cliente.get("/chamados", headers=contas[quem]["headers"]).json()) == 2
