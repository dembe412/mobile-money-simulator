from src.ussd.protocol import USSDFormatter, USSDSessionManager


def test_ussd_session_lifecycle(db):
    manager = USSDSessionManager(ttl_seconds=60)

    session = manager.create_session(db, "0700000001")
    assert session.session_id.startswith("ussd_0700000001_")
    assert session.session_state == "MAIN_MENU"

    loaded = manager.get_session(db, session.session_id)
    assert loaded is not None
    assert loaded.phone_number == "0700000001"

    updated = manager.update_session(db, session.session_id, "DEPOSIT_AMOUNT", {"pending_operation": "deposit"})
    assert updated.session_state == "DEPOSIT_AMOUNT"
    assert updated.session_data["data"]["pending_operation"] == "deposit"

    assert manager.end_session(db, session.session_id) is True
    assert manager.get_session(db, session.session_id) is None


def test_ussd_formatter_session_responses():
    assert USSDFormatter.main_menu().startswith("CON ")
    assert USSDFormatter.session_end("Done").startswith("END ")
