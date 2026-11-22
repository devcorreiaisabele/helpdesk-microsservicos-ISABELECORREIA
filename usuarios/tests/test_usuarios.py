"""Serviço usuarios: login, JWT, permissões por perfil e validação de entrada."""
import importlib

import pytest

from apoio_testes import SENHA, TIPOS_TOKEN_INVALIDO, modelo_usuario, sessao_banco, token_invalido

ROTAS_PROTEGIDAS = [("get", "/usuarios"), ("get", "/usuarios/1"), ("post", "/usuarios"), ("get", "/auth/eu")]


def test_saude(cliente):
    assert cliente.get("/saude").status_code == 200


# ---------- autenticação ----------

@pytest.mark.parametrize("metodo,rota", ROTAS_PROTEGIDAS)
def test_sem_token_retorna_401(cliente, metodo, rota):
    assert getattr(cliente, metodo)(rota).status_code == 401, rota


@pytest.mark.parametrize("tipo", TIPOS_TOKEN_INVALIDO)
def test_token_invalido_retorna_401(cliente, contas_login, tipo):
    headers = {"Authorization": f"Bearer {token_invalido(tipo)}"}
    assert cliente.get("/auth/eu", headers=headers).status_code == 401


def test_login_devolve_token_que_funciona(cliente, contas_login):
    r = cliente.post("/auth/login", json={"email": "ana@x.com", "senha": SENHA})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["access_token"] and corpo["usuario"]["email"] == "ana@x.com"
    assert "senha" not in corpo["usuario"] and "senha_hash" not in corpo["usuario"]
    eu = cliente.get("/auth/eu", headers={"Authorization": f"Bearer {corpo['access_token']}"})
    assert eu.status_code == 200 and eu.json()["id"] == corpo["usuario"]["id"]


def test_login_com_senha_errada(cliente, contas_login):
    r = cliente.post("/auth/login", json={"email": "ana@x.com", "senha": "errada123"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha inválidos."


def test_login_com_email_inexistente_tem_a_mesma_mensagem(cliente, contas_login):
    r = cliente.post("/auth/login", json={"email": "ninguem@x.com", "senha": "errada123"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha inválidos."


def test_bloqueio_apos_varias_senhas_erradas(cliente, contas_login):
    config = importlib.import_module("app.config")
    for _ in range(config.LOGIN_MAX_FALHAS):
        cliente.post("/auth/login", json={"email": "ana@x.com", "senha": "errada123"})
    # mesmo com a senha certa, fica bloqueado por um tempo
    assert cliente.post("/auth/login", json={"email": "ana@x.com", "senha": SENHA}).status_code == 429


def test_senha_guardada_com_hash(cliente, contas_login):
    Usuario = modelo_usuario()
    with sessao_banco() as db:
        u = db.query(Usuario).filter_by(email="ana@x.com").one()
        assert SENHA not in u.senha_hash and u.senha_hash.startswith("scrypt$")


# ---------- regras e permissões por perfil ----------

def test_admin_cria_usuario(cliente, contas_login):
    r = cliente.post("/usuarios", headers=contas_login["admin"]["headers"],
                     json={"nome": "Davi", "email": "davi@x.com", "perfil": "tecnico", "senha": "Forte1234"})
    assert r.status_code == 201
    assert "senha" not in r.json() and "senha_hash" not in r.json()


def test_solicitante_nao_cria_usuario(cliente, contas_login):
    r = cliente.post("/usuarios", headers=contas_login["ana"]["headers"],
                     json={"nome": "Eva", "email": "eva@x.com", "perfil": "admin", "senha": "Forte1234"})
    assert r.status_code == 403


def test_senha_fraca_e_recusada(cliente, contas_login):
    r = cliente.post("/usuarios", headers=contas_login["admin"]["headers"],
                     json={"nome": "Eva", "email": "eva@x.com", "perfil": "solicitante", "senha": "abcdefgh"})
    assert r.status_code == 422


def test_email_repetido_e_recusado(cliente, contas_login):
    dados = {"nome": "Ana 2", "email": "ANA@x.com", "perfil": "solicitante", "senha": "Forte1234"}
    assert cliente.post("/usuarios", headers=contas_login["admin"]["headers"], json=dados).status_code == 422


def test_usuario_inexistente(cliente, contas_login):
    assert cliente.get("/usuarios/99", headers=contas_login["ana"]["headers"]).status_code == 404


def test_lista_publica_nao_mostra_email(cliente, contas_login):
    lista = cliente.get("/usuarios", headers=contas_login["ana"]["headers"]).json()
    assert lista and all("email" not in u for u in lista)
