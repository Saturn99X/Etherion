import time


def slow_return():
    time.sleep(1.0)
    return "ok"


def test_run_in_process_with_timeout_times_out():
    from src.services.ingestion_service import _run_in_process_with_timeout

    ok, value, timed_out, err = _run_in_process_with_timeout(slow_return, tuple(), timeout_s=0.05)
    assert ok is False
    assert value is None
    assert timed_out is True
    assert err == "timeout"
