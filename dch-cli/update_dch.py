#!/usr/bin/env python3
"""Compare the Databricks landing volume with the DCH Excel sheet and update the sheet.

Owner: Teammate 3. Run by .github/workflows/dch-excel.yml, or locally from the repo root:

    python dch-cli/update_dch.py --path /Volumes/<catalog>/dch_demo/landing/ --dry-run

Credentials come from DATABRICKS_HOST and DATABRICKS_TOKEN, or from your
`databricks auth login` profile when you run it on your own machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from excel_registry import ExcelRegistry
from volume_reader import VolumeFile, build_urn, group_datasets, list_files, normalize

DEFAULT_WORKBOOK = "dch/dch_registry.xlsx"
DEFAULT_METADATA = "metadata/datasets.json"

# Every dataset needs these before it is added to the sheet.
REQUIRED_METADATA = ["data_product_name", "owner", "domain", "description"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update the DCH Excel sheet from a Databricks volume.")
    parser.add_argument(
        "--path",
        default=os.environ.get("DCH_VOLUME_PATH"),
        help="Volume folder to scan, e.g. /Volumes/workspace/dch_demo/landing/ (default: $DCH_VOLUME_PATH)",
    )
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help=f"Excel file to update (default: {DEFAULT_WORKBOOK})")
    parser.add_argument("--metadata", default=DEFAULT_METADATA, help=f"Dataset metadata JSON (default: {DEFAULT_METADATA})")
    parser.add_argument("--env", default="dev", help="Environment name used in the URN (default: dev)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving the sheet")
    args = parser.parse_args(argv)
    if not args.path:
        parser.error("--path is required (or set DCH_VOLUME_PATH)")
    return args


def load_metadata(path: str | Path) -> dict:
    """Read the metadata file, keyed by dataset name. A missing file means no metadata."""
    path = Path(path)
    if not path.exists():
        print(f"Warning: metadata file {path} not found. Every dataset will fail validation.", file=sys.stderr)
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {normalize(key): value for key, value in raw.items()}


def reconcile(
    files: list[VolumeFile], volume_path: str, registry: ExcelRegistry, metadata: dict, env: str = "dev"
) -> dict:
    """Apply every dataset in the volume to the registry. Returns a summary dict."""
    datasets, rejected = group_datasets(files, volume_path)
    summary: dict[str, list] = {"created": [], "updated": [], "unchanged": [], "invalid": [], "rejected": rejected}
    for name in sorted(datasets):
        ds = datasets[name]
        urn = build_urn(volume_path, name, env)
        meta = metadata.get(name) or {}
        missing = [f for f in REQUIRED_METADATA if not str(meta.get(f) or "").strip()]
        if missing:
            registry.log_validation_failure(urn, missing)
            summary["invalid"].append((urn, missing))
            continue
        record = {
            "urn": urn,
            "dataset": name,
            **{f: str(meta[f]).strip() for f in REQUIRED_METADATA},
            "location": ds.location,
            "format": "json",
            "file_count": ds.file_count,
            "total_bytes": ds.total_bytes,
            "last_updated": ds.last_updated,
        }
        action = registry.upsert(record)
        summary[action].append(record["urn"])
    return summary


def format_summary(summary: dict, dry_run: bool) -> str:
    title = "## DCH sheet update" + (" (dry run, nothing saved)" if dry_run else "")
    lines = [
        title,
        "",
        "| Result | Count |",
        "| --- | --- |",
        f"| Created | {len(summary['created'])} |",
        f"| Updated | {len(summary['updated'])} |",
        f"| Unchanged | {len(summary['unchanged'])} |",
        f"| Invalid (missing metadata) | {len(summary['invalid'])} |",
        f"| Rejected | {len(summary['rejected'])} |",
        "",
    ]
    for label in ("created", "updated"):
        if summary[label]:
            lines.append(f"**{label.capitalize()}**")
            lines.extend(f"- `{urn}`" for urn in summary[label])
            lines.append("")
    if summary["invalid"]:
        lines.append("**Validation failures (not registered)**")
        lines.extend(f"- `{urn}`: missing {', '.join(missing)}" for urn, missing in summary["invalid"])
        lines.append("")
    if summary["rejected"]:
        lines.append("**Rejected (not added to the sheet)**")
        lines.extend(f"- `{r.path}`: {r.reason}" for r in summary["rejected"])
        lines.append("")
    return "\n".join(lines)


def append_to_env_file(variable: str, text: str) -> None:
    """Write to a file GitHub Actions gives us (GITHUB_STEP_SUMMARY or GITHUB_OUTPUT)."""
    path = os.environ.get(variable)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Imported here so the unit tests never need Databricks credentials.
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import DatabricksError, NotFound, PermissionDenied

    try:
        client = WorkspaceClient()
    except ValueError as exc:
        print(f"Could not connect to Databricks: {exc}", file=sys.stderr)
        print("Set DATABRICKS_HOST and DATABRICKS_TOKEN, or run `databricks auth login`.", file=sys.stderr)
        return 1

    try:
        files = list_files(client, args.path)
    except NotFound:
        print(f"Volume path not found: {args.path}. Check DCH_VOLUME_PATH.", file=sys.stderr)
        return 1
    except PermissionDenied:
        print(f"The Databricks token can't read {args.path}. Ask for READ VOLUME on the volume.", file=sys.stderr)
        return 1
    except DatabricksError as exc:
        print(f"Databricks error while listing {args.path}: {exc}", file=sys.stderr)
        return 1

    metadata = load_metadata(args.metadata)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    registry = ExcelRegistry(
        args.workbook,
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        commit_sha=os.environ.get("GITHUB_SHA", "local"),
        now=now,
    )
    summary = reconcile(files, args.path, registry, metadata, args.env)
    changed = False if args.dry_run else registry.save_if_changed()

    text = format_summary(summary, args.dry_run)
    print(text)
    append_to_env_file("GITHUB_STEP_SUMMARY", text)
    append_to_env_file("GITHUB_OUTPUT", f"changed={'true' if changed else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
