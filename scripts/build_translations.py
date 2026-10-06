from __future__ import annotations

import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from extract_strings import PLUGIN_DIR, tr_strings
from translations import LANGUAGES

CONTEXT = "ParcelGps"
I18N_DIR = PLUGIN_DIR / "i18n"


def ts_document(language: str, translations: dict[str, str], sources: list[str]) -> str:
    messages = "".join(
        f"    <message>\n        <source>{escape(text)}</source>\n"
        f"        <translation>{escape(translations[text])}</translation>\n    </message>\n"
        for text in sources
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        f'<TS version="2.1" language="{language}">\n<context>\n    <name>{CONTEXT}</name>\n'
        f"{messages}</context>\n</TS>\n"
    )


def lrelease_binary() -> str:
    for name in ("lrelease", "pyside6-lrelease", "lrelease-qt5"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("lrelease not found: pip install pyside6-essentials")


def main() -> None:
    sources = tr_strings()
    I18N_DIR.mkdir(exist_ok=True)
    lrelease = lrelease_binary()
    for language, translations in LANGUAGES.items():
        missing = [text for text in sources if text not in translations]
        if missing:
            sys.exit(f"{language}: missing translations for {missing}")
        ts_path = I18N_DIR / f"parcel_gps_{language}.ts"
        ts_path.write_text(ts_document(language, translations, sources), encoding="utf-8")
        subprocess.run([lrelease, str(ts_path), "-qm", str(ts_path.with_suffix(".qm"))], check=True)


if __name__ == "__main__":
    main()
