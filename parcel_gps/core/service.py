from __future__ import annotations

from .client import ParcelGpsClient
from .countries import normalize_country, supports_reference
from .errors import NoOutlineError, NotFoundError
from .parsing import ParcelRecord, parse_parcel, reference_at_point


class ParcelService:
    def __init__(self, client: ParcelGpsClient) -> None:
        self._client = client

    @property
    def client(self) -> ParcelGpsClient:
        return self._client

    def by_reference(self, reference: str, country: str | None = None) -> ParcelRecord:
        code = normalize_country(country)
        cleaned = " ".join((reference or "").split())
        record = parse_parcel(self._client.get_parcel(cleaned, code), cleaned, code)
        if record.has_outline:
            return record
        outline = parse_parcel(self._client.get_polygon(cleaned, record.country or code), cleaned, record.country)
        merged = record.merged_with(outline)
        if not merged.has_outline:
            raise NoOutlineError("The API returned this parcel without an outline.", details={"reference": cleaned})
        return merged

    def at_point(self, lat: float, lng: float, country: str | None = None) -> ParcelRecord:
        code = normalize_country(country)
        data = self._client.parcel_at(lat, lng, code)
        point_record = parse_parcel(data, "", code)
        if point_record.has_outline and point_record.reference:
            return point_record
        reference, found_country = reference_at_point(data)
        if not reference:
            raise NotFoundError("No cadastral parcel was found at this point.")
        found_country = found_country or code
        if not supports_reference(found_country):
            raise NoOutlineError(
                "This country is covered by coordinates only: no outline is available.",
                details={"reference": reference, "country": found_country},
            )
        return self.by_reference(reference, found_country).merged_with(point_record)
