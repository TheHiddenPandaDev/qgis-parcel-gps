from __future__ import annotations

import json
from typing import Any

import pytest

from parcel_gps.core.client import ParcelGpsClient
from parcel_gps.core.transport import HttpResponse

API_KEY = "pk_live_secret_test_key"


def json_response(status: int, payload: Any, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), headers or {})


class FakeTransport:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if not self.responses:
            raise AssertionError(f"unexpected request {url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def urls(self) -> list[str]:
        return [call["url"] for call in self.calls]


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(sleeps: list[float]):
    def factory(*responses: Any, **kwargs: Any) -> tuple[ParcelGpsClient, FakeTransport]:
        transport = FakeTransport(*responses)
        client = ParcelGpsClient(API_KEY, transport=transport, sleep=sleeps.append, **kwargs)
        return client, transport

    return factory
