import pytest
from delipick_server import main, update_delivery


@pytest.mark.parametrize("module", [main, update_delivery])
def test_explicit_database_is_not_replaced_by_a_fallback(module, monkeypatch):
    monkeypatch.setenv("DB_NAME", "explicit_test_db")
    assert module._db_candidates() == ["explicit_test_db"]


@pytest.mark.parametrize("module", [main, update_delivery])
def test_configured_database_port_is_used(module, monkeypatch):
    monkeypatch.setenv("DB_NAME", "explicit_test_db")
    monkeypatch.setenv("DB_PORT", "13307")
    marker = object()
    def connect(**kwargs):
        assert kwargs["port"] == 13307
        assert kwargs["db"] == "explicit_test_db"
        return marker
    monkeypatch.setattr(module.pymysql, "connect", connect)
    assert module.get_db_connection() is marker
