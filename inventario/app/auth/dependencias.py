"""Dependências de autenticação/autorização.

O token é validado apenas com o segredo compartilhado (JWT_SEGREDO);
este serviço nunca consulta o banco de usuários.
"""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import JWT_ALGORITMO, JWT_EMISSOR, jwt_segredo

_esquema = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UsuarioToken:
    id: str
    perfil: str


def _nao_autenticado(detalhe: str = "Token ausente ou inválido.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalhe,
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_esquema),
) -> UsuarioToken:
    if credenciais is None:
        raise _nao_autenticado()
    try:
        claims = jwt.decode(
            credenciais.credentials,
            jwt_segredo(),
            algorithms=[JWT_ALGORITMO],  # algoritmo fixo: evita confusão de algoritmos
            issuer=JWT_EMISSOR,
            options={"require": ["sub", "iss"]},
        )
    except jwt.InvalidTokenError:
        raise _nao_autenticado() from None
    return UsuarioToken(id=str(claims["sub"]), perfil=str(claims.get("perfil", "")))


def exigir_perfil(*perfis: str):
    """Fábrica de dependência que exige um dos perfis informados."""

    def _verificar(usuario: UsuarioToken = Depends(usuario_atual)) -> UsuarioToken:
        if usuario.perfil not in perfis:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil sem permissão.")
        return usuario

    return _verificar
