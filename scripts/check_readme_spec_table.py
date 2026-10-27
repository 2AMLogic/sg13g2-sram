#!/usr/bin/env python3
"""Fail if the README's spec table differs from the table in spec/sram.md.

The table is the first Markdown table whose header row starts with
"| Parameter". Rows are compared cell by cell, whitespace-normalised.

Run: python3 -I scripts/check_readme_spec_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def spec_table(text: str) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("| Parameter"):
            inside = True
        elif inside and not line.startswith("|"):
            break
        if inside:
            rows.append(tuple(" ".join(c.split()) for c in line.strip().strip("|").split("|")))
    return rows


def diff(readme: str, spec: str) -> list[str]:
    a, b = spec_table(readme), spec_table(spec)
    if not a:
        return ["README.md has no spec table (header row starting '| Parameter')"]
    if not b:
        return ["spec/sram.md has no spec table (header row starting '| Parameter')"]
    errs = []
    for i in range(max(len(a), len(b))):
        ra = a[i] if i < len(a) else None
        rb = b[i] if i < len(b) else None
        if ra != rb:
            errs.append(f"row {i}: README {ra!r} != spec {rb!r}")
    return errs


def main() -> int:
    errs = diff((ROOT / "README.md").read_text(), (ROOT / "spec/sram.md").read_text())
    for e in errs:
        print(f"check_readme_spec_table: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
