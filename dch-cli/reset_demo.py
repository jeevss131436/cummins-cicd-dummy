#!/usr/bin/env python3
"""Empty the demo volume and reset the DCH sheet to headers only.

Owner: Teammate 5. Run by .github/workflows/dch-reset.yml. It deletes every file and
folder under the volume path but never the volume itself.
"""
from __future__ import annotations

import argparse
import os
import sys

from excel_registry import create_workbook
from volume_reader import parse_volume_path

DEFAULT_WORKBOOK = "dch/dch_registry.xlsx"


def delete_contents(client, root: str) -> tuple[int, int]:
    """Delete everything under root. Returns (files deleted, folders deleted)."""
    root = root.rstrip("/")
    files: list[str] = []
    folders: list[str] = []
    to_visit = [root]
    while to_visit:
        directory = to_visit.pop()
        for entry in client.files.list_directory_contents(directory):
            if entry.is_directory:
                folder = entry.path.rstrip("/")
                folders.append(folder)
                to_visit.append(folder)
            else:
                files.append(entry.path)

    for path in files:
        client.files.delete(path)
    # A folder must be empty before it can be deleted, so remove the deepest ones first.
    for folder in sorted(folders, key=lambda p: p.count("/"), reverse=True):
        client.files.delete_directory(folder)
    return len(files), len(folders)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset the DCH demo volume and sheet.")
    parser.add_argument("--path", default=os.environ.get("DCH_VOLUME_PATH"), help="Volume folder to empty (default: $DCH_VOLUME_PATH)")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help=f"Excel file to reset (default: {DEFAULT_WORKBOOK})")
    args = parser.parse_args(argv)

    if not args.path:
        parser.error("--path is required (or set DCH_VOLUME_PATH)")
    parse_volume_path(args.path)  # refuses anything that isn't a /Volumes/... path

    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()
    n_files, n_folders = delete_contents(client, args.path)
    create_workbook(args.workbook)

    text = (
        "## DCH demo reset\n\n"
        f"Deleted {n_files} file(s) and {n_folders} folder(s) under `{args.path}`.\n\n"
        f"`{args.workbook}` is back to headers only."
    )
    print(text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
