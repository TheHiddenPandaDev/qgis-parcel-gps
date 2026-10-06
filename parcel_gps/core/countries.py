from __future__ import annotations

COUNTRY_NAMES: dict[str, str] = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "CH": "Switzerland",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GR": "Greece",
    "HR": "Croatia",
    "IE": "Ireland",
    "IS": "Iceland",
    "IT": "Italy",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "NA": "Spain - Navarre",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "PV": "Spain - Basque Country",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "UK": "United Kingdom (Scotland)",
}

FORAL_CADASTRES = frozenset({"PV", "NA"})
COORDINATES_ONLY = frozenset({"UK", "HR"})
COUNTRY_CODES = tuple(sorted(COUNTRY_NAMES, key=lambda code: COUNTRY_NAMES[code]))
REFERENCE_COUNTRY_CODES = tuple(code for code in COUNTRY_CODES if code not in COORDINATES_ONLY)
PUBLIC_COUNTRY_COUNT = len(COUNTRY_NAMES) - len(FORAL_CADASTRES)
COUNTRY_ALIASES = {"GB": "UK", "EL": "GR"}


def normalize_country(value: object) -> str | None:
    if value is None:
        return None
    code = str(value).strip().upper()
    if not code:
        return None
    code = COUNTRY_ALIASES.get(code, code)
    return code if code in COUNTRY_NAMES else None


def supports_reference(code: str | None) -> bool:
    return code is None or code not in COORDINATES_ONLY


def country_label(code: str | None) -> str:
    if code is None:
        return ""
    return COUNTRY_NAMES.get(code, code)
