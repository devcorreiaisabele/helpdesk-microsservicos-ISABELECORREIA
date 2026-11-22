"""Validação do token JWT emitido pelo serviço de autenticação.

Claims esperadas: iss='helpdesk-ti', sub=<usuario_id>, perfil.
O serviço não consulta o banco de usuários: confia na assinatura do token.
"""
from dataclasses import dataclass

import jwt
from fastapi import Header

from app import config
from app.erros import NaoAutenticado


@dataclass(frozen=True)
class Usuario:
    id: int
    perfil: str
    autorizacao: str  # cabeçalho Authorization original, repassado aos outros serviços


def usuario_atual(authorization: str | None = Header(default=None)) -> Usuario:
    if not authorization or authorization[:7].lower() != "bearer ":
        raise NaoAutenticado("Token de autenticação ausente.")
    token = authorization[7:].strip()
    try:
        dados = jwt.decode(
            token,
            config.JWT_SEGREDO,
            algorithms=[config.JWT_ALGORITMO],
            issuer=config.JWT_EMISSOR,
            options={"require": ["sub", "iss"]},
        )
        usuario_id = int(dados["sub"])
        perfil = dados["perfil"]
        if not isinstance(perfil, str):
            raise ValueError("perfil inválido")
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise NaoAutenticado("Token inválido ou expirado.")
    return Usuario(id=usuario_id, perfil=perfil, autorizacao=authorization)
