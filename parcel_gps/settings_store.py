from __future__ import annotations

from qgis.core import QgsSettings

from .core.presentation import DEFAULT_BASEMAP, normalize_basemap_choice

API_KEY_SETTING = "parcel_gps/api_key"
COUNTRY_SETTING = "parcel_gps/country"
BASEMAP_SETTING = "parcel_gps/basemap"


def load_api_key() -> str:
    return str(QgsSettings().value(API_KEY_SETTING, "") or "").strip()


def save_api_key(api_key: str) -> None:
    settings = QgsSettings()
    if api_key.strip():
        settings.setValue(API_KEY_SETTING, api_key.strip())
    else:
        settings.remove(API_KEY_SETTING)


def load_country() -> str:
    return str(QgsSettings().value(COUNTRY_SETTING, "") or "")


def save_country(code: str) -> None:
    QgsSettings().setValue(COUNTRY_SETTING, code or "")


def load_basemap() -> str:
    return normalize_basemap_choice(QgsSettings().value(BASEMAP_SETTING, DEFAULT_BASEMAP))


def save_basemap(choice: str) -> None:
    QgsSettings().setValue(BASEMAP_SETTING, normalize_basemap_choice(choice))
