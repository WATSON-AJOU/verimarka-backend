import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from contents.models import Content
from operations.models import AdminActionLog, ModerationCase, ReportCase

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="ops-admin",
        nickname="ops-admin",
        display_name="Ops Admin",
        email="ops-admin@example.com",
        password="Passw0rd!",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="ops-user",
        nickname="ops-user",
        display_name="Ops User",
        email="ops-user@example.com",
        password="Passw0rd!",
        phone_verified=True,
        email_verified=True,
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def content(regular_user):
    return Content.objects.create(
        owner=regular_user,
        status="review",
        decision="review",
        original_file="",
        original_filename="sample.png",
        mime_type="image/png",
        file_size=123,
    )


@pytest.mark.django_db
def test_admin_moderation_case_updates_content_and_logs_action(admin_client, content):
    response = admin_client.post(
        reverse("admin_moderation_cases"),
        {
            "content_public_id": str(content.public_id),
            "action": "approve",
            "reason": "운영자 확인 완료",
        },
        format="json",
    )

    assert response.status_code == 201
    content.refresh_from_db()
    assert content.status == "allow"
    assert content.decision == "allow"
    assert ModerationCase.objects.filter(content=content, action="approve").exists()
    assert AdminActionLog.objects.filter(
        action="content_moderation",
        target_type="content",
        target_id=str(content.public_id),
    ).exists()


@pytest.mark.django_db
def test_admin_report_update_assigns_and_logs_action(
    admin_client, admin_user, regular_user, content
):
    report = ReportCase.objects.create(
        reporter=regular_user,
        content=content,
        report_type="copyright",
        title="권리 침해 신고",
        description="원저작자 확인이 필요합니다.",
    )

    response = admin_client.patch(
        reverse("admin_report_detail", kwargs={"report_id": report.pk}),
        {
            "status": "investigating",
            "resolution": "증빙 확인 중",
            "assign_to_me": True,
        },
        format="json",
    )

    assert response.status_code == 200
    report.refresh_from_db()
    assert report.status == "investigating"
    assert report.assignee == admin_user
    assert AdminActionLog.objects.filter(
        action="report_update",
        target_type="report",
        target_id=str(report.pk),
    ).exists()


@pytest.mark.django_db
def test_user_admin_patch_writes_audit_log(admin_client, regular_user):
    response = admin_client.patch(
        reverse("admin_user_detail", kwargs={"user_id": regular_user.pk}),
        {"status": "정지"},
        format="json",
    )

    assert response.status_code == 200
    regular_user.refresh_from_db()
    assert regular_user.is_active is False
    assert AdminActionLog.objects.filter(
        action="user_update",
        target_type="user",
        target_id=str(regular_user.pk),
    ).exists()
