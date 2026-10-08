"""Append-only audit trail of who signed in, from where.

Every row records one authentication attempt and is immutable. The model refuses
to be updated or deleted, the API is read-only, and a database trigger rejects
any UPDATE or DELETE that reaches the table directly, so the trail cannot be
edited or erased through the ORM, the admin, a shell or raw SQL.
"""

import hashlib

import uuid

from django.db import models
from django.utils import timezone


class AccessLog(models.Model):
    """One authentication attempt. Written once, never modified.

    Deliberately not a BaseModel: a failed login has no user to credit as its
    author, and an append-only row has no meaningful "updated at".
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    # A default rather than auto_now_add: the tamper-evidence hash covers the
    # timestamp, so it has to exist before the row is written.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Event(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login success"
        LOGIN_FAILURE = "login_failure", "Login failure"
        TOKEN_REFRESH = "token_refresh", "Token refresh"
        LOGOUT = "logout", "Logout"
        ACCESS_DENIED = "access_denied", "Access denied"
        PASSWORD_CHANGED = "password_changed", "Password changed"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Password reset requested"

    # Kept as PROTECT so removing a user leaves its login history behind rather
    # than cascading it away. A null user means the attempt named no account.
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="access_logs",
        null=True,
        blank=True,
    )
    # Always recorded, even when it names no account: a failed login against an
    # unknown address is exactly the case worth seeing.
    email_attempted = models.EmailField(blank=True, db_index=True)
    event = models.CharField(max_length=30, choices=Event.choices, db_index=True)
    reason = models.CharField(max_length=255, blank=True)

    # --- Where the request came from ---
    ip_address = models.GenericIPAddressField(db_index=True)
    ip_version = models.PositiveSmallIntegerField(choices=((4, "IPv4"), (6, "IPv6")))
    user_agent = models.CharField(max_length=512, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    os_name = models.CharField(max_length=80, blank=True)
    browser_name = models.CharField(max_length=80, blank=True)

    # --- Where that address is ---
    country = models.CharField(max_length=80, blank=True, db_index=True)
    country_code = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # --- Comparison against the account's own history ---
    is_first_login = models.BooleanField(default=False)
    is_new_device = models.BooleanField(default=False)
    previous_ip_address = models.GenericIPAddressField(null=True, blank=True)
    previous_login_at = models.DateTimeField(null=True, blank=True)
    failed_attempts_before = models.PositiveIntegerField(default=0)

    # --- Tamper evidence ---
    # Each row is hashed together with the row before it, so editing or removing
    # any earlier entry breaks every hash after it.
    previous_hash = models.CharField(max_length=64, blank=True, editable=False)
    entry_hash = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "access log"
        verbose_name_plural = "access logs"

    def __str__(self):
        who = self.email_attempted or (self.user.email if self.user else "unknown")
        return f"{self.event} {who} from {self.ip_address}"

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "Access log entries are permanent and cannot be modified."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Access log entries are permanent and cannot be deleted.")

    # ------------------------------------------------------------------
    # Tamper evidence
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(previous_hash, event, user_id, email, ip, created_at, reason=""):
        """A stable digest of everything worth protecting about one entry."""
        parts = (
            previous_hash,
            event,
            "" if user_id is None else str(user_id),
            email,
            ip or "",
            created_at.isoformat() if created_at else "",
            reason or "",
        )
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def stamp(self):
        """Link this entry to the previous one and compute its own hash."""
        previous = (
            AccessLog.objects.order_by("-id")
            .values_list("entry_hash", flat=True)
            .first()
        )
        self.previous_hash = previous or ""
        self.entry_hash = self._fingerprint(
            self.previous_hash,
            self.event,
            self.user_id,
            self.email_attempted,
            self.ip_address,
            self.created_at or timezone.now(),
            self.reason,
        )
        return self

    def verify_chain(self, entry=None):
        """Return the first entry whose stored hash no longer matches its content."""
        entry = entry or self
        previous_hash = entry.previous_hash
        for record in (
            AccessLog.objects.filter(id__gte=entry.id).order_by("id")
        ):
            expected = self._fingerprint(
                previous_hash,
                record.event,
                record.user_id,
                record.email_attempted,
                record.ip_address,
                record.created_at,
                record.reason,
            )
            if expected != record.entry_hash or record.previous_hash != previous_hash:
                return record
            previous_hash = record.entry_hash
        return None