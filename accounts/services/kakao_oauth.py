import requests
from django.conf import settings


class KakaoOAuthError(Exception):
    pass


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    # 카카오는 보안 강화를 위해 client_secret 사용 가능
    if getattr(settings, "KAKAO_CLIENT_SECRET", ""):
        data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    try:
        resp = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data=data,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise KakaoOAuthError(f"token_exchange_failed: request_error {exc}") from exc
    if resp.status_code != 200:
        raise KakaoOAuthError(f"token_exchange_failed: {resp.status_code} {resp.text}")

    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    try:
        resp = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise KakaoOAuthError(f"userinfo_failed: request_error {exc}") from exc
    if resp.status_code != 200:
        raise KakaoOAuthError(f"userinfo_failed: {resp.status_code} {resp.text}")

    return resp.json()
