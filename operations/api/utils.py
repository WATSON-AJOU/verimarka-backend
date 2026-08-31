from operations.models import AdminActionLog


def get_request_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


def log_admin_action(
    *,
    request,
    action: str,
    target_type: str,
    target_id,
    reason: str = "",
    before: dict | None = None,
    after: dict | None = None,
) -> AdminActionLog:
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None
    return AdminActionLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason,
        before=before or {},
        after=after or {},
        request_id=request.headers.get("X-Request-Id", ""),
        ip_address=get_request_ip(request),
    )
