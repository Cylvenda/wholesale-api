"""The live schema must match the models, not just the migration records.

Django compares models against migration *state*, so ``makemigrations --check``
stays silent when a database was created from an older revision of a model and
then recorded as already migrated. One table drifted exactly that way: it kept
an older shape while the migration record claimed it was current, and the first
symptom was an unrelated ``no such column`` 500 while deleting a user.

These tests read the real tables through the database's own introspection and
compare them with what the models declare.
"""

from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase


class SchemaIntegrityTests(TestCase):
    def tables(self):
        with connection.cursor() as cursor:
            return {
                row[0]
                for row in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

    def columns(self, table):
        with connection.cursor() as cursor:
            return {row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")')}

    def test_every_concrete_model_table_exists(self):
        tables = self.tables()
        missing = [
            model._meta.db_table
            for model in apps.get_models()
            if not model._meta.proxy
            and not model._meta.auto_created
            and model._meta.db_table not in tables
        ]
        self.assertEqual(missing, [], "Tables missing from the database")

    def test_every_model_column_exists(self):
        problems = []
        for model in apps.get_models():
            if model._meta.proxy or model._meta.auto_created:
                continue
            table = model._meta.db_table
            if table not in self.tables():
                continue
            expected = {field.column for field in model._meta.local_fields}
            absent = expected - self.columns(table)
            if absent:
                problems.append(f"{table} is missing {sorted(absent)}")
        self.assertEqual(problems, [], "Schema drift against the models")

    def test_migration_state_matches_the_models(self):
        """makemigrations must have nothing left to do."""
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        state = loader.project_state()

        problems = []
        for model in apps.get_models():
            if model._meta.proxy or model._meta.auto_created:
                continue
            try:
                migrated = state.apps.get_model(
                    model._meta.app_label, model._meta.model_name
                )
            except LookupError:
                problems.append(f"{model._meta.label} has no migration state")
                continue
            expected = {f.name for f in model._meta.local_fields}
            recorded = {f.name for f in migrated._meta.local_fields}
            if expected != recorded:
                problems.append(
                    f"{model._meta.label}: model has {sorted(expected - recorded)} "
                    f"that migrations do not"
                )
        self.assertEqual(problems, [], "Migration state is out of date")

    def test_no_pending_migrations(self):
        """A pending migration is the condition this module guards against."""
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        self.assertEqual(
            list(executor.migration_plan(executor.loader.graph.leaf_nodes())), []
        )