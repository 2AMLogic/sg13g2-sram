#!/usr/bin/env python3
"""Tests for check_readme_spec_table.py, including a negative control.

Run: python3 -I scripts/test_check_readme_spec_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_readme_spec_table as chk  # noqa: E402

ROOT = chk.ROOT


def main() -> int:
    readme = (ROOT / "README.md").read_text()
    spec = (ROOT / "spec/sram.md").read_text()
    assert len(chk.spec_table(spec)) >= 3, "spec table not parsed"
    assert chk.diff(readme, spec) == [], chk.diff(readme, spec)
    # negative control: one mutated cell, a dropped row, a missing table
    assert chk.diff(readme.replace("1.08 / 1.20 / 1.32 V", "1.0 / 1.2 / 1.4 V", 1), spec)
    assert chk.diff(readme.replace("| Corners |", "| Corner |", 1), spec)
    assert chk.diff("no table here", spec)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
