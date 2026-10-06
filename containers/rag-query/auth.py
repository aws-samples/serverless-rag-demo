"""Cognito ID token verification for the RAG query WebSocket.

The WebSocket is reached with SigV4-signed Identity Pool credentials, which
identify the shared authenticated role rather than the person using it. So to
scope retrieval to one user we need the Cognito ID token itself, and we have to
verify it here: a plain `user_email` field in the message body is a claim the
caller makes about themselves, not evidence.
"""

import logging
import os

import jwt

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# PyJWKClient caches the signing keys, so this is one network call per key id.
_jwks_client = jwt.PyJWKClient(JWKS_URL, cache_keys=True) if USER_POOL_ID else None


class AuthError(Exception):
    """The caller did not prove who they are."""


def verify_id_token(token: str) -> dict:
    """Return the verified claims of a Cognito ID token, or raise AuthError.

    Checks the RS256 signature against the User Pool's published keys plus
    expiry, audience and issuer. Also requires token_use == "id", because an
    access token for the same pool would otherwise satisfy the signature check
    while carrying no email claim.
    """
    if _jwks_client is None:
        raise AuthError("COGNITO_USER_POOL_ID is not configured")
    if not CLIENT_ID:
        raise AuthError("COGNITO_CLIENT_ID is not configured")
    if not token:
        raise AuthError("No id_token supplied")

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except Exception as exc:
        # The reason is useful in logs but must not go back to the caller.
        logger.warning("ID token rejected: %s", exc)
        raise AuthError("Invalid or expired id_token") from exc

    if claims.get("token_use") != "id":
        raise AuthError("Not an ID token")

    return claims


def verified_email(token: str) -> str:
    """Return the verified email address of the caller."""
    claims = verify_id_token(token)

    email = claims.get("email")
    if not email:
        raise AuthError("ID token carries no email claim")
    if claims.get("email_verified") not in (True, "true", "True"):
        raise AuthError("Email address is not verified")

    return email
