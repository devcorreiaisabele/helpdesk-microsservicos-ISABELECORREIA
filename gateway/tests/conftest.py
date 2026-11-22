"""Fixtures do serviço gateway (gerado por criar_testes.py)."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apoio_testes as ap  # noqa: E402


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Banco SQLite temporário + JWT_SEGREDO de teste + URLs dos outros serviços."""
    banco = tmp_path / "teste.db"
    for var in ap.VARS_BANCO_URL:
        monkeypatch.setenv(var, f"sqlite:///{banco.as_posix()}")
    for var in ap.VARS_BANCO_ARQUIVO:
        monkeypatch.setenv(var, str(banco))
    monkeypatch.setenv("JWT_SEGREDO", ap.JWT_SEGREDO_TESTE)
    monkeypatch.setenv("DADOS_EXEMPLO", "0")
    monkeypatch.setenv("REDIS_URL", "redis://redis-falso:6379/0")
    for var, valor in ap.URLS_SERVICOS.items():
        monkeypatch.setenv(var, valor)
    return tmp_path


@pytest.fixture
def redis_falso(monkeypatch):
    return ap.instalar_redis(monkeypatch)


@pytest.fixture
def servicos(monkeypatch):
    falsos = ap.ServicosFalsos()
    ap.instalar_httpx(monkeypatch, falsos)
    return falsos


@pytest.fixture
def app_modulo(ambiente, redis_falso, servicos):
    """Importa o app DEPOIS de ambiente/Redis/httpx estarem trocados (estado limpo a cada teste)."""
    ap.limpar_modulos_app()
    modulo = importlib.import_module(ap.MODULO_APP)
    yield modulo
    ap.limpar_modulos_app()


@pytest.fixture
def cliente(app_modulo):
    with TestClient(app_modulo.app) as c:
        yield c


@pytest.fixture
def contas(app_modulo):
    """Tokens JWT de teste (admin, ana/bia = solicitantes, carla = técnica), assinados com o segredo de teste."""
    return {apelido: {"headers": {"Authorization": f"Bearer {ap.gerar_token(c['id'], c['perfil'])}"},
                      "id": c["id"], "perfil": c["perfil"]}
            for apelido, c in ap.CONTAS.items()}


@pytest.fixture
def contas_login(cliente):
    """Só para o serviço `usuarios`: cria os 4 usuários no banco e faz login de verdade."""
    for c in ap.CONTAS.values():
        ap.criar_usuario_direto(c["nome"], c["email"], c["perfil"], ap.SENHA)
    resultado = {}
    for apelido, c in ap.CONTAS.items():
        r = cliente.post("/auth/login", json={"email": c["email"], "senha": ap.SENHA})
        assert r.status_code == 200, r.text
        dados = r.json()
        resultado[apelido] = {"headers": {"Authorization": f"Bearer {dados['access_token']}"},
                              "id": dados["usuario"]["id"], "perfil": c["perfil"]}
    return resultado
