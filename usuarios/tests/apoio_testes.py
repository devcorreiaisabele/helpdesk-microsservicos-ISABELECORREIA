"""Apoio dos testes do serviço usuarios (gerado por criar_testes.py).

Tudo roda sem rede: Redis falso em memória, httpx simulado e JWT de teste.
"""
import asyncio
import fnmatch
import importlib
import json
import queue
import re
import sys
import threading
import time
import types
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest

RAIZ_SERVICO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICO))

SERVICO = "usuarios"
SENHA = "Senha123"
JWT_SEGREDO_TESTE = "segredo-de-teste-com-mais-de-32-caracteres-0123456789"

# ===================================== AJUSTE AQUI ==========================================
MODULO_APP = "app.main"  # módulo que expõe a variável `app` (FastAPI)

# O banco temporário é entregue ao serviço por todas estas variáveis (as que ele não usa são ignoradas).
VARS_BANCO_URL = ["DATABASE_URL", "BANCO_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL"]
VARS_BANCO_ARQUIVO = ["DATABASE_PATH", "DB_PATH", "BANCO_PATH", "SQLITE_PATH", "DB_FILE"]

# URLs dos outros serviços (as chamadas httpx para elas são interceptadas, nunca saem pela rede)
URLS_SERVICOS = {
    "USUARIOS_URL": "http://usuarios:8001",
    "INVENTARIO_URL": "http://inventario:8002",
    "CHAMADOS_URL": "http://chamados:8003",
    "NOTIFICACOES_URL": "http://notificacoes:8004",
}

# Onde ficam serviço/esquemas/modelos/banco de usuários (usados só pelo serviço `usuarios`)
CANDIDATOS_SERVICO_USUARIOS = ["app.usuarios.servico", "app.servico"]
CANDIDATOS_ESQUEMAS_USUARIOS = ["app.usuarios.esquemas", "app.esquemas"]
CANDIDATOS_MODELOS_USUARIOS = ["app.usuarios.modelos", "app.modelos"]
CANDIDATOS_DATABASE = ["app.database", "app.db", "app.banco"]

# Rota -> serviço dono dela (usado pelo httpx simulado para saber quem "respondeu")
PREFIXOS_ROTAS = {"auth": "usuarios", "usuarios": "usuarios", "ativos": "inventario",
                  "chamados": "chamados", "notificacoes": "notificacoes"}
# =============================================================================================

CONTAS = {
    "admin": {"id": 1, "nome": "Admin", "email": "admin@x.com", "perfil": "admin"},
    "ana": {"id": 2, "nome": "Ana", "email": "ana@x.com", "perfil": "solicitante"},
    "bia": {"id": 3, "nome": "Bia", "email": "bia@x.com", "perfil": "solicitante"},
    "carla": {"id": 4, "nome": "Carla", "email": "carla@x.com", "perfil": "tecnico"},
}


# ---------------------------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------------------------
def _config():
    return sys.modules.get("app.config")


def segredo_jwt():
    return getattr(_config(), "JWT_SEGREDO", None) or JWT_SEGREDO_TESTE


def emissor_jwt():
    return getattr(_config(), "JWT_EMISSOR", None) or "helpdesk-ti"


def gerar_token(usuario_id, perfil, expira_em=timedelta(hours=1), segredo=None, **extras):
    agora = datetime.now(timezone.utc)
    emitido = agora if expira_em.total_seconds() > 0 else agora + expira_em - timedelta(minutes=5)
    conta = next((c for c in CONTAS.values() if c["id"] == usuario_id), {})
    payload = {"sub": str(usuario_id), "perfil": perfil, "nome": conta.get("nome", "Teste"),
               "email": conta.get("email", "teste@x.com"), "iss": emissor_jwt(),
               "iat": emitido, "exp": agora + expira_em, **extras}
    return jwt.encode(payload, segredo or segredo_jwt(), algorithm="HS256")


TIPOS_TOKEN_INVALIDO = ["adulterado", "outro_segredo", "alg_none", "expirado", "lixo"]


def token_invalido(tipo, usuario_id=2, perfil="solicitante"):
    if tipo == "adulterado":
        return gerar_token(usuario_id, perfil) + "x"
    if tipo == "outro_segredo":
        return gerar_token(usuario_id, perfil, segredo="segredo-de-outra-pessoa-com-mais-de-32-caracteres")
    if tipo == "alg_none":
        agora = datetime.now(timezone.utc)
        return jwt.encode({"sub": str(usuario_id), "perfil": perfil, "iss": emissor_jwt(), "iat": agora,
                           "exp": agora + timedelta(hours=1)}, None, algorithm="none")
    if tipo == "expirado":
        return gerar_token(usuario_id, perfil, expira_em=timedelta(hours=-2))
    return "isto-nao-e-um-jwt"


# ---------------------------------------------------------------------------------------------
# Redis falso (sync + async)
# ---------------------------------------------------------------------------------------------
class Texto(str):
    """str que também aceita .decode(), como os bytes devolvidos pelo Redis real."""

    def decode(self, *args, **kwargs):
        return str(self)


def _saida(valor):
    if isinstance(valor, bytes):
        return Texto(valor.decode())
    if isinstance(valor, str):
        return Texto(valor)
    if isinstance(valor, dict):
        return {_saida(k): _saida(v) for k, v in valor.items()}
    return valor


def _texto(valor):
    if isinstance(valor, bytes):
        return valor.decode(errors="replace")
    if isinstance(valor, (dict, list, tuple)):
        try:
            return json.dumps(valor, default=str, ensure_ascii=False)
        except TypeError:
            return str(valor)
    return str(valor)


class RedisFalso:
    """Redis em memória: chaves, listas, streams e pub/sub. Um único estado por teste."""

    _atual = None

    def __new__(cls, *args, **kwargs):
        if RedisFalso._atual is None:
            instancia = super().__new__(cls)
            instancia._iniciar()
            RedisFalso._atual = instancia
        return RedisFalso._atual

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    @classmethod
    def reiniciar(cls):
        RedisFalso._atual = None

    def _iniciar(self):
        self.trava = threading.RLock()
        self.chaves = {}
        self.listas = {}
        self.streams = {}
        self.assinantes = []
        self.eventos = []  # tudo que foi publicado, como texto (para os asserts)
        self.consome = {"canais": set(), "streams": set(), "listas": set()}
        self._seq = 0
        self._entregues = {}

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        return lambda *args, **kwargs: None  # comando não simulado: não faz nada

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _registrar(self, *partes):
        self.eventos.append(" ".join(_texto(p) for p in partes))

    def _aguardar(self, tentar, espera, sem_bloqueio=False):
        # espera: None = não bloqueia; 0 = "para sempre" (limitado a 0,2 s); > 0 = segundos (limitado a 0,2 s)
        limite = time.monotonic() + (0 if espera is None else min(espera or 0.2, 0.2))
        while True:
            with self.trava:
                resultado = tentar()
            if resultado is not None:
                return resultado
            if sem_bloqueio or time.monotonic() >= limite:
                if espera is None and not sem_bloqueio:
                    time.sleep(0.005)
                return None
            time.sleep(0.01)

    # --- chaves simples
    def ping(self, *args, **kwargs):
        return True

    def close(self, *args, **kwargs):
        return None

    def get(self, chave):
        return _saida(self.chaves.get(_texto(chave)))

    def set(self, chave, valor, *args, **kwargs):
        self.chaves[_texto(chave)] = valor
        return True

    def setex(self, chave, tempo, valor):
        return self.set(chave, valor)

    def delete(self, *chaves):
        return sum(1 for c in chaves if self.chaves.pop(_texto(c), None) is not None)

    def exists(self, *chaves):
        return sum(1 for c in chaves if _texto(c) in self.chaves)

    def incr(self, chave, quantidade=1):
        novo = int(self.chaves.get(_texto(chave), 0)) + quantidade
        self.chaves[_texto(chave)] = novo
        return novo

    def expire(self, *args, **kwargs):
        return True

    # --- pub/sub
    def publish(self, canal, mensagem):
        with self.trava:
            nome = _texto(canal)
            self._registrar("publish", nome, mensagem)
            entregues = 0
            for assinante in list(self.assinantes):
                if assinante._quer(nome):
                    assinante._receber(nome, mensagem)
                    entregues += 1
            return entregues

    def pubsub(self, **kwargs):
        return PubSubFalso(self)

    # --- listas
    def lpush(self, nome, *valores):
        with self.trava:
            self._registrar("lpush", nome, *valores)
            lista = self.listas.setdefault(_texto(nome), [])
            for valor in valores:
                lista.insert(0, valor)
            return len(lista)

    def rpush(self, nome, *valores):
        with self.trava:
            self._registrar("rpush", nome, *valores)
            lista = self.listas.setdefault(_texto(nome), [])
            lista.extend(valores)
            return len(lista)

    def _pegar_da_lista(self, nomes, fim):
        for nome in nomes:
            lista = self.listas.get(_texto(nome))
            if lista:
                valor = lista.pop() if fim == "direita" else lista.pop(0)
                return (_saida(nome), _saida(valor))
        return None

    def brpop(self, keys, timeout=0, _sem_bloqueio=False):
        nomes = [keys] if isinstance(keys, (str, bytes)) else list(keys)
        self.consome["listas"].update(_texto(n) for n in nomes)
        return self._aguardar(lambda: self._pegar_da_lista(nomes, "direita"), timeout, _sem_bloqueio)

    def blpop(self, keys, timeout=0, _sem_bloqueio=False):
        nomes = [keys] if isinstance(keys, (str, bytes)) else list(keys)
        self.consome["listas"].update(_texto(n) for n in nomes)
        return self._aguardar(lambda: self._pegar_da_lista(nomes, "esquerda"), timeout, _sem_bloqueio)

    def rpop(self, nome, *args, **kwargs):
        with self.trava:
            lista = self.listas.get(_texto(nome))
            return _saida(lista.pop()) if lista else None

    def lpop(self, nome, *args, **kwargs):
        with self.trava:
            lista = self.listas.get(_texto(nome))
            return _saida(lista.pop(0)) if lista else None

    def llen(self, nome):
        return len(self.listas.get(_texto(nome), []))

    def lrange(self, nome, inicio, fim):
        lista = self.listas.get(_texto(nome), [])
        return [_saida(v) for v in lista[inicio: None if fim == -1 else fim + 1]]

    # --- streams
    def xadd(self, nome, campos, id="*", *args, **kwargs):
        with self.trava:
            self._seq += 1
            novo = f"{self._seq}-0"
            self.streams.setdefault(_texto(nome), []).append((novo, dict(campos)))
            self._registrar("xadd", nome, campos)
            return Texto(novo)

    def xlen(self, nome):
        return len(self.streams.get(_texto(nome), []))

    def xgroup_create(self, name, groupname, id="$", mkstream=False, *args, **kwargs):
        self.streams.setdefault(_texto(name), [])
        self.consome["streams"].add(_texto(name))
        return True

    def xack(self, *args, **kwargs):
        return 1

    def _ler_stream(self, grupo, streams, count):
        saida = []
        for nome, id_ in streams.items():
            chave = _texto(nome)
            self.consome["streams"].add(chave)
            minimo = self._entregues.get((chave, grupo), 0)
            if str(id_) not in ("$", ">", "0", "0-0"):
                try:
                    minimo = max(minimo, int(str(id_).split("-")[0]))
                except ValueError:
                    pass
            novas = [(i, c) for i, c in self.streams.get(chave, []) if int(i.split("-")[0]) > minimo]
            if count:
                novas = novas[:count]
            if novas:
                self._entregues[(chave, grupo)] = int(novas[-1][0].split("-")[0])
                saida.append((_saida(chave), [(Texto(i), _saida(c)) for i, c in novas]))
        return saida or None

    def xread(self, streams, count=None, block=None, _sem_bloqueio=False):
        espera = None if block is None else block / 1000
        return self._aguardar(lambda: self._ler_stream(None, streams, count), espera, _sem_bloqueio) or []

    def xreadgroup(self, groupname, consumername, streams, count=None, block=None, noack=False,
                   _sem_bloqueio=False):
        espera = None if block is None else block / 1000
        return self._aguardar(lambda: self._ler_stream(_texto(groupname), streams, count), espera,
                              _sem_bloqueio) or []


class PubSubFalso:
    def __init__(self, redis_falso, *args, **kwargs):
        self._r = redis_falso
        self._fila = queue.Queue()
        self._canais = {}
        self._padroes = {}
        self._fechado = False
        with redis_falso.trava:
            redis_falso.assinantes.append(self)

    def subscribe(self, *canais, **tratadores):
        for canal in list(canais) + list(tratadores):
            nome = _texto(canal)
            self._canais[nome] = tratadores.get(canal)
            self._r.consome["canais"].add(nome)
            self._fila.put({"type": "subscribe", "pattern": None, "channel": Texto(nome),
                            "data": len(self._canais)})

    def psubscribe(self, *padroes, **tratadores):
        for padrao in list(padroes) + list(tratadores):
            nome = _texto(padrao)
            self._padroes[nome] = tratadores.get(padrao)
            self._r.consome["canais"].add(nome)
            self._fila.put({"type": "psubscribe", "pattern": None, "channel": Texto(nome),
                            "data": len(self._padroes)})

    def unsubscribe(self, *canais):
        for canal in (canais or list(self._canais)):
            self._canais.pop(_texto(canal), None)

    def punsubscribe(self, *padroes):
        for padrao in (padroes or list(self._padroes)):
            self._padroes.pop(_texto(padrao), None)

    def _quer(self, canal):
        return canal in self._canais or any(fnmatch.fnmatch(canal, p) for p in self._padroes)

    def _receber(self, canal, dado):
        tipo = "message" if canal in self._canais else "pmessage"
        self._fila.put({"type": tipo, "pattern": None, "channel": Texto(canal), "data": _saida(dado)})

    def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        try:
            msg = self._fila.get(timeout=min(timeout or 0.0, 0.2))
        except queue.Empty:
            if not timeout:
                time.sleep(0.005)
            return None
        if msg["type"] in ("subscribe", "psubscribe") and ignore_subscribe_messages:
            return None
        canal = str(msg["channel"])
        tratador = self._canais.get(canal) or next(
            (t for p, t in self._padroes.items() if t and fnmatch.fnmatch(canal, p)), None)
        if tratador and msg["type"] in ("message", "pmessage"):
            tratador(msg)
            return None
        return msg

    def listen(self):
        while not self._fechado:
            msg = self.get_message(timeout=0.1)
            if msg is not None:
                yield msg

    def run_in_thread(self, sleep_time=0.0, daemon=True, *args, **kwargs):
        parar = threading.Event()

        def laco():
            while not parar.is_set() and not self._fechado:
                self.get_message(timeout=0.05)

        fio = threading.Thread(target=laco, daemon=True)
        fio.start()
        fio.stop = parar.set
        return fio

    def close(self):
        self._fechado = True
        with self._r.trava:
            if self in self._r.assinantes:
                self._r.assinantes.remove(self)

    reset = close

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PubSubFalsoAsync:
    def __init__(self, redis_falso, *args, **kwargs):
        self._p = PubSubFalso(redis_falso)

    async def subscribe(self, *canais, **tratadores):
        return self._p.subscribe(*canais, **tratadores)

    async def psubscribe(self, *padroes, **tratadores):
        return self._p.psubscribe(*padroes, **tratadores)

    async def unsubscribe(self, *canais):
        return self._p.unsubscribe(*canais)

    async def close(self):
        return self._p.close()

    aclose = close

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        fim = time.monotonic() + min(timeout or 0.0, 0.2)
        while True:
            msg = self._p.get_message(ignore_subscribe_messages=ignore_subscribe_messages, timeout=0)
            if msg is not None or time.monotonic() >= fim:
                return msg
            await asyncio.sleep(0.01)

    async def listen(self):
        while not self._p._fechado:
            msg = await self.get_message(timeout=0.1)
            if msg is not None:
                yield msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._p.close()


class RedisFalsoAsync:
    """Mesma coisa que RedisFalso, mas com métodos `async` (redis.asyncio)."""

    BLOQUEANTES = {"brpop", "blpop", "xread", "xreadgroup"}

    def __init__(self, *args, **kwargs):
        self._r = RedisFalso()

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def pubsub(self, **kwargs):
        return PubSubFalsoAsync(self._r)

    async def aclose(self):
        return None

    async def close(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __getattr__(self, nome):
        if nome.startswith("_"):
            raise AttributeError(nome)
        alvo = getattr(self._r, nome)
        if not callable(alvo):
            return alvo

        async def chamar(*args, **kwargs):
            if nome in self.BLOQUEANTES:
                kwargs["_sem_bloqueio"] = True
                resultado = alvo(*args, **kwargs)
                if not resultado:
                    await asyncio.sleep(0.05)
                return resultado
            return alvo(*args, **kwargs)

        return chamar


def instalar_redis(monkeypatch):
    """Troca o cliente Redis (sync e asyncio) pelo falso. Deve rodar ANTES de importar o app."""
    RedisFalso.reiniciar()
    try:
        import redis
        import redis.asyncio as redis_async
    except ImportError:
        redis = types.ModuleType("redis")
        redis_async = types.ModuleType("redis.asyncio")
        excecoes = types.ModuleType("redis.exceptions")

        class RedisError(Exception):
            pass

        excecoes.RedisError = excecoes.ConnectionError = excecoes.TimeoutError = RedisError
        redis.RedisError = redis.ConnectionError = redis.TimeoutError = RedisError
        redis.exceptions, redis.asyncio = excecoes, redis_async
        for nome, modulo in (("redis", redis), ("redis.asyncio", redis_async), ("redis.exceptions", excecoes)):
            monkeypatch.setitem(sys.modules, nome, modulo)
    for modulo, classe in ((redis, RedisFalso), (redis_async, RedisFalsoAsync)):
        for atributo in ("Redis", "StrictRedis", "ConnectionPool"):
            monkeypatch.setattr(modulo, atributo, classe, raising=False)
        monkeypatch.setattr(modulo, "from_url", classe.from_url, raising=False)
    return RedisFalso()


# ---------------------------------------------------------------------------------------------
# httpx simulado: responde no lugar dos outros serviços
# ---------------------------------------------------------------------------------------------
def _corpo_json(request):
    try:
        return json.loads(request.content or b"{}")
    except (ValueError, httpx.RequestNotRead):
        return {}


class ServicosFalsos:
    """Faz o papel de usuarios/inventario/chamados/notificacoes quando o serviço testado os chama.

    * Todas as rotas (exceto /saude e /auth/login) exigem um JWT válido: sem ele, 401 (como os serviços reais).
    * GET /ativos/{id} e GET /usuarios/{id} consultam os dicionários `ativos` e `usuarios`.
    * `regras` permite a um teste forçar uma resposta: (metodo, regex_do_caminho, funcao(request, match)).
    * `fora_do_ar` guarda nomes de serviços que devem falhar com httpx.ConnectError.
    """

    def __init__(self):
        self.chamadas = []
        self.ativos = {1: {"id": 1, "patrimonio": "PAT-1", "tipo": "computador",
                           "descricao": "Desktop", "setor": "TI"}}
        self.usuarios = {c["id"]: {**c, "ativo": True} for c in CONTAS.values()}
        self.fora_do_ar = set()
        self.regras = []

    def servico_de(self, request):
        partes = [p for p in request.url.path.split("/") if p]
        if partes and partes[0] == "api":
            partes = partes[1:]
        return PREFIXOS_ROTAS.get(partes[0] if partes else "", "desconhecido")

    @staticmethod
    def _json(request, status, dados):
        return httpx.Response(status, json=dados, request=request)

    def _usuario_do_token(self, request):
        autorizacao = request.headers.get("authorization", "")
        if not autorizacao.lower().startswith("bearer "):
            return None
        try:
            dados = jwt.decode(autorizacao[7:].strip(), segredo_jwt(), algorithms=["HS256"],
                               options={"verify_aud": False, "verify_iss": False})
            return self.usuarios.get(int(dados.get("sub")))
        except (jwt.PyJWTError, ValueError, TypeError):
            return None

    def _login(self, request):
        corpo = _corpo_json(request)
        for conta in self.usuarios.values():
            if conta["email"] == str(corpo.get("email", "")).lower() and corpo.get("senha") == SENHA:
                token = gerar_token(conta["id"], conta["perfil"])
                return self._json(request, 200, {"access_token": token, "token_type": "bearer", "usuario": conta})
        return self._json(request, 401, {"detail": "E-mail ou senha inválidos."})

    def tratar(self, request):
        self.chamadas.append(request)
        nome = self.servico_de(request)
        if nome in self.fora_do_ar:
            raise httpx.ConnectError("Serviço fora do ar (simulado).", request=request)
        caminho = request.url.path.rstrip("/") or "/"
        for metodo, padrao, funcao in self.regras:
            achou = re.search(padrao, caminho)
            if achou and metodo == request.method:
                return funcao(request, achou)
        publico = caminho.endswith("/saude") or caminho.endswith("/auth/login")
        usuario = self._usuario_do_token(request)
        if not publico and usuario is None:
            return self._json(request, 401, {"detail": "Token ausente ou inválido."})
        if caminho.endswith("/saude"):
            return self._json(request, 200, {"status": "ok", "servico": nome})
        if caminho.endswith("/auth/login") and request.method == "POST":
            return self._login(request)
        if caminho.endswith("/auth/eu"):
            return self._json(request, 200, usuario)
        if request.method == "GET":
            achou = re.search(r"/ativos/(\d+)$", caminho)
            if achou:
                ativo = self.ativos.get(int(achou.group(1)))
                return self._json(request, 200, ativo) if ativo else \
                    self._json(request, 404, {"detail": "Ativo não encontrado."})
            achou = re.search(r"/usuarios/(\d+)$", caminho)
            if achou:
                dono = self.usuarios.get(int(achou.group(1)))
                return self._json(request, 200, dono) if dono else \
                    self._json(request, 404, {"detail": "Usuário não encontrado."})
        return self._json(request, 200, {"servico": nome, "metodo": request.method, "caminho": caminho,
                                         "usuario_id": usuario["id"] if usuario else None})


def instalar_httpx(monkeypatch, servicos):
    """Intercepta httpx.Client/AsyncClient. As chamadas do TestClient (host 'testserver') passam normalmente."""
    enviar_sync = httpx.Client.send
    enviar_async = httpx.AsyncClient.send

    def send(self, request, *args, **kwargs):
        if request.url.host == "testserver":
            return enviar_sync(self, request, *args, **kwargs)
        return servicos.tratar(request)

    async def send_async(self, request, *args, **kwargs):
        if request.url.host == "testserver":
            return await enviar_async(self, request, *args, **kwargs)
        return servicos.tratar(request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", send_async)


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------
def limpar_modulos_app():
    for nome in list(sys.modules):
        if nome == "app" or nome.startswith("app."):
            del sys.modules[nome]


def esperar_ate(condicao, espera=5.0):
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        valor = condicao()
        if valor:
            return valor
        time.sleep(0.05)
    return condicao()


def entregar_evento(redis, evento, espera=5.0):
    """Entrega um evento ao consumidor do serviço, pelo mesmo canal/stream/lista que ele escuta."""
    esperar_ate(lambda: any(redis.consome.values()), espera)
    if not any(redis.consome.values()):
        pytest.fail("O serviço não começou a consumir o Redis (esperava subscribe/xread/xreadgroup/brpop).")
    corpo = json.dumps(evento)
    for canal in list(redis.consome["canais"]):
        redis.publish(canal, corpo)
    for stream in list(redis.consome["streams"]):
        redis.xadd(stream, {**{k: str(v) for k, v in evento.items()}, "dados": corpo, "payload": corpo})
    for lista in list(redis.consome["listas"]):
        redis.lpush(lista, corpo)


def _primeiro_modulo(candidatos):
    erros = []
    for nome in candidatos:
        try:
            return importlib.import_module(nome)
        except ImportError as erro:
            erros.append(f"{nome}: {erro}")
    pytest.fail("Nenhum destes módulos pôde ser importado - ajuste os CANDIDATOS_* em apoio_testes.py: "
                + "; ".join(erros))


@contextmanager
def sessao_banco():
    database = _primeiro_modulo(CANDIDATOS_DATABASE)
    gerador = database.get_db()
    db = next(gerador)
    try:
        yield db
    finally:
        gerador.close()


def modelo_usuario():
    return _primeiro_modulo(CANDIDATOS_MODELOS_USUARIOS).Usuario


def criar_usuario_direto(nome, email, perfil, senha=SENHA):
    """Cria um usuário pela camada de serviço (como o conftest do monolito fazia)."""
    servico = _primeiro_modulo(CANDIDATOS_SERVICO_USUARIOS)
    esquemas = _primeiro_modulo(CANDIDATOS_ESQUEMAS_USUARIOS)
    with sessao_banco() as db:
        return servico.criar(db, esquemas.UsuarioCriar(nome=nome, email=email, perfil=perfil, senha=senha))
