from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()


def _create_user(username: str, *, is_staff=False, is_superuser=False):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="Password123!",
        nickname=username[:30],
        display_name=username,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def test_admin_cannot_demote_self(db):
    admin = _create_user("admin-self", is_staff=True, is_superuser=True)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.patch(
        reverse("admin_user_detail", kwargs={"user_id": admin.id}),
        {"role": "일반회원"},
        format="json",
    )

    assert response.status_code == 400
    admin.refresh_from_db()
    assert admin.is_staff is True
    assert admin.is_superuser is True


def test_admin_cannot_deactivate_last_active_admin(db):
    actor = _create_user("admin-actor", is_staff=True, is_superuser=True)
    client = APIClient()
    client.force_authenticate(actor)

    response = client.patch(
        reverse("admin_user_detail", kwargs={"user_id": actor.id}),
        {"status": "정지"},
        format="json",
    )

    assert response.status_code == 400
    actor.refresh_from_db()
    assert actor.is_active is True


def test_admin_can_demote_another_admin_when_active_admin_remains(db):
    actor = _create_user("admin-actor2", is_staff=True, is_superuser=True)
    target = _create_user("admin-target", is_staff=True, is_superuser=True)
    client = APIClient()
    client.force_authenticate(actor)

    response = client.patch(
        reverse("admin_user_detail", kwargs={"user_id": target.id}),
        {"role": "일반회원"},
        format="json",
    )

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.is_staff is False
    assert target.is_superuser is False
