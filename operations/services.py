from operations.api.utils import get_request_ip
from operations.models import PolicyVersion, UserPolicyConsent


def record_active_policy_consents(*, user, request=None) -> int:
    active_policies = PolicyVersion.objects.filter(is_active=True)
    ip_address = get_request_ip(request) if request is not None else None
    created = 0
    for policy in active_policies:
        _, was_created = UserPolicyConsent.objects.get_or_create(
            user=user,
            policy_version=policy,
            defaults={"ip_address": ip_address},
        )
        if was_created:
            created += 1
    return created
