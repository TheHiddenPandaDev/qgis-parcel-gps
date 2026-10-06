from __future__ import annotations

import importlib
import sys
import types

import pytest

STORED_PATH = "parcel_gps/api_key"
STORED_VALUE = "pk_live_existing_install"


class FakeSettings:
    store: dict[str, object] = {}

    def value(self, path, default=None):
        return self.store.get(path, default)

    def setValue(self, path, value):
        self.store[path] = value

    def remove(self, path):
        self.store.pop(path, None)


@pytest.fixture
def settings_store(monkeypatch):
    FakeSettings.store = {}
    qgis = types.ModuleType("qgis")
    qgis_core = types.ModuleType("qgis.core")
    qgis_core.QgsSettings = FakeSettings
    qgis.core = qgis_core
    monkeypatch.setitem(sys.modules, "qgis", qgis)
    monkeypatch.setitem(sys.modules, "qgis.core", qgis_core)
    monkeypatch.delitem(sys.modules, "parcel_gps.settings_store", raising=False)
    yield importlib.import_module("parcel_gps.settings_store")
    sys.modules.pop("parcel_gps.settings_store", None)


def test_existing_install_keeps_its_stored_key(settings_store):
    FakeSettings.store[STORED_PATH] = f"  {STORED_VALUE} "

    assert settings_store.load_api_key() == STORED_VALUE


def test_saving_writes_to_the_same_path_existing_installs_use(settings_store):
    settings_store.save_api_key(f" {STORED_VALUE} ")

    assert FakeSettings.store == {STORED_PATH: STORED_VALUE}


def test_saving_a_blank_key_removes_it(settings_store):
    FakeSettings.store[STORED_PATH] = STORED_VALUE

    settings_store.save_api_key("   ")

    assert STORED_PATH not in FakeSettings.store
    assert settings_store.load_api_key() == ""


def test_country_and_basemap_round_trip(settings_store):
    settings_store.save_country("PT")
    settings_store.save_basemap("streets")

    assert settings_store.load_country() == "PT"
    assert settings_store.load_basemap() == "streets"
