"""Shared helpers for access-log tests."""

from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient

from apps.access_logs import triggers as access_log_triggers

User = get_user_model()

DESKTOP_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
)


def make_user(email="staff@example.com", password="Str0ngPass!23", **extra):
    extra.setdefault("phone", "+255700000001")
    extra.setdefault("first_name", "Test")
    user = User.objects.create_user(email=email, password=password, **extra)
    return user


def login_client(user=None, password="Str0ngPass!23", ip="197.16.79.20", user_agent=DESKTOP_CHROME):
    """POST the sign-in endpoint the frontend uses."""
    client = APIClient()
    body = {
        "email": (user.email if user else "staff@example.com"),
        "password": password,
    }
    response = client.post(
        "/api/auth/jwt/create/",
        body,
        format="json",
        HTTP_USER_AGENT=user_agent,
        REMOTE_ADDR=ip,
    )
    return client, response


def authenticated_admin_client(user=None):
    client = APIClient()
    user = user or make_user(is_staff=True, role="admin")
    client.force_authenticate(user=user)
    return client


@contextmanager
def triggers_removed():
    """Temporarily lift the immutability triggers.

    Someone who reaches the database directly would have to do exactly this to
    alter history, so tests that need to tamper have to lift the triggers too.
    """
    if connection.vendor == "postgresql":
        connection.cursor().execute(
            "DROP TRIGGER IF EXISTS access_logs_no_mutation ON access_logs_accesslog"
        )
    else:
        connection.cursor().execute("DROP TRIGGER IF EXISTS access_logs_no_update")
        connection.cursor().execute("DROP TRIGGER IF EXISTS access_logs_no_delete")
    try:
        yield
    finally:
        # A cursor rather than a schema_editor: SQLite will not open one inside
        # the transaction the test is already running in.
        with connection.cursor() as cursor:
            for statement in access_log_triggers.statements(connection, forward=True):
                cursor.execute(statement)