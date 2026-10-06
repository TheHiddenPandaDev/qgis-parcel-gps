from __future__ import annotations

import json
import math
import time
from typing import Any, Callable
from collections.abc import Mapping
from urllib.parse import quote, urlencode

from .errors import (
    NetworkError,
    ParcelGpsError,
    RequestTimeoutError,
    ServerError,
    ValidationError,
    error_from_response,
)
from .transport import HttpResponse, Transport, TransportFailure, TransportTimeout, urllib_transport

DEFAULT_BASE_URL = "https://api.parcelgps.com"
DEVELOPER_PORTAL_URL = "https://www.parcelgps.com/developers"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 1.0
RETRYABLE_STATUS = frozenset({502, 503, 504})
MAX_REFERENCE_LENGTH = 64
HTTP_OK_MAX = 299
PLUGIN_VERSION = "0.3.0"
USER_AGENT = f"parcel-gps-qgis/{PLUGIN_VERSION}"


class ParcelGpsClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Transport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = USER_AGENT,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ValidationError("An API key is required.", code="NO_API_KEY")
        self._api_key = key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport or urllib_transport
        self._max_retries = max(0, max_retries)
        self._sleep = sleep
        self._user_agent = user_agent
        self.last_quota: dict[str, Any] | None = None

    def __repr__(self) -> str:
        return f"ParcelGpsClient(base_url={self._base_url!r}, api_key='***')"

    def get_parcel(self, reference: str, country: str | None = None) -> dict[str, Any]:
        return self._get(_parcel_path(reference), {"country": country})

    def get_polygon(self, reference: str, country: str | None = None) -> dict[str, Any]:
        return self._get(_parcel_path(reference, "/polygon"), {"country": country})

    def parcel_at(self, lat: float, lng: float, country: str | None = None) -> dict[str, Any]:
        if not (_finite(lat) and _finite(lng)) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValidationError("Latitude and longitude must be valid WGS84 numbers.")
        return self._get("/api/search/coordinates", {"lat": f"{lat:.7f}", "lng": f"{lng:.7f}", "country": country})

    def _get(self, path: str, query: Mapping[str, Any]) -> dict[str, Any]:
        params = {key: value for key, value in query.items() if value not in (None, "")}
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        attempt = 0
        while True:
            try:
                return self._once(url)
            except (ServerError, RequestTimeoutError, NetworkError) as error:
                if not self._retryable(error) or attempt >= self._max_retries:
                    raise
                self._sleep(error.retry_after or BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1

    def _retryable(self, error: ParcelGpsError) -> bool:
        return isinstance(error, (RequestTimeoutError, NetworkError)) or error.status in RETRYABLE_STATUS

    def _once(self, url: str) -> dict[str, Any]:
        headers = {"X-API-Key": self._api_key, "Accept": "application/json", "User-Agent": self._user_agent}
        try:
            response = self._transport(url, headers, self._timeout)
        except TransportTimeout as error:
            raise RequestTimeoutError("The Parcel GPS API did not answer in time.") from error
        except TransportFailure as error:
            raise NetworkError(f"Could not reach the Parcel GPS API: {error}") from error
        quota = read_quota(response)
        if quota:
            self.last_quota = quota
        payload = _json(response.body)
        if response.status > HTTP_OK_MAX:
            raise error_from_response(response.status, payload, _retry_after(response))
        data = payload.get("data", payload)
        return data if isinstance(data, dict) else {}


def _parcel_path(reference: str, suffix: str = "") -> str:
    cleaned = " ".join((reference or "").split())
    if not cleaned:
        raise ValidationError("The cadastral reference is empty.")
    if len(cleaned) > MAX_REFERENCE_LENGTH:
        raise ValidationError("The cadastral reference is too long.")
    return f"/api/catastro/{quote(cleaned, safe='')}{suffix}"


def read_quota(response: HttpResponse) -> dict[str, Any]:
    quota: dict[str, Any] = {}
    plan = response.header("X-Quota-Tier")
    if plan:
        quota["plan"] = plan
    for key, header in (
        ("limit", "X-Quota-Limit"),
        ("remaining", "X-Quota-Remaining"),
        ("rate_limit", "X-RateLimit-Limit"),
        ("rate_remaining", "X-RateLimit-Remaining"),
        ("rate_reset_seconds", "X-RateLimit-Reset"),
    ):
        value = _integer(response.header(header))
        if value is not None:
            quota[key] = value
    reset = response.header("X-Quota-Reset")
    if reset:
        quota["resets_at"] = reset
    return quota


def _integer(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return int(value) if math.isfinite(value) else None


def _retry_after(response: HttpResponse) -> float | None:
    for header in ("Retry-After", "X-RateLimit-Reset"):
        value = _integer(response.header(header))
        if value is not None and value > 0:
            return float(value)
    return None


def _json(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
