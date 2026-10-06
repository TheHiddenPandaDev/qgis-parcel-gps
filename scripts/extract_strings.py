from __future__ import annotations

import ast
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "parcel_gps"


def tr_strings() -> list[str]:
    found: list[str] = []
    for path in sorted(PLUGIN_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value not in found
            ):
                found.append(node.args[0].value)
    return found


if __name__ == "__main__":
    for text in tr_strings():
        sys.stdout.write(f"{text!r}\n")
