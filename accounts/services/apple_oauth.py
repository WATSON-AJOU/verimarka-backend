import time
from functools import lru_cache

import jwt
import requests
from django.conf import settings


class AppleOAuthError(Exception):
    pass


def _get_apple_private_key() -> str:
    private_key = settings.APPLE_PRIVATE_KEY.strip()
    if not private_key:
        raise AppleOAuthError("apple_private_key_missing")
    return private_key.replace("\\n", "\n")


def generate_client_secret() -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.APPLE_TEAM_ID,
            "iat": now,
            "exp": now + (60 * 60 * 24 * 180),
            "aud": "https://appleid.apple.com",
            "sub": settings.APPLE_SERVICES_ID,
        },
        _get_apple_private_key(),
        algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID},
    )


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.APPLE_SERVICES_ID,
        "client_secret": generate_client_secret(),
        "redirect_uri": redirect_uri,
    }

    resp = requests.post(settings.APPLE_TOKEN_URI, data=data, timeout=10)
    if resp.status_code != 200:
        raise AppleOAuthError(f"token_exchange_failed: {resp.status_code} {resp.text}")

    return resp.json()


@lru_cache(maxsize=1)
def _get_jwk_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(settings.APPLE_JWKS_URI)


def verify_identity_token(identity_token: str) -> dict:
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.APPLE_SERVICES_ID,
            issuer="https://appleid.apple.com",
        )
    except jwt.PyJWTError as exc:
        raise AppleOAuthError(f"id_token_verification_failed: {exc}") from exc
