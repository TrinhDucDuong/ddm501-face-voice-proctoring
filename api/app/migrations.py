"""Additive migration for the pre-SaaS demo; safe to rerun without deleting records."""
from sqlalchemy import inspect, text


def migrate(engine) -> None:
    with engine.begin() as connection:
        # Serialize concurrent API startup migrations on PostgreSQL.
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(5012026)"))
        from . import models  # noqa: F401
        from .db import Base
        Base.metadata.create_all(connection)
        delivery_columns = inspect(connection).get_columns("webhook_deliveries")
        if not next(c for c in delivery_columns if c["name"] == "session_id")["nullable"]:
            if connection.dialect.name == "postgresql":
                connection.execute(text("ALTER TABLE webhook_deliveries ALTER COLUMN session_id DROP NOT NULL"))
            else:
                # Old SQLite demos have no inbound foreign keys to this outbox.
                connection.execute(text("ALTER TABLE webhook_deliveries RENAME TO old_webhook_deliveries"))
                for index in inspect(connection).get_indexes("old_webhook_deliveries"):
                    connection.execute(text('DROP INDEX "' + index['name'].replace('"', '""') + '"'))
                models.WebhookDelivery.__table__.create(connection)
                names = ','.join('"' + c['name'] + '"' for c in delivery_columns)
                connection.execute(text(f"INSERT INTO webhook_deliveries ({names}) SELECT {names} FROM old_webhook_deliveries"))
                connection.execute(text("DROP TABLE old_webhook_deliveries"))
        columns = {item["name"] for item in inspect(connection).get_columns("people")}
        if "tenant_id" not in columns:
            connection.execute(text("ALTER TABLE people ADD COLUMN tenant_id VARCHAR(36) NOT NULL DEFAULT 'demo'"))
            connection.execute(text("CREATE INDEX ix_people_tenant_id ON people (tenant_id)"))
        if "external_ref" not in columns:
            connection.execute(text("ALTER TABLE people ADD COLUMN external_ref VARCHAR(100)"))
        if "details" not in {item["name"] for item in inspect(connection).get_columns("audit_logs")}:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN details TEXT"))
        connection.execute(text("INSERT INTO tenants (id, name, active, created_at) "
                                "VALUES ('demo', 'Existing demo', true, CURRENT_TIMESTAMP) ON CONFLICT (id) DO NOTHING"))
