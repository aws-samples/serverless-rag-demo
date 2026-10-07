"""Cognito ID token verification for the AgentCore WebSocket handlers.

The WebSocket is reached with SigV4-signed Identity Pool credentials, which
identify the shared authenticated role rather than the person using it. So to
scope retrieval to one user we need the Cognito ID token itself, and we have to
verify it here: a plain `user_email` field in the message body is a claim the
caller makes about themselves, not evidence.

This file is deliberately identical in containers/rag-query and
containers/multi-agent — each Dockerfile builds from its own directory, so a
shared module would mean two build contexts for no security gain. A test asserts
the two copies have not drifted.
"""

import logging
import os
from dataclasses import dataclass

import jwt

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")

# Membership of this Cognito group is what grants a reader the shared corpus.
# Without it a caller only ever sees their own documents.
SHARED_CORPUS_GROUP = os.getenv("SHARED_CORPUS_GROUP", "corpus-readers")

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# PyJWKClient caches the signing keys, so this is one network call per key id.
_jwks_client = jwt.PyJWKClient(JWKS_URL, cache_keys=True) if USER_POOL_ID else None


class AuthError(Exception):
    """The caller did not prove who they are."""


class Forbidden(Exception):
    """The caller is known but is not allowed to do this."""


@dataclass(frozen=True)
class Caller:
    """Who the caller is, according to their ID token and nothing else."""

    email: str
    may_read_shared_corpus: bool


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


def claim_groups(claims: dict) -> list:
    """Return the caller's Cognito groups.

    Cognito sends `cognito:groups` as a JSON array in the ID token, but the claim
    survives some round trips as a bracketed, comma- or space-separated string.
    Handle both, the same way the API handler does, rather than silently treating
    a string as a list of characters — the two paths authorise the same thing and
    must not disagree about what the claim says.
    """
    groups = claims.get("cognito:groups") or []
    if isinstance(groups, str):
        groups = groups.strip().strip("[]").replace(",", " ").split()
    return [g for g in groups if isinstance(g, str) and g]


def verified_caller(token: str) -> Caller:
    """Return the verified identity of the caller."""
    claims = verify_id_token(token)

    email = claims.get("email")
    if not email:
        raise AuthError("ID token carries no email claim")
    if claims.get("email_verified") not in (True, "true", "True"):
        raise AuthError("Email address is not verified")

    return Caller(
        email=email,
        may_read_shared_corpus=SHARED_CORPUS_GROUP in claim_groups(claims),
    )
