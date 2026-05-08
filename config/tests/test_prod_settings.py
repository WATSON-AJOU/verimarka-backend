import importlib
import os


def test_production_settings_enable_browser_security_headers(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("DB_NAME", "verimarka")
    monkeypatch.setenv("DB_USER", "verimarka")
    monkeypatch.setenv("DB_PASSWORD", "verimarka")
    monkeypatch.setenv("DB_HOST", "127.0.0.1")

    previous_settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    try:
        prod = importlib.reload(importlib.import_module("config.settings.prod"))
    finally:
        if previous_settings_module is None:
            os.environ.pop("DJANGO_SETTINGS_MODULE", None)
        else:
            os.environ["DJANGO_SETTINGS_MODULE"] = previous_settings_module

    assert prod.DEBUG is False
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_HSTS_SECONDS >= 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True
    assert prod.SECURE_REFERRER_POLICY == "strict-origin-when-cross-origin"
    assert prod.SECURE_CROSS_ORIGIN_OPENER_POLICY == "same-origin"
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.SESSION_COOKIE_SAMESITE == "Lax"
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SAMESITE == "Lax"
