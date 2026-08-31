from django.urls import path

from operations.api.views import (
    AdminActionLogListView,
    AdminJobDetailView,
    AdminJobListView,
    AdminModerationCaseListView,
    AdminNotificationListView,
    AdminOperationsSummaryView,
    AdminPolicyVersionListView,
    AdminReportCaseDetailView,
    AdminReportCaseListView,
    AdminRetentionRequestDetailView,
    AdminRetentionRequestListView,
    PublicReportCaseCreateView,
)

urlpatterns = [
    path("reports/", PublicReportCaseCreateView.as_view(), name="report_create"),
    path(
        "admin/summary/",
        AdminOperationsSummaryView.as_view(),
        name="admin_operations_summary",
    ),
    path(
        "admin/audit-logs/", AdminActionLogListView.as_view(), name="admin_action_logs"
    ),
    path(
        "admin/moderation-cases/",
        AdminModerationCaseListView.as_view(),
        name="admin_moderation_cases",
    ),
    path("admin/reports/", AdminReportCaseListView.as_view(), name="admin_reports"),
    path(
        "admin/reports/<int:report_id>/",
        AdminReportCaseDetailView.as_view(),
        name="admin_report_detail",
    ),
    path(
        "admin/policies/", AdminPolicyVersionListView.as_view(), name="admin_policies"
    ),
    path(
        "admin/retention-requests/",
        AdminRetentionRequestListView.as_view(),
        name="admin_retention_requests",
    ),
    path(
        "admin/retention-requests/<int:retention_id>/",
        AdminRetentionRequestDetailView.as_view(),
        name="admin_retention_detail",
    ),
    path(
        "admin/notifications/",
        AdminNotificationListView.as_view(),
        name="admin_notifications",
    ),
    path("admin/jobs/", AdminJobListView.as_view(), name="admin_jobs"),
    path(
        "admin/jobs/<uuid:job_id>/<str:action>/",
        AdminJobDetailView.as_view(),
        name="admin_job_action",
    ),
]
