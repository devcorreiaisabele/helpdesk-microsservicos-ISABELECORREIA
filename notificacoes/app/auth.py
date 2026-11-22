"""Validação do JWT emitido pelo serviço de usuários (HS256, iss=helpdesk-ti)."""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import JWT_ALGORITMO, JWT_EMISSOR, JWT_SEGREDO

_bearer = HTTPBearer(auto_error=False)


def usuario_atual(credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> int:
    """Devolve o id do usuário dono do token."""
    erro = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ausente ou inválido",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciais is None:
        raise erro
    try:
        dados = jwt.decode(
            credenciais.credentials,
            JWT_SEGREDO,
            algorithms=[JWT_ALGORITMO],
            issuer=JWT_EMISSOR,
        )
        return int(dados.get("sub") or dados["usuario_id"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise erro
