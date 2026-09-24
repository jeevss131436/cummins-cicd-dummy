#!/usr/bin/env python3
"""Create a blank DCH Excel sheet with the Assets and Audit sheets.

Owner: Teammate 4. Run once from the repo root, then commit the file:
    python dch-cli/create_registry.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from excel_registry import create_workbook

DEFAULT_WORKBOOK = "dch/dch_registry.xlsx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a blank DCH Excel sheet.")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help=f"Where to write it (default: {DEFAULT_WORKBOOK})")
    parser.add_argument("--force", action="store_true", help="Replace an existing workbook with a blank one")
    args = parser.parse_args(argv)

    path = Path(args.workbook)
    if path.exists() and not args.force:
        print(f"{path} already exists. Add --force to replace it with a blank sheet.", file=sys.stderr)
        return 1

    create_workbook(path)
    print(f"Created {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
