from __future__ import annotations

from collections.abc import Mapping

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .core.transport import HttpResponse, TransportFailure, TransportTimeout

MILLISECONDS = 1000


def qgis_transport(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = QNetworkRequest(QUrl(url))
    for name, value in headers.items():
        request.setRawHeader(name.encode("ascii"), value.encode("utf-8"))
    if hasattr(request, "setTransferTimeout"):
        request.setTransferTimeout(int(timeout * MILLISECONDS))
    blocking = QgsBlockingNetworkRequest()
    outcome = blocking.get(request, True)
    reply = blocking.reply()
    status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
    if status is not None and int(status) > 0:
        response_headers = {
            bytes(name).decode("latin-1"): bytes(reply.rawHeader(name)).decode("latin-1")
            for name in reply.rawHeaderList()
        }
        return HttpResponse(int(status), bytes(reply.content()), response_headers)
    if outcome == QgsBlockingNetworkRequest.TimeoutError:
        raise TransportTimeout(blocking.errorMessage())
    raise TransportFailure(blocking.errorMessage() or "Network request failed")
