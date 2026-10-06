from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable
from collections.abc import Iterable

from .countries import normalize_country
from .errors import AuthenticationError, ForbiddenError, ParcelGpsError, QuotaExceededError, RateLimitError
from .parsing import ParcelRecord

DEFAULT_RATE_LIMIT_WAIT_SECONDS = 10.0
MAX_RATE_LIMIT_WAIT_SECONDS = 60.0
MAX_RATE_LIMIT_RETRIES = 5
WAIT_SLICE_SECONDS = 0.5
EMPTY_MARKERS = frozenset({"", "NULL", "NONE", "NAN"})
FATAL_ERRORS = (QuotaExceededError, AuthenticationError, ForbiddenError)


@dataclass(frozen=True)
class BatchJob:
    reference: str
    country: str | None = None


@dataclass(frozen=True)
class BatchOutcome:
    job: BatchJob
    record: ParcelRecord | None = None
    error: ParcelGpsError | None = None

    @property
    def ok(self) -> bool:
        return self.record is not None


@dataclass
class BatchSummary:
    total: int = 0
    fetched: int = 0
    failed: int = 0
    cancelled: bool = False
    stopped_by: ParcelGpsError | None = None
    failures: list[BatchOutcome] = field(default_factory=list)

    @property
    def not_processed(self) -> int:
        return self.total - self.fetched - self.failed


def clean_reference(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != value:
            return None
        text = str(int(value)) if value.is_integer() else str(value)
    else:
        text = str(value)
    cleaned = " ".join(text.split())
    return None if cleaned.upper() in EMPTY_MARKERS else cleaned


def build_jobs(rows: Iterable[tuple[Any, Any]], default_country: str | None = None) -> list[BatchJob]:
    jobs: list[BatchJob] = []
    seen: set[tuple[str, str | None]] = set()
    fallback = normalize_country(default_country)
    for raw_reference, raw_country in rows:
        reference = clean_reference(raw_reference)
        if reference is None:
            continue
        country = normalize_country(clean_reference(raw_country)) or fallback
        key = (reference.upper(), country)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(BatchJob(reference, country))
    return jobs


class BatchRunner:
    def __init__(
        self,
        fetch: Callable[[str, str | None], ParcelRecord],
        *,
        sleep: Callable[[float], None] = time.sleep,
        is_cancelled: Callable[[], bool] = lambda: False,
        quota_provider: Callable[[], dict | None] = lambda: None,
        max_rate_limit_retries: int = MAX_RATE_LIMIT_RETRIES,
        default_wait: float = DEFAULT_RATE_LIMIT_WAIT_SECONDS,
        max_wait: float = MAX_RATE_LIMIT_WAIT_SECONDS,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep
        self._is_cancelled = is_cancelled
        self._quota_provider = quota_provider
        self._max_retries = max_rate_limit_retries
        self._default_wait = default_wait
        self._max_wait = max_wait

    def run(
        self,
        jobs: list[BatchJob],
        on_result: Callable[[BatchOutcome], None] = lambda outcome: None,
        on_progress: Callable[[int, int], None] = lambda done, total: None,
    ) -> BatchSummary:
        summary = BatchSummary(total=len(jobs))
        for index, job in enumerate(jobs):
            if self._is_cancelled():
                summary.cancelled = True
                break
            self._respect_burst_limit()
            outcome = self._run_job(job)
            if outcome is None:
                summary.cancelled = True
                break
            if outcome.ok:
                summary.fetched += 1
            else:
                summary.failed += 1
                summary.failures.append(outcome)
            on_result(outcome)
            on_progress(index + 1, len(jobs))
            if isinstance(outcome.error, FATAL_ERRORS):
                summary.stopped_by = outcome.error
                break
        return summary

    def _run_job(self, job: BatchJob) -> BatchOutcome | None:
        attempts = 0
        while True:
            try:
                return BatchOutcome(job, record=self._fetch(job.reference, job.country))
            except RateLimitError as error:
                attempts += 1
                if attempts > self._max_retries:
                    return BatchOutcome(job, error=error)
                if not self._wait(error.retry_after or self._default_wait * attempts):
                    return None
            except ParcelGpsError as error:
                return BatchOutcome(job, error=error)

    def _respect_burst_limit(self) -> None:
        quota = self._quota_provider() or {}
        if quota.get("rate_remaining") == 0:
            self._wait(quota.get("rate_reset_seconds") or self._default_wait)

    def _wait(self, seconds: float) -> bool:
        remaining = min(max(float(seconds), 0.0), self._max_wait)
        while remaining > 0:
            if self._is_cancelled():
                return False
            step = min(WAIT_SLICE_SECONDS, remaining)
            self._sleep(step)
            remaining -= step
        return not self._is_cancelled()
