"""Read a Unity Catalog volume and turn its files into DCH dataset records.

Owner: Teammate 3. Used by update_dch.py.

Rules:
  * Each top-level folder under the volume path is one dataset (one row in the sheet).
  * Only .json files inside a dataset folder count. Anything else is rejected.
  * Files in deeper subfolders (customers/2026/09/x.json) still belong to the top folder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath

_UNSAFE = re.compile(r"[^a-z0-9_\-]+")


@dataclass(frozen=True)
class VolumeFile:
    path: str  # full path, e.g. /Volumes/workspace/dch_demo/landing/customers/customers_01.json
    size: int  # bytes
    modified_ms: int  # last modified time, milliseconds since 1970-01-01 UTC


@dataclass(frozen=True)
class Rejected:
    path: str
    reason: str


@dataclass
class Dataset:
    name: str  # normalized folder name, e.g. "customers"
    location: str  # full folder path, e.g. /Volumes/workspace/dch_demo/landing/customers/
    files: list[VolumeFile] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def last_updated(self) -> str:
        newest = max((f.modified_ms for f in self.files), default=0)
        return ms_to_iso(newest)


def ms_to_iso(ms: int) -> str:
    """Milliseconds since the epoch -> '2026-09-21T14:03:00Z'."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_volume_path(path: str) -> tuple[str, str, str]:
    """Return (catalog, schema, volume) from a path like /Volumes/<catalog>/<schema>/<volume>/..."""
    parts = PurePosixPath(path).parts  # ('/', 'Volumes', catalog, schema, volume, ...)
    if len(parts) < 5 or parts[0] != "/" or parts[1] != "Volumes":
        raise ValueError(
            f"Not a Unity Catalog volume path: {path!r}. "
            "Expected something like /Volumes/<catalog>/dch_demo/landing/"
        )
    return parts[2], parts[3], parts[4]


def normalize(value: str) -> str:
    """Lowercase, trim, and turn anything outside a-z, 0-9, _ and - into _."""
    cleaned = _UNSAFE.sub("_", value.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError(f"{value!r} has no letters or numbers to build a name from")
    return cleaned


def build_urn(volume_path: str, dataset: str, env: str = "dev") -> str:
    """Build the unique key for a dataset.

    build_urn("/Volumes/workspace/dch_demo/landing/", "Customers")
      -> "urn:dch:dataset:databricks:dev:workspace.dch_demo.landing/customers"
    """
    catalog, schema, volume = parse_volume_path(volume_path)
    qualified = ".".join(normalize(part) for part in (catalog, schema, volume))
    return f"urn:dch:dataset:databricks:{normalize(env)}:{qualified}/{normalize(dataset)}"


def list_files(client, root: str) -> list[VolumeFile]:
    """List every file under root, walking into every subfolder.

    client is a databricks.sdk.WorkspaceClient (or anything with the same files API).
    """
    root = root.rstrip("/")
    found: list[VolumeFile] = []
    to_visit = [root]
    while to_visit:
        directory = to_visit.pop()
        for entry in client.files.list_directory_contents(directory):
            if entry.is_directory:
                to_visit.append(entry.path.rstrip("/"))
            else:
                found.append(
                    VolumeFile(
                        path=entry.path,
                        size=entry.file_size or 0,
                        modified_ms=entry.last_modified or 0,
                    )
                )
    return sorted(found, key=lambda f: f.path)


def group_datasets(files: list[VolumeFile], root: str) -> tuple[dict[str, Dataset], list[Rejected]]:
    """Split files into datasets (by top-level folder) and rejects."""
    root = root.rstrip("/")
    datasets: dict[str, Dataset] = {}
    rejected: list[Rejected] = []
    for f in files:
        try:
            parts = PurePosixPath(f.path).relative_to(root).parts
        except ValueError:
            rejected.append(Rejected(f.path, "outside the volume path"))
            continue
        if len(parts) < 2:
            rejected.append(Rejected(f.path, "not inside a dataset folder"))
            continue
        if not parts[-1].lower().endswith(".json"):
            rejected.append(Rejected(f.path, "not a .json file"))
            continue
        folder = parts[0]
        try:
            name = normalize(folder)
        except ValueError:
            rejected.append(Rejected(f.path, "folder name has no letters or numbers"))
            continue
        if name not in datasets:
            datasets[name] = Dataset(name=name, location=f"{root}/{folder}/")
        datasets[name].files.append(f)
    return datasets, rejected
