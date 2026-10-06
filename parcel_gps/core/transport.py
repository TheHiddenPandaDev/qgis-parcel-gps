from __future__ import annotations

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
