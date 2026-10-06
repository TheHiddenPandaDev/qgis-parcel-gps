from __future__ import annotations

import os

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QCoreApplication, QTranslator

CONTEXT = "ParcelGps"
I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")


def tr(text: str) -> str:
    return QCoreApplication.translate(CONTEXT, text)


def install_translator() -> QTranslator | None:
    locale = str(QgsSettings().value("locale/userLocale", "") or "")[:2]
    path = os.path.join(I18N_DIR, f"parcel_gps_{locale}.qm")
    if not locale or not os.path.exists(path):
        return None
    translator = QTranslator()
    if not translator.load(path):
        return None
    QCoreApplication.installTranslator(translator)
    return translator
