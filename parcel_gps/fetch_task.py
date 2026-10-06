from __future__ import annotations


from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from .core.batch import BatchJob, BatchRunner, BatchSummary
from .core.client import ParcelGpsClient
from .core.service import ParcelService
from .qgis_transport import qgis_transport

PERCENT = 100.0


class FetchTask(QgsTask):
    outcome_ready = pyqtSignal(object)
    done = pyqtSignal(object)

    def __init__(
        self,
        description: str,
        api_key: str,
        jobs: list[BatchJob],
        point: tuple[float, float] | None = None,
    ) -> None:
        super().__init__(description, QgsTask.CanCancel)
        self._api_key = api_key
        self._jobs = jobs
        self._point = point
        self.summary: BatchSummary | None = None
        self.quota: dict | None = None
        self.error: Exception | None = None

    @property
    def job_count(self) -> int:
        return len(self._jobs)

    def run(self) -> bool:
        try:
            client = ParcelGpsClient(self._api_key, transport=qgis_transport)
            service = ParcelService(client)
            runner = BatchRunner(
                self._fetcher(service),
                is_cancelled=self.isCanceled,
                quota_provider=lambda: client.last_quota,
            )
            self.summary = runner.run(self._jobs, self.outcome_ready.emit, self._report_progress)
            self.quota = client.last_quota
            return True
        except Exception as error:
            self.error = error
            return False

    def finished(self, result: bool) -> None:
        self.done.emit(self)

    def _fetcher(self, service: ParcelService):
        if self._point is None:
            return service.by_reference
        lat, lng = self._point
        return lambda _reference, country: service.at_point(lat, lng, country)

    def _report_progress(self, done: int, total: int) -> None:
        if total:
            self.setProgress(PERCENT * done / total)
