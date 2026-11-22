"""Serviço gateway: autenticação na borda, roteamento para os serviços e repasse de respostas.

Os serviços de trás são simulados por `servicos` (httpx interceptado); nada sai pela rede.
"""
import json

import httpx
import pytest

from apoio_testes import SENHA, TIPOS_TOKEN_INVALIDO, token_invalido

ROTAS_PROTEGIDAS = [("get", "/chamados"), ("get", "/usuarios"), ("get", "/ativos"), ("get", "/notificacoes"),
                    ("post", "/chamados"), ("get", "/auth/eu")]
ROTAS_E_SERVICOS = [("/chamados", "chamados"), ("/ativos", "inventario"), ("/usuarios", "usuarios"),
                    ("/notificacoes", "notificacoes")]


def test_saude(cliente):
    assert cliente.get("/saude").status_code == 200


# ---------- autenticação ----------

@pytest.mark.parametrize("metodo,rota", ROTAS_PROTEGIDAS)
def test_sem_token_retorna_401(cliente, metodo, rota):
    assert getattr(cliente, metodo)(rota).status_code == 401, rota


@pytest.mark.parametrize("tipo", TIPOS_TOKEN_INVALIDO)
@pytest.mark.parametrize("rota", ["/chamados", "/auth/eu"])
def test_token_invalido_retorna_401(cliente, contas, tipo, rota):
    headers = {"Authorization": f"Bearer {token_invalido(tipo)}"}
    assert cliente.get(rota, headers=headers).status_code == 401


def test_login_e_publico_e_vai_para_usuarios(cliente, servicos):
    r = cliente.post("/auth/login", json={"email": "ana@x.com", "senha": SENHA})
    assert r.status_code == 200 and r.json()["access_token"]
    assert servicos.servico_de(servicos.chamadas[-1]) == "usuarios"


def test_login_com_senha_errada_repassa_401(cliente):
    r = cliente.post("/auth/login", json={"email": "ana@x.com", "senha": "errada123"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha inválidos."


# ---------- roteamento ----------

@pytest.mark.parametrize("rota,servico", ROTAS_E_SERVICOS)
def test_rota_autenticada_e_encaminhada_ao_servico_certo(cliente, contas, servicos, rota, servico):
    r = cliente.get(rota, headers=contas["ana"]["headers"])
    assert r.status_code == 200
    chamada = servicos.chamadas[-1]
    assert servicos.servico_de(chamada) == servico
    assert chamada.url.path.rstrip("/").endswith(rota)


def test_authorization_e_repassado(cliente, contas, servicos):
    cliente.get("/chamados", headers=contas["ana"]["headers"])
    assert servicos.chamadas[-1].headers["authorization"] == contas["ana"]["headers"]["Authorization"]


def test_post_repassa_metodo_e_corpo(cliente, contas, servicos):
    dados = {"titulo": "Teste", "descricao": "Teste", "prioridade": "baixa", "ativo_id": 1}
    r = cliente.post("/chamados", headers=contas["ana"]["headers"], json=dados)
    assert r.status_code == 200
    chamada = servicos.chamadas[-1]
    assert chamada.method == "POST" and json.loads(chamada.content)["titulo"] == "Teste"


@pytest.mark.parametrize("status,detalhe", [(403, "Sem permissão."), (404, "Chamado não encontrado."),
                                            (422, "Dados inválidos.")])
def test_status_e_mensagem_do_servico_sao_repassados(cliente, contas, servicos, status, detalhe):
    servicos.regras.append(("GET", r"/chamados/42$", lambda req, m: httpx.Response(
        status, json={"detail": detalhe}, request=req)))
    r = cliente.get("/chamados/42", headers=contas["ana"]["headers"])
    assert r.status_code == status and r.json()["detail"] == detalhe


def test_permissao_negada_pelo_servico_chega_ao_cliente(cliente, contas, servicos):
    """A regra de perfil mora no serviço de trás; o gateway não pode transformá-la em sucesso."""
    servicos.regras.append(("POST", r"/usuarios$", lambda req, m: httpx.Response(
        403, json={"detail": "Sem permissão."}, request=req)))
    r = cliente.post("/usuarios", headers=contas["ana"]["headers"],
                     json={"nome": "Eva", "email": "eva@x.com", "perfil": "admin", "senha": "Forte1234"})
    assert r.status_code == 403


def test_servico_fora_do_ar(cliente, contas, servicos):
    servicos.fora_do_ar.add("chamados")
    r = cliente.get("/chamados", headers=contas["ana"]["headers"])
    assert r.status_code in (502, 503, 504)


def test_rota_inexistente(cliente, contas):
    assert cliente.get("/nao-existe", headers=contas["ana"]["headers"]).status_code in (401, 404)
