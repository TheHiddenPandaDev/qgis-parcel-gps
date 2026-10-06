from __future__ import annotations

import configparser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "parcel_gps"
DIST_DIR = ROOT / "dist"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
REQUIRED_FILES = ("__init__.py", "metadata.txt", "icon.png", "LICENSE")


def plugin_version() -> str:
    parser = configparser.ConfigParser()
    parser.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
    return parser["general"]["version"]


def packaged_files() -> list[Path]:
    files = []
    for path in sorted(PLUGIN_DIR.rglob("*")):
        relative = path.relative_to(PLUGIN_DIR)
        if path.is_dir() or path.suffix in EXCLUDED_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS or part.startswith(".") for part in relative.parts):
            continue
        files.append(path)
    return files


def main() -> None:
    missing = [name for name in REQUIRED_FILES if not (PLUGIN_DIR / name).exists()]
    if missing:
        raise SystemExit(f"missing in plugin folder: {missing}")
    DIST_DIR.mkdir(exist_ok=True)
    target = DIST_DIR / f"parcel_gps-{plugin_version()}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in packaged_files():
            archive.write(path, Path(PLUGIN_DIR.name) / path.relative_to(PLUGIN_DIR))
    print(target)


if __name__ == "__main__":
    main()
