"""Write entries to the access log.

This is the only place an AccessLog is ever created. Everything that reports a
login, failure or session change funnels through `record()` so the schema of an
entry stays consistent.
"""

import ipaddress

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.access_logs.models import AccessLog
from apps.access_logs.request_info import (
    describe_device,
    describe_location,
    get_client_ip,
)

User = get_user_model()


def record(
    event,
    request=None,
    user=None,
    email="",
    ip_address=None,
    user_agent=None,
    reason="",
):
    """Append one entry to the access log and return it.

    Never raises: a failure to audit must not stop the operation being audited,
    and a broken audit trail is reported rather than propagated.
    """
    try:
        address = ip_address or (get_client_ip(request) if request is not None else None)
        address = address or "0.0.0.0"
        agent = (
            user_agent
            if user_agent is not None
            else (request.META.get("HTTP_USER_AGENT", "") if request is not None else "")
        )
        device_type, os_name, browser_name = describe_device(agent)

        account = user
        email_address = email or (account.email if account else "")
        if account is None and email_address:
            account = User.objects.filter(email__iexact=email_address).first()

        history = AccessLog.objects.filter(user=account).order_by("-id") if account else AccessLog.objects.none()

        previous = history.first()
        previous_success = history.filter(event=AccessLog.Event.LOGIN_SUCCESS).first()

        entry = AccessLog(
            user=account,
            email_attempted=email_address[:254],
            event=event,
            reason=str(reason)[:255],
            ip_address=address,
            ip_version=ipaddress_version(address),
            user_agent=str(agent)[:512],
            device_type=device_type,
            os_name=os_name,
            browser_name=browser_name,
            is_first_login=bool(previous_success is None),
            is_new_device=bool(
                previous_success is not None
                and previous_success.user_agent != str(agent)[:512]
            ),
            previous_ip_address=previous.ip_address if previous else None,
            previous_login_at=previous.created_at if previous else None,
            failed_attempts_before=(
                AccessLog.objects.filter(
                    user=account,
                    event=AccessLog.Event.LOGIN_FAILURE,
                    created_at__gte=previous_success.created_at,
                ).count()
                if previous_success
                else 0
            ),
            **describe_location(address),
        )
        entry.stamp()
        with transaction.atomic():
            entry.save()
        return entry
    except (IntegrityError, ValueError, TypeError):
        return None


def ipaddress_version(address):
    """Which IP version an address is; defaults to 4 if it is unparseable."""
    try:
        return ipaddress.ip_address(address).version
    except ValueError:
        return 4


def sync_last_login_ip(user, request=None, ip_address=None):
    """Mirror the newest address onto the user for at-a-glance comparison."""
    if user is None:
        return
    address = ip_address or (get_client_ip(request) if request is not None else None)
    if address and user.last_login_ip != address:
        User.objects.filter(pk=user.pk).update(last_login_ip=address)