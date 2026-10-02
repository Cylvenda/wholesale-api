"""Readable delete errors instead of 500s.

The shop's data model protects its history: almost every relation that points at
master data uses ``on_delete=PROTECT``. Deleting a product, customer, supplier,
brand, category or user therefore raises ``ProtectedError`` whenever the record
is referenced, and a stray ``IntegrityError`` covers unique/foreign-key
violations. DRF turns any of those into "Internal Server Error", which tells the
user nothing and hides the real reason.

``SafeDestroyMixin`` translates both into a 400 with the records that block the
delete, so the client can show something actionable.
"""

from collections import Counter

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework.exceptions import ValidationError

# Labels for constraint text the database may hand back verbatim.
_UNIQUE_HINTS = (
    "unique constraint",
    "duplicate key",
)
_FOREIGN_KEY_HINTS = (
    "foreign key",
    "violates foreign key",
)


def describe_blockers(protected_objects) -> list[str]:
    """Turn the collector's payload into ``["product (x3)", ...]``.

    Depending on the Django version and error type this arrives as a flat set of
    model instances (``ProtectedError``) or as ``(model, instances)`` pairs, so
    both shapes are unwrapped here rather than at each call site.
    """
    counts: Counter = Counter()

    for entry in protected_objects or ():
        # A model instance, a model class, or a (model, ...) pair.
        model = getattr(entry, "_meta", None)
        if model is None:
            first = entry[0] if isinstance(entry, (tuple, list)) and entry else entry
            model = getattr(first, "_meta", None)
        if model is not None:
            counts[model.verbose_name] += 1

    return [
        f"{name} (x{count})" if count > 1 else name
        for name, count in sorted(counts.items())
    ]


def blocker_payload(exc):
    """Read the referenced-record payload off either delete error type."""
    for attribute in ("protected_objects", "restricted_objects"):
        payload = getattr(exc, attribute, None)
        if payload:
            return payload
    return []


def build_delete_error(instance, blockers: list[str]) -> str:
    label = instance._meta.verbose_name
    return (
        f"This {label} cannot be deleted because it is still referenced by: "
        f"{', '.join(blockers)}. Remove or deactivate those records first so the "
        "history stays intact."
    )


def integrity_error_message(exc: IntegrityError) -> str:
    """Explain a raw constraint violation in the shop's own words."""
    detail = str(getattr(exc, "__cause__", None) or exc).lower()

    if any(hint in detail for hint in _FOREIGN_KEY_HINTS):
        return (
            "This record cannot be deleted because other records still depend on "
            "it. Remove or deactivate those records first."
        )
    if any(hint in detail for hint in _UNIQUE_HINTS):
        return (
            "This record cannot be saved or deleted because it conflicts with an "
            "existing record that uses the same unique value."
        )
    return "This record cannot be deleted because it conflicts with existing data."


class SafeDestroyMixin:
    """Give ``perform_destroy`` readable errors for protected/constraint deletes.

    Viewsets that need extra work around a delete (restoring stock, recalculating
    a balance) should override :meth:`destroy_instance` instead of
    :meth:`perform_destroy`, so this error handling keeps applying.
    """

    def perform_destroy(self, instance):
        try:
            # Wrapped so a partially applied delete cannot survive the error.
            with transaction.atomic():
                self.destroy_instance(instance)
        except (ProtectedError, RestrictedError) as exc:
            blockers = describe_blockers(blocker_payload(exc))
            raise ValidationError(
                build_delete_error(instance, blockers or ["other records"])
            ) from exc
        except IntegrityError as exc:
            raise ValidationError(integrity_error_message(exc)) from exc

    def destroy_instance(self, instance):
        instance.delete()