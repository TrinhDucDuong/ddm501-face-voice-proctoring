from app.migrations import migrate
from sqlalchemy import create_engine, text

from pipeline.responsible_ai_report import build_report


def test_additive_migration_preserves_old_people(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE people (id VARCHAR(36) PRIMARY KEY, external_id VARCHAR(100) UNIQUE, "
                                "display_name VARCHAR(200), active BOOLEAN, created_at DATETIME)"))
        connection.execute(text("INSERT INTO people VALUES ('old', 'OLD-1', 'Existing person', true, CURRENT_TIMESTAMP)"))
    migrate(engine)
    migrate(engine)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT external_id, tenant_id, display_name FROM people WHERE id='old'")).one()
        assert tuple(row) == ("OLD-1", "demo", "Existing person")
        assert connection.execute(text("SELECT count(*) FROM tenants WHERE id='demo'")).scalar() == 1
    engine.dispose()


def test_fairness_report_does_not_claim_human_fairness_from_synthetic_labels():
    rows = [
        {"quality_slice": "high", "label_source": "synthetic", "reviewed": 100, "accuracy": 1,
         "false_accept_rate": None, "false_reject_rate": 0},
        {"quality_slice": "low", "label_source": "synthetic", "reviewed": 100, "accuracy": 0,
         "false_accept_rate": 1, "false_reject_rate": None},
    ]
    assert build_report(rows)["gate"] == "insufficient_data"
    for row in rows:
        row["label_source"] = "human"
        row['genuine_count'] = row['impostor_count'] = 50
    assert build_report(rows)["gate"] == "review"
