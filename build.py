#!/usr/bin/env python3
"""Construit dist/livraddict-<version>.zip, prêt à charger dans Calibre."""
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
FICHIERS = ["__init__.py", "parser.py", "plugin-import-name-livraddict.txt"]


def version() -> str:
    m = re.search(r"version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)", (SRC / "__init__.py").read_text(encoding="utf-8"))
    return ".".join(m.groups())


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"livraddict-{version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FICHIERS:
            z.write(SRC / f, f)
    print(out)


if __name__ == "__main__":
    main()
