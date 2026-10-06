from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from collections.abc import Mapping


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None


class TransportTimeout(Exception):
    pass


class TransportFailure(Exception):
    pass


Transport = Callable[[str, Mapping[str, str], float], HttpResponse]


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.read(), dict(response.headers.items()))
    except urllib.error.HTTPError as error:
        body = error.read() if error.fp is not None else b""
        return HttpResponse(error.code, body, dict(error.headers.items()) if error.headers else {})
    except (socket.timeout, TimeoutError) as error:
        raise TransportTimeout(str(error)) from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise TransportTimeout(str(error.reason)) from error
        raise TransportFailure(str(error.reason)) from error
    except OSError as error:
        raise TransportFailure(str(error)) from error
