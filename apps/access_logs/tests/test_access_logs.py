"""The access log must record every sign-in attempt and refuse all edits."""

import django
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.access_logs.models import AccessLog
from apps.access_logs.request_info import describe_device
from apps.access_logs.tests.base import (
    DESKTOP_CHROME,
    IPHONE_SAFARI,
    authenticated_admin_client,
    login_client,
    make_user,
    triggers_removed,
)


def make_log(**overrides):
    values = {
        "event": AccessLog.Event.LOGIN_SUCCESS,
        "email_attempted": "staff@example.com",
        "ip_address": "197.16.79.20",
        "ip_version": 4,
    }
    values.update(overrides)
    entry = AccessLog(**values)
    entry.stamp()
    entry.save()
    return entry


class LoginRecordingTests(TestCase):
    def test_successful_login_is_recorded_with_address_and_device(self):
        user = make_user()
        _client, response = login_client(user)

        self.assertEqual(response.status_code, 200)
        entry = AccessLog.objects.get()
        self.assertEqual(entry.event, AccessLog.Event.LOGIN_SUCCESS)
        self.assertEqual(entry.user, user)
        self.assertEqual(entry.email_attempted, user.email)
        self.assertEqual(entry.ip_address, "197.16.79.20")
        self.assertEqual(entry.ip_version, 4)
        self.assertEqual(entry.device_type, "desktop")
        self.assertEqual(entry.os_name, "Windows")
        self.assertEqual(entry.browser_name, "Chrome")
        self.assertTrue(entry.is_first_login)

    def test_login_updates_the_users_stored_address(self):
        user = make_user()
        login_client(user, ip="197.16.79.20")

        user.refresh_from_db()
        self.assertEqual(user.last_login_ip, "197.16.79.20")

    def test_wrong_password_is_recorded_and_rejected(self):
        user = make_user()
        _client, response = login_client(user, password="wrong-password")

        self.assertEqual(response.status_code, 401)
        entry = AccessLog.objects.get()
        self.assertEqual(entry.event, AccessLog.Event.LOGIN_FAILURE)
        self.assertEqual(entry.user, user)
        self.assertIn("Incorrect", entry.reason)

    def test_login_for_an_unknown_address_is_recorded_without_a_user(self):
        response = APIClient().post(
            "/api/auth/jwt/create/",
            {"email": "ghost@example.com", "password": "whatever123"},
            format="json",
            REMOTE_ADDR="197.16.79.20",
        )
        self.assertEqual(response.status_code, 401)
        entry = AccessLog.objects.get()
        self.assertEqual(entry.event, AccessLog.Event.LOGIN_FAILURE)
        self.assertIsNone(entry.user)
        self.assertEqual(entry.email_attempted, "ghost@example.com")

    def test_inactive_user_login_is_recorded_and_refused(self):
        user = make_user(is_active=False)
        _client, response = login_client(user)

        # One uniform 401 for a disabled account and a wrong password, so a
        # caller cannot probe which addresses exist.
        self.assertEqual(response.status_code, 401)
        entry = AccessLog.objects.get()
        self.assertEqual(entry.event, AccessLog.Event.LOGIN_FAILURE)
        self.assertEqual(entry.user, user)
        self.assertEqual(entry.reason, "Account is inactive")

    def test_empty_payload_is_recorded_as_a_failure(self):
        response = APIClient().post("/api/auth/jwt/create/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AccessLog.objects.get().event, AccessLog.Event.LOGIN_FAILURE)

    def test_second_login_from_a_new_device_is_flagged(self):
        user = make_user()
        login_client(user, user_agent=DESKTOP_CHROME)
        login_client(user, user_agent=IPHONE_SAFARI)

        second = AccessLog.objects.order_by("id").last()
        self.assertTrue(second.is_new_device)
        self.assertFalse(second.is_first_login)
        self.assertEqual(second.browser_name, "Safari")
        self.assertEqual(second.device_type, "mobile")
        self.assertEqual(second.previous_ip_address, "197.16.79.20")

    def test_repeat_login_from_the_same_device_is_not_new(self):
        user = make_user()
        login_client(user, user_agent=DESKTOP_CHROME)
        login_client(user, user_agent=DESKTOP_CHROME)

        self.assertFalse(AccessLog.objects.order_by("id").last().is_new_device)

    def test_forwarded_header_is_ignored_without_a_configured_proxy(self):
        user = make_user()
        response = APIClient().post(
            "/api/auth/jwt/create/",
            {"email": user.email, "password": "Str0ngPass!23"},
            format="json",
            REMOTE_ADDR="197.16.79.20",
            HTTP_X_FORWARDED_FOR="1.2.3.4",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccessLog.objects.get().ip_address, "197.16.79.20")


class ImmutabilityTests(TestCase):
    def test_saving_an_existing_entry_is_refused(self):
        entry = make_log()
        entry.ip_address = "10.0.0.1"

        with self.assertRaises(ValueError):
            entry.save()

    def test_deleting_an_entry_is_refused(self):
        entry = make_log()
        with self.assertRaises(ValueError):
            entry.delete()

    def test_database_trigger_blocks_a_bulk_update(self):
        make_log()
        with self.assertRaises(Exception):
            AccessLog.objects.update(reason="rewritten")

    def test_database_trigger_blocks_a_bulk_delete(self):
        make_log()
        with self.assertRaises(Exception):
            AccessLog.objects.all().delete()

    def test_database_trigger_blocks_a_direct_sql_update(self):
        entry = make_log()
        with self.assertRaises(Exception):
            AccessLog.objects.raw(
                "UPDATE access_logs_accesslog SET reason = 'rewritten' WHERE id = %s",
                [entry.id],
            ).execute()

    def test_hash_chain_detects_an_edited_row(self):
        first = make_log(email_attempted="one@example.com")
        make_log(email_attempted="two@example.com")

        # Reaching the database directly means lifting the trigger first.
        with triggers_removed():
            AccessLog.objects.filter(pk=first.pk).update(email_attempted="edited@example.com")

        self.assertIsNotNone(first.verify_chain())

    def test_hash_chain_is_intact_when_untouched(self):
        first = make_log(email_attempted="one@example.com")
        make_log(email_attempted="two@example.com")

        self.assertIsNone(first.verify_chain())

    def test_deleting_a_user_does_not_erase_their_log(self):
        from django.db.models import ProtectedError

        user = make_user()
        login_client(user)
        with self.assertRaises(ProtectedError):
            user.delete()
        self.assertEqual(AccessLog.objects.count(), 1)


class AccessLogApiTests(TestCase):
    def setUp(self):
        self.client = authenticated_admin_client()

    def test_list_requires_an_admin(self):
        plain = APIClient()
        plain.force_authenticate(user=make_user(email="sales@example.com", phone="+255700000009"))
        self.assertEqual(plain.get("/api/access-logs/").status_code, 403)
        self.assertEqual(APIClient().get("/api/access-logs/").status_code, 401)

    def test_list_returns_entries(self):
        make_log(email_attempted="one@example.com")
        response = self.client.get("/api/access-logs/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertIn("ip_address", response.data["results"][0])

    def test_write_and_delete_endpoints_are_not_available(self):
        make_log()
        for method, url in (
            ("post", "/api/access-logs/"),
            ("put", "/api/access-logs/1/"),
            ("patch", "/api/access-logs/1/"),
            ("delete", "/api/access-logs/1/"),
        ):
            with self.subTest(method=method):
                self.assertIn(getattr(self.client, method)(url, {}, format="json").status_code, (401, 405))

    def test_filtering_by_event_and_ip(self):
        make_log(email_attempted="one@example.com", ip_address="197.16.79.20")
        make_log(
            event=AccessLog.Event.LOGIN_FAILURE,
            email_attempted="two@example.com",
            ip_address="197.16.79.21",
        )

        by_event = self.client.get("/api/access-logs/?event=login_failure")
        self.assertEqual(by_event.data["count"], 1)

        by_ip = self.client.get("/api/access-logs/?ip_address=197.16.79.20")
        self.assertEqual(by_ip.data["count"], 1)

    def test_summary_endpoint_counts_events(self):
        make_log()
        make_log(event=AccessLog.Event.LOGIN_FAILURE)
        response = self.client.get("/api/access-logs/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["successful_logins"], 1)
        self.assertEqual(response.data["failed_attempts"], 1)

    def test_integrity_endpoint_reports_a_healthy_chain(self):
        first = make_log()
        make_log()
        response = self.client.get("/api/access-logs/integrity/")

        self.assertTrue(response.data["intact"])
        self.assertEqual(response.data["entries"], 2)

    def test_integrity_endpoint_flags_an_edited_row(self):
        first = make_log()
        with triggers_removed():
            AccessLog.objects.filter(pk=first.pk).update(reason="rewritten")

        response = self.client.get("/api/access-logs/integrity/")
        self.assertFalse(response.data["intact"])
        self.assertEqual(response.data["first_broken_entry"], first.id)


class DeviceParsingTests(TestCase):
    def test_windows_chrome_is_desktop(self):
        self.assertEqual(
            describe_device(DESKTOP_CHROME), ("desktop", "Windows", "Chrome")
        )

    def test_iphone_safari_is_mobile(self):
        self.assertEqual(describe_device(IPHONE_SAFARI), ("mobile", "iOS", "Safari"))

    def test_unknown_agent_yields_blanks(self):
        self.assertEqual(describe_device(""), ("", "", ""))

    def test_private_addresses_have_no_location_lookup(self):
        from apps.access_logs.request_info import describe_location

        self.assertEqual(describe_location("127.0.0.1"), {})
        self.assertEqual(describe_location("10.0.0.1"), {})