from functools import wraps
import json
from urllib.request import urlopen
import jwt
from fastapi import Request, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Callable, Any
import logging

from app.core.exceptions import AuthError
from app.core.config import settings

security = HTTPBearer()


def get_token_from_credentials(credentials: HTTPAuthorizationCredentials) -> str:
    """Extrae y valida el token de las credenciales HTTP Bearer"""
    if not credentials:
        raise AuthError(
            message="Authorization header is expected",
            details={"code": "authorization_header_missing"},
        )

    if credentials.scheme.lower() != "bearer":
        raise AuthError(
            message="Authorization header must start with Bearer",
            details={"code": "invalid_header"},
        )

    if not credentials.credentials:
        raise AuthError(message="Token not found", details={"code": "invalid_header"})

    return credentials.credentials


def verify_jwt_token(token: str) -> dict:
    """Verifica y decodifica el JWT token"""
    try:
        # Obtener las claves públicas de Auth0
        jsonurl = urlopen(f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json")
        jwks = json.loads(jsonurl.read())

        # Obtener el header no verificado para encontrar el kid
        unverified_header = jwt.get_unverified_header(token)

        # Buscar la clave pública correspondiente
        public_key = None
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

        if not public_key:
            raise AuthError(
                message="Unable to find appropriate key",
                details={"code": "invalid_header"},
            )

        # Decodificar y verificar el token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=settings.AUTH0_ALGORITHMS,
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise AuthError(message="Token is expired", details={"code": "token_expired"})
    except jwt.InvalidAudienceError:
        raise AuthError(
            message="Incorrect audience, please check the audience",
            details={"code": "invalid_audience"},
        )
    except jwt.InvalidIssuerError:
        raise AuthError(
            message="Incorrect issuer, please check the issuer",
            details={"code": "invalid_issuer"},
        )
    except jwt.InvalidTokenError:
        raise AuthError(
            message="Unable to parse authentication token",
            details={"code": "invalid_header"},
        )
    except Exception as e:
        raise AuthError(
            message="Unable to parse authentication token",
            details={"code": "invalid_header"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependency para obtener el usuario actual autenticado"""
    token = get_token_from_credentials(credentials)
    payload = verify_jwt_token(token)
    return payload
