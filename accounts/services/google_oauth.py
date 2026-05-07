import requests
from django.conf import settings


class GoogleOAuthError(Exception):
    pass


def exchange_code_for_token(
    code: str, redirect_uri: str, code_verifier: str | None = None
) -> dict:
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    # PKCE 옵션
    if code_verifier:
        data["code_verifier"] = code_verifier

    try:
        resp = requests.post(settings.GOOGLE_TOKEN_URI, data=data, timeout=10)
    except requests.RequestException as exc:
        raise GoogleOAuthError(f"token_exchange_failed: request_error {exc}") from exc
    if resp.status_code != 200:
        raise GoogleOAuthError(f"token_exchange_failed: {resp.status_code} {resp.text}")

    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    try:
        resp = requests.get(
            settings.GOOGLE_USERINFO_URI,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(f"userinfo_failed: request_error {exc}") from exc
    if resp.status_code != 200:
        raise GoogleOAuthError(f"userinfo_failed: {resp.status_code} {resp.text}")
    return resp.json()
