from app.models import AppConfigHistory
from app.services.config_service import get_config, list_config_history, set_config


def test_set_config_records_history_only_when_value_changes(db_session):
    changed = set_config(
        db_session,
        "benchmark_instrument",
        "OZR.AX",
        changed_by="test",
        source="unit",
    )
    assert changed is True
    assert get_config(db_session, "benchmark_instrument") == "OZR.AX"

    unchanged = set_config(
        db_session,
        "benchmark_instrument",
        "OZR.AX",
        changed_by="test",
        source="unit",
    )
    assert unchanged is False

    changed_again = set_config(
        db_session,
        "benchmark_instrument",
        "XMM.AX",
        changed_by="test",
        source="unit",
    )
    assert changed_again is True

    rows = db_session.query(AppConfigHistory).order_by(AppConfigHistory.id).all()
    assert len(rows) == 2
    assert rows[0].key == "benchmark_instrument"
    assert rows[0].old_value is None
    assert rows[0].new_value == '"OZR.AX"'
    assert rows[0].changed_by == "test"
    assert rows[0].source == "unit"
    assert rows[1].old_value == '"OZR.AX"'
    assert rows[1].new_value == '"XMM.AX"'


def test_list_config_history_limits_rows(db_session):
    for i in range(3):
        set_config(db_session, "benchmark_instrument", f"TST{i}.AX")

    rows = list_config_history(db_session, limit=2)
    assert len(rows) == 2
    assert rows[0].new_value == '"TST2.AX"'
    assert rows[1].new_value == '"TST1.AX"'
