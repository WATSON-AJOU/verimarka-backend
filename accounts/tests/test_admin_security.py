from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from contents.models import Content

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


def test_staff_admin_cannot_change_admin_role(db):
    actor = _create_user("staff-actor", is_staff=True, is_superuser=False)
    target = _create_user("staff-target")
    client = APIClient()
    client.force_authenticate(actor)

    response = client.patch(
        reverse("admin_user_detail", kwargs={"user_id": target.id}),
        {"role": "관리자"},
        format="json",
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert target.is_staff is False
    assert target.is_superuser is False


def test_admin_role_promotion_does_not_grant_superuser(db):
    actor = _create_user("super-actor", is_staff=True, is_superuser=True)
    target = _create_user("promote-target")
    client = APIClient()
    client.force_authenticate(actor)

    response = client.patch(
        reverse("admin_user_detail", kwargs={"user_id": target.id}),
        {"role": "관리자"},
        format="json",
    )

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.is_staff is True
    assert target.is_superuser is False


def test_deleted_user_is_not_exposed_in_admin_detail(db):
    admin = _create_user("admin-deleted-detail", is_staff=True, is_superuser=True)
    target = _create_user("deleted-target")
    target.is_deleted = True
    target.save(update_fields=["is_deleted"])
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get(reverse("admin_user_detail", kwargs={"user_id": target.id}))

    assert response.status_code == 404


def test_deleted_admin_cannot_login_with_password(db):
    email = "deleted-admin@example.com"
    User.objects.create_user(
        username=email,
        email=email,
        password="Password123!",
        nickname="deleted-admin",
        display_name="deleted-admin",
        is_staff=True,
        is_superuser=True,
        is_deleted=True,
    )
    client = APIClient()

    response = client.post(
        reverse("admin_login"),
        {"email": email, "password": "Password123!"},
        format="json",
    )

    assert response.status_code == 400
    assert "탈퇴한 계정" in str(response.data)


def test_admin_user_detail_limits_recent_activity_page(db):
    admin = _create_user("admin-activity", is_staff=True, is_superuser=True)
    target = _create_user("activity-target")
    base_time = timezone.now()
    contents = [
        Content.objects.create(
            owner=target,
            content_type="image",
            status="allow",
            decision="allow",
            original_file="",
            original_filename=f"activity-{index}.png",
            mime_type="image/png",
            file_size=123,
            reason="등록 승인",
        )
        for index in range(3)
    ]
    for index, content in enumerate(contents):
        Content.objects.filter(pk=content.pk).update(
            created_at=base_time + timedelta(minutes=index)
        )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get(
        reverse("admin_user_detail", kwargs={"user_id": target.id}),
        {"page_size": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["activity_total_count"] == 3
    assert payload["activity_total_pages"] == 2
    assert len(payload["recent_activities"]) == 2
    assert [item["title"] for item in payload["recent_activities"]] == [
        "activity-2.png",
        "activity-1.png",
    ]
