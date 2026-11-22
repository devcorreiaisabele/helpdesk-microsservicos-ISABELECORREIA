"""Serviço inventario: autenticação, permissões por perfil e regras dos ativos."""
import pytest

from apoio_testes import TIPOS_TOKEN_INVALIDO, token_invalido

ROTAS_PROTEGIDAS = [("get", "/ativos"), ("get", "/ativos/1"), ("post", "/ativos")]


def novo_ativo(**extra):
    return {"patrimonio": "PAT-1", "tipo": "computador", "descricao": "Desktop", "setor": "TI", **extra}


def test_saude(cliente):
    assert cliente.get("/saude").status_code == 200


# ---------- autenticação ----------

@pytest.mark.parametrize("metodo,rota", ROTAS_PROTEGIDAS)
def test_sem_token_retorna_401(cliente, metodo, rota):
    assert getattr(cliente, metodo)(rota).status_code == 401, rota


@pytest.mark.parametrize("tipo", TIPOS_TOKEN_INVALIDO)
def test_token_invalido_retorna_401(cliente, contas, tipo):
    headers = {"Authorization": f"Bearer {token_invalido(tipo)}"}
    assert cliente.get("/ativos", headers=headers).status_code == 401


# ---------- permissões por perfil ----------

def test_solicitante_nao_cadastra_ativo(cliente, contas):
    r = cliente.post("/ativos", headers=contas["ana"]["headers"], json=novo_ativo(patrimonio="PAT-9", tipo="outro"))
    assert r.status_code == 403


def test_tecnico_cadastra_ativo(cliente, contas):
    r = cliente.post("/ativos", headers=contas["carla"]["headers"], json=novo_ativo())
    assert r.status_code == 201 and r.json()["patrimonio"] == "PAT-1"


def test_admin_cadastra_ativo(cliente, contas):
    r = cliente.post("/ativos", headers=contas["admin"]["headers"], json=novo_ativo(patrimonio="PAT-7"))
    assert r.status_code == 201


# ---------- regras ----------

def test_tecnico_cadastra_ativo_e_filtra_por_setor(cliente, contas):
    h = contas["carla"]["headers"]
    cliente.post("/ativos", headers=h, json=novo_ativo(patrimonio="PAT-1", tipo="impressora", descricao="HP", setor="RH"))
    cliente.post("/ativos", headers=h, json=novo_ativo(patrimonio="PAT-2", tipo="computador", descricao="Dell", setor="TI"))
    assert len(cliente.get("/ativos", params={"setor": "RH"}, headers=h).json()) == 1


def test_patrimonio_repetido_e_recusado(cliente, contas):
    h = contas["carla"]["headers"]
    assert cliente.post("/ativos", headers=h, json=novo_ativo()).status_code == 201
    assert cliente.post("/ativos", headers=h, json=novo_ativo()).status_code in (409, 422)


def test_consulta_ativo_por_id(cliente, contas):
    h = contas["carla"]["headers"]
    criado = cliente.post("/ativos", headers=h, json=novo_ativo()).json()
    r = cliente.get(f"/ativos/{criado['id']}", headers=h)
    assert r.status_code == 200 and r.json()["patrimonio"] == "PAT-1"


def test_ativo_inexistente(cliente, contas):
    assert cliente.get("/ativos/999", headers=contas["carla"]["headers"]).status_code == 404
