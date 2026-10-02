"""Repair the ``expenses_expense`` table, which is missing its BaseModel columns.

Some databases were created from an older revision of the expenses app where
``Expense`` did not yet inherit ``BaseModel``. Those installs have an
``expenses_expense`` table with no ``uuid``, ``created_at``, ``updated_at`` or
``created_by_id``, yet the migration record still shows ``0001_initial`` as
applied, so Django never repairs it and never notices.

The drift stayed hidden until something queried those columns - deleting a user
walks every PROTECT relation, which made Django collect expenses and fail with
``no such column: expenses_expense.uuid``.

This migration compares the real table against the columns the model expects
and adds only what is missing, so it is a no-op on a correct database and never
touches a column that already exists.
"""

import uuid

from django.db import migrations

# (column, SQL type, how to backfill existing rows)
BACKFILL_COLUMNS = (
    ("uuid", "char(32)"),
    ("created_at", "datetime"),
    ("updated_at", "datetime"),
    ("created_by_id", "integer"),
)


def existing_columns(schema_editor, table):
    with schema_editor.connection.cursor() as cursor:
        return {
            row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")')
        }


def repair_expense_columns(apps, schema_editor):
    table = "expenses_expense"
    present = existing_columns(schema_editor, table)

    missing = [(name, sql) for name, sql in BACKFILL_COLUMNS if name not in present]
    if not missing:
        return

    with schema_editor.connection.cursor() as cursor:
        for name, sql in missing:
            cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql} NULL')

        rows = cursor.execute(f'SELECT id FROM "{table}"').fetchall()

        if rows:
            # Nothing can be recovered for a row whose author is unknown, so the
            # oldest administrator stands in rather than leaving it NULL: the
            # column is a required PROTECT foreign key.
            cursor.execute(
                'SELECT id FROM accounts_user ORDER BY is_superuser DESC, id LIMIT 1'
            )
            fallback_user = cursor.fetchone()
            fallback_id = fallback_user[0] if fallback_user else None

            for (row_id,) in rows:
                cursor.execute(
                    f'UPDATE "{table}" SET "uuid" = ? WHERE id = ?',
                    (uuid.uuid4().hex, row_id),
                )
                cursor.execute(
                    f'UPDATE "{table}" '
                    'SET "created_at" = COALESCE("created_at", "expense_date"), '
                    '"updated_at" = COALESCE("updated_at", "expense_date") '
                    "WHERE id = ?",
                    (row_id,),
                )
                if fallback_id is not None:
                    cursor.execute(
                        f'UPDATE "{table}" SET "created_by_id" = ? '
                        "WHERE id = ? AND created_by_id IS NULL",
                        (fallback_id, row_id),
                    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(repair_expense_columns, noop),
    ]