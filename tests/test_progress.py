"""Tests for the thread-local progress channel."""

import threading

from optionpilot.progress import progress_to, report


def test_report_without_sink_is_noop():
    report("nothing set — must not raise")   # no sink -> silently ignored


def test_report_routes_to_sink_within_context():
    got = []
    with progress_to(got.append):
        report("a")
        report("b")
    assert got == ["a", "b"]


def test_sink_restored_after_context():
    outer = []
    with progress_to(outer.append):
        inner = []
        with progress_to(inner.append):
            report("x")
        report("y")          # back to the outer sink
    assert inner == ["x"] and outer == ["y"]


def test_sink_is_thread_local():
    got = []
    with progress_to(got.append):
        done = threading.Event()

        def worker():
            report("from other thread")   # other thread has no sink -> ignored
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        done.wait(timeout=2)
        t.join()
        report("from main")
    assert got == ["from main"]


def test_sink_failure_never_propagates():
    def boom(_msg):
        raise RuntimeError("sink broke")

    with progress_to(boom):
        report("should be swallowed")     # must not raise
