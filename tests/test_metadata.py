from __future__ import annotations

import configparser
import re
from pathlib import Path

from parcel_gps.core.client import PLUGIN_VERSION

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "parcel_gps"
ENUM_OWNERS = (
    "Qt",
    "Qgis",
    "QLineEdit",
    "QMessageBox",
    "QNetworkRequest",
    "QgsTask",
    "QgsFeatureRequest",
    "QgsVectorFileWriter",
    "QgsBlockingNetworkRequest",
    "QgsMapLayerProxyModel",
)
UNSCOPED_ENUM = re.compile(rf"\b(?:{'|'.join(ENUM_OWNERS)})\.[A-Za-z]+\b(?![.(])")
REQUIRED_KEYS = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
    "tracker",
    "homepage",
    "tags",
    "icon",
)


def _metadata() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
    return parser["general"]


def test_metadata_has_required_keys_and_matching_version():
    metadata = _metadata()

    assert all(metadata.get(key) for key in REQUIRED_KEYS)
    assert metadata["version"] == PLUGIN_VERSION
    assert metadata["qgisMinimumVersion"] == "3.22"
    assert metadata["qgisMaximumVersion"] == "4.99"
    assert "supportsQt6" not in metadata
    assert (PLUGIN_DIR / metadata["icon"]).exists()


def test_public_wording_uses_29_countries():
    text = (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8")

    assert "29 European countries" in text
    assert " 21 " not in text and " 31 " not in text


def test_every_language_has_a_compiled_translation():
    for language in ("es", "fr", "de", "it"):
        assert (PLUGIN_DIR / "i18n" / f"parcel_gps_{language}.qm").stat().st_size > 0


def test_qt_imports_go_through_the_qgis_shim():
    for module in PLUGIN_DIR.rglob("*.py"):
        source = module.read_text(encoding="utf-8")

        assert "PyQt5" not in source and "PyQt6" not in source.replace("qgis.PyQt", ""), module.name


def test_qt_enums_are_fully_scoped():
    for module in PLUGIN_DIR.glob("*.py"):
        source = module.read_text(encoding="utf-8")

        assert UNSCOPED_ENUM.findall(source) == [], module.name
