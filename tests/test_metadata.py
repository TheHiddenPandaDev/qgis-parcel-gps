from __future__ import annotations

import configparser
from pathlib import Path

from parcel_gps.core.client import PLUGIN_VERSION

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "parcel_gps"
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
    assert (PLUGIN_DIR / metadata["icon"]).exists()


def test_public_wording_uses_29_countries():
    text = (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8")

    assert "29 European countries" in text
    assert " 21 " not in text and " 31 " not in text


def test_every_language_has_a_compiled_translation():
    for language in ("es", "fr", "de", "it"):
        assert (PLUGIN_DIR / "i18n" / f"parcel_gps_{language}.qm").stat().st_size > 0
