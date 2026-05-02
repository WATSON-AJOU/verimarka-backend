import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from wallets.models import WalletLink


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    model = get_user_model()
    return model.objects.create_user(
        username="pytest-user",
        nickname="pytestuser",
        display_name="Pytest User",
        email="pytest-user@example.com",
        password="password1234",
        phone="01000001111",
        phone_verified=True,
    )


@pytest.fixture
def wallet_link(user):
    return WalletLink.objects.create(
        user=user,
        address="0x1234567890123456789012345678901234567890",
    )


@pytest.fixture
def authenticated_api_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
