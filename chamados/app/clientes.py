"""Clientes HTTP para os outros serviços (Usuários e Inventário).

O cabeçalho `Authorization` recebido do cliente é repassado como está.
Timeout de 3s; falhas de rede viram HTTP 503 com mensagem clara.
"""
import httpx

from app import config
from app.erros import NaoEncontrado, ServicoIndisponivel


def _get(url: str, autorizacao: str, servico: str) -> httpx.Response:
    try:
        return httpx.get(url, headers={"Authorization": autorizacao}, timeout=config.TIMEOUT_HTTP)
    except httpx.TimeoutException:
        raise ServicoIndisponivel(
            f"O serviço de {servico} não respondeu em {config.TIMEOUT_HTTP:g}s. Tente novamente em instantes."
        )
    except httpx.RequestError:
        raise ServicoIndisponivel(
            f"Não foi possível conectar ao serviço de {servico}. Tente novamente em instantes."
        )


def obter_ativo(ativo_id: int, autorizacao: str) -> dict:
    resp = _get(f"{config.INVENTARIO_URL}/ativos/{ativo_id}", autorizacao, "inventário")
    if resp.status_code == 404:
        raise NaoEncontrado(f"Ativo {ativo_id} não encontrado.")
    if resp.status_code != 200:
        raise ServicoIndisponivel(
            f"O serviço de inventário respondeu com erro inesperado (HTTP {resp.status_code})."
        )
    return resp.json()


def obter_usuario(usuario_id: int, autorizacao: str) -> dict:
    resp = _get(f"{config.USUARIOS_URL}/usuarios/{usuario_id}", autorizacao, "usuários")
    if resp.status_code == 404:
        raise NaoEncontrado(f"Usuário {usuario_id} não encontrado.")
    if resp.status_code != 200:
        raise ServicoIndisponivel(
            f"O serviço de usuários respondeu com erro inesperado (HTTP {resp.status_code})."
        )
    return resp.json()
