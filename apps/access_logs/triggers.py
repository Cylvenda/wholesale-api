"""Database-level protection for the access log table.

The application refuses to update or delete an entry. These triggers close the
remaining routes: a bulk query that skips `save()`/`delete()`, or raw SQL from a
shell, fails at the database itself. Kept outside the migration module so tests
can lift and restore them without loading migrations by name.
"""

SQLITE_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS access_logs_no_update
    BEFORE UPDATE ON access_logs_accesslog
    BEGIN
        SELECT RAISE(ABORT, 'Access log entries are permanent and cannot be modified.');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS access_logs_no_delete
    BEFORE DELETE ON access_logs_accesslog
    BEGIN
        SELECT RAISE(ABORT, 'Access log entries are permanent and cannot be deleted.');
    END
    """,
]

# Sent as a single execute(): the function body between $$ markers contains
# semicolons, so it cannot be split.
POSTGRES_TRIGGERS = """
CREATE OR REPLACE FUNCTION access_logs_block_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Access log entries are permanent and cannot be modified or deleted.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS access_logs_no_mutation ON access_logs_accesslog;
CREATE TRIGGER access_logs_no_mutation
BEFORE UPDATE OR DELETE ON access_logs_accesslog
FOR EACH ROW EXECUTE FUNCTION access_logs_block_mutation();
"""

DROP_SQLITE_TRIGGERS = [
    "DROP TRIGGER IF EXISTS access_logs_no_update",
    "DROP TRIGGER IF EXISTS access_logs_no_delete",
]

DROP_POSTGRES_TRIGGERS = """
DROP TRIGGER IF EXISTS access_logs_no_mutation ON access_logs_accesslog;
DROP FUNCTION IF EXISTS access_logs_block_mutation();
"""


def _statements(connection, forward):
    if connection.vendor == "postgresql":
        return [POSTGRES_TRIGGERS] if forward else [DROP_POSTGRES_TRIGGERS]
    # SQLite allows only one statement per execute call.
    return SQLITE_TRIGGERS if forward else DROP_SQLITE_TRIGGERS


def statements(connection, forward=True):
    """The DDL to run, for callers holding a cursor rather than a schema_editor.

    SQLite refuses to open a schema editor inside an open transaction, so tests
    restore the triggers through a plain cursor.
    """
    return _statements(connection, forward)


def create(schema_editor):
    """Install the triggers. Takes a schema_editor so tests can reuse it."""
    for statement in statements(schema_editor.connection, forward=True):
        schema_editor.execute(statement)


def remove(schema_editor):
    """Uninstall the triggers."""
    for statement in _statements(schema_editor.connection, forward=False):
        schema_editor.execute(statement)


# RunPython passes (app_registry, schema_editor); adapt to the helpers above.
def apply_triggers(apps, schema_editor):
    create(schema_editor)


def drop_triggers(apps, schema_editor):
    remove(schema_editor)