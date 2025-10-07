from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import logging

from app.core.exceptions import AuthError
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_token_from_credentials(credentials: HTTPAuthorizationCredentials) -> str:
    """Extracts and validates the token from HTTP Bearer credentials"""
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


# def verify_jwt_token(token: str) -> dict:
#     """
#     Verifies JWT token using HS256
#     Only checks that the token is valid - does not verify specific content
#     """
#     try:
#         # Decode and verify the token using HS256
#         payload = jwt.decode(
#             token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
#         )

#         logger.debug(f"Token verified successfully")
#         return payload

#     except jwt.ExpiredSignatureError:
#         logger.warning("Token expired")
#         raise AuthError(message="Token is expired", details={"code": "token_expired"})

#     except jwt.InvalidTokenError as e:
#         logger.warning(f"Invalid token: {str(e)}")
#         raise AuthError(message="Invalid token", details={"code": "invalid_token"})

#     except Exception as e:
#         logger.error(f"Token verification error: {str(e)}")
#         raise AuthError(
#             message="Unable to parse authentication token",
#             details={"code": "invalid_header"},
#         )


def verify_jwt_token(token: str) -> dict:
    """
    Verifies JWT token using HS256
    Only checks that the token is valid - does not verify specific content
    """
    try:
        # Log the token for debugging (remove in production)
        logger.debug(f"Attempting to verify token: {token[:20]}...{token[-20:]}")
        logger.debug(f"Token length: {len(token)}")

        # Decode and verify the token using HS256
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
            leeway=10,
        )

        logger.debug(f"Token verified successfully")
        return payload

    except jwt.ImmatureSignatureError:
        logger.warning("Token issued in the future (iat claim)")
        raise AuthError(
            message="Token not yet valid", details={"code": "token_not_yet_valid"}
        )

    except jwt.InvalidSignatureError:
        logger.warning("Invalid token signature")
        raise AuthError(
            message="Invalid token signature", details={"code": "invalid_signature"}
        )

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise AuthError(message="Token is expired", details={"code": "token_expired"})

    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        logger.warning(f"Token causing error: {token}")  # Log full token for debugging
        raise AuthError(message="Invalid token", details={"code": "invalid_token"})

    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise AuthError(
            message="Unable to parse authentication token",
            details={"code": "invalid_header"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Dependency to get the currently authenticated user

    Returns:
        dict: Payload of the verified JWT token
    """
    token = get_token_from_credentials(credentials)
    payload = verify_jwt_token(token)
    return payload
