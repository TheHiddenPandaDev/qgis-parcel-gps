from __future__ import annotations

import pytest

from parcel_gps.core.batch import BatchJob, BatchRunner, build_jobs, clean_reference
from parcel_gps.core.errors import (
    AuthenticationError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)
from parcel_gps.core.parsing import ParcelRecord


class ScriptedFetch:
    def __init__(self, script):
        self.script = dict(script)
        self.calls = []

    def __call__(self, reference, country):
        self.calls.append((reference, country))
        steps = self.script.get(reference)
        step = steps.pop(0) if isinstance(steps, list) else steps
        if isinstance(step, Exception):
            raise step
        return ParcelRecord(reference, country)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (True, None),
        (float("nan"), None),
        (12345.0, "12345"),
        (12.5, "12.5"),
        (987, "987"),
        ("  9872023VH5797S  0001WX ", "9872023VH5797S 0001WX"),
        ("NULL", None),
        ("", None),
        ("nan", None),
    ],
)
def test_clean_reference(value, expected):
    assert clean_reference(value) == expected


def test_build_jobs_dedupes_skips_empty_and_applies_countries():
    rows = [
        ("A1", None),
        ("a1", None),
        ("A1", "fr"),
        (None, "ES"),
        ("B2", "XX"),
        ("C3", "gb"),
        ("D4", "NULL"),
    ]

    jobs = build_jobs(rows, default_country="ES")

    assert jobs == [
        BatchJob("A1", "ES"),
        BatchJob("A1", "FR"),
        BatchJob("B2", "ES"),
        BatchJob("C3", "UK"),
        BatchJob("D4", "ES"),
    ]


def test_build_jobs_without_default_country():
    assert build_jobs([("A1", "")]) == [BatchJob("A1", None)]


def test_runner_collects_results_and_failures():
    fetch = ScriptedFetch({"A": None, "B": NotFoundError("missing"), "C": ServerError("boom", status=500)})
    seen, progress = [], []

    summary = BatchRunner(fetch, sleep=lambda s: None).run(
        [BatchJob("A"), BatchJob("B"), BatchJob("C")], seen.append, lambda done, total: progress.append((done, total))
    )

    assert summary.total == 3
    assert summary.fetched == 1
    assert summary.failed == 2
    assert summary.not_processed == 0
    assert [outcome.ok for outcome in seen] == [True, False, False]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert summary.stopped_by is None
    assert [failure.job.reference for failure in summary.failures] == ["B", "C"]


def test_runner_waits_and_retries_on_burst_limit():
    sleeps = []
    fetch = ScriptedFetch({"A": [RateLimitError("slow down", status=429, retry_after=2), None]})

    summary = BatchRunner(fetch, sleep=sleeps.append).run([BatchJob("A")])

    assert summary.fetched == 1
    assert sum(sleeps) == pytest.approx(2.0)
    assert all(step <= 0.5 for step in sleeps)


def test_runner_uses_growing_default_wait_without_retry_after():
    sleeps = []
    fetch = ScriptedFetch({"A": [RateLimitError("x", status=429), RateLimitError("x", status=429), None]})

    BatchRunner(fetch, sleep=sleeps.append, default_wait=1.0).run([BatchJob("A")])

    assert sum(sleeps) == pytest.approx(3.0)


def test_runner_caps_wait_and_gives_up_after_retries():
    sleeps = []
    errors = [RateLimitError("x", status=429, retry_after=999) for _ in range(3)]
    fetch = ScriptedFetch({"A": errors, "B": None})

    summary = BatchRunner(fetch, sleep=sleeps.append, max_rate_limit_retries=2, max_wait=1.0).run(
        [BatchJob("A"), BatchJob("B")]
    )

    assert summary.failed == 1
    assert summary.fetched == 1
    assert sum(sleeps) == pytest.approx(2.0)


@pytest.mark.parametrize("fatal", [QuotaExceededError("quota", status=429), AuthenticationError("key", status=401)])
def test_runner_stops_on_fatal_errors(fatal):
    fetch = ScriptedFetch({"A": None, "B": fatal, "C": None})

    summary = BatchRunner(fetch, sleep=lambda s: None).run([BatchJob("A"), BatchJob("B"), BatchJob("C")])

    assert summary.stopped_by is fatal
    assert summary.fetched == 1
    assert summary.failed == 1
    assert summary.not_processed == 1
    assert fetch.calls == [("A", None), ("B", None)]


def test_runner_respects_exhausted_burst_window_before_next_call():
    sleeps = []
    quotas = iter([{"rate_remaining": 0, "rate_reset_seconds": 1}, {"rate_remaining": 0}, {}])

    BatchRunner(
        ScriptedFetch({"A": None, "B": None, "C": None}),
        sleep=sleeps.append,
        quota_provider=lambda: next(quotas),
        default_wait=2.0,
    ).run([BatchJob("A"), BatchJob("B"), BatchJob("C")])

    assert sum(sleeps) == pytest.approx(3.0)


def test_runner_cancelled_before_start():
    fetch = ScriptedFetch({"A": None})

    summary = BatchRunner(fetch, is_cancelled=lambda: True).run([BatchJob("A")])

    assert summary.cancelled
    assert fetch.calls == []
    assert summary.not_processed == 1


def test_runner_cancel_during_rate_limit_wait_stops_quickly():
    sleeps = []
    flag = {"cancel": False}

    def sleep(step):
        sleeps.append(step)
        flag["cancel"] = True

    fetch = ScriptedFetch({"A": [RateLimitError("x", status=429, retry_after=30), None], "B": None})

    summary = BatchRunner(fetch, sleep=sleep, is_cancelled=lambda: flag["cancel"]).run([BatchJob("A"), BatchJob("B")])

    assert summary.cancelled
    assert summary.fetched == 0
    assert len(sleeps) == 1
    assert fetch.calls == [("A", None)]


def test_wait_returns_false_when_cancelled_at_once():
    runner = BatchRunner(lambda r, c: ParcelRecord(r), is_cancelled=lambda: True)

    assert runner._wait(5) is False
    assert runner._wait(0) is False
