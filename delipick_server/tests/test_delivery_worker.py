"""Offline checks: no real Naver calls, database updates or background threads."""
from delipick_server import update_delivery as delivery
import pytest


def test_startup_refreshes_once_then_schedules_every_hour(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    calls = []
    class Scheduler:
        running = False
        def add_job(self, function, trigger, **kwargs):
            calls.append(("schedule", function, trigger, kwargs))
        def start(self):
            self.running = True
            calls.append(("start",))
    scheduler = Scheduler()
    def refresh():
        calls.append(("refresh",))
    monkeypatch.setattr(delivery, "scheduler", scheduler)
    monkeypatch.setattr(delivery, "update_delivery_times", refresh)
    delivery.start_delivery_worker()
    assert len(calls) == 2
    assert calls[0][0:3] == ("schedule", refresh, "interval")
    assert calls[0][3]["minutes"] == 60
    assert calls[0][3]["max_instances"] == 1
    assert calls[0][3]["next_run_time"] is not None
    assert calls[1] == ("start",)
    delivery.start_delivery_worker()
    assert len(calls) == 2


def test_keys_and_fixed_origin_are_used_for_route_request(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    class Response:
        status_code = 200
        def json(self):
            return {"route": {"trafast": [{"summary": {"duration": 900000}}]}}
    def get(url, *, params, headers, timeout):
        assert url == delivery.NAVER_URL
        assert params["start"] == f"{delivery.USER_LON},{delivery.USER_LAT}"
        assert params["goal"] == "129.0,35.2"
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "test-client"
        assert headers["X-NCP-APIGW-API-KEY"] == "test-secret"
        assert timeout == 8
        return Response()
    monkeypatch.setattr(delivery.requests, "get", get)
    assert delivery.get_naver_duration(35.2, 129.0) == 15


def test_missing_keys_do_not_fabricate_a_delivery_time(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("No request should be made without keys")
    monkeypatch.setattr(delivery.requests, "get", forbidden)
    assert delivery.get_naver_duration(35.2, 129.0) is None


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_failure_stops_a_batch(monkeypatch, status):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    class Response:
        status_code = status
    monkeypatch.setattr(delivery.requests, "get", lambda *a, **k: Response())
    with pytest.raises(delivery.NaverAccessError):
        delivery.get_naver_duration(35.2, 129.0)


def test_no_credentials_do_not_even_open_the_database(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    def forbidden():
        raise AssertionError("Do not write artificial times to the database")
    monkeypatch.setattr(delivery, "get_db_connection", forbidden)
    delivery.update_delivery_times()


def test_failed_route_keeps_stored_time_and_timestamp(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    writes = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, *args):
            if sql.startswith("UPDATE"): writes.append(sql)
        def fetchall(self): return [{"id": 1, "latitude": 35.2, "longitude": 129.0}]
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    monkeypatch.setattr(delivery, "get_db_connection", Connection)
    monkeypatch.setattr(delivery, "get_naver_duration", lambda *args: None)
    delivery.update_delivery_times()
    assert writes == []
