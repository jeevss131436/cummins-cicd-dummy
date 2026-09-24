"""Unit tests for volume_reader.py and the reconcile step in update_dch.py.

Owner: Teammate 3. Run from the repo root:  pytest dch-cli/tests -q
No Databricks connection is needed; a fake client stands in for the workspace.
"""
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make dch-cli importable

from excel_registry import ExcelRegistry, create_workbook  # noqa: E402
from update_dch import reconcile  # noqa: E402
from volume_reader import (  # noqa: E402
    VolumeFile, build_urn, group_datasets, list_files, normalize, parse_volume_path,
)

ROOT = "/Volumes/workspace/dch_demo/landing"

META = {
    "customers": {
        "data_product_name": "Customer Master",
        "owner": "sales-data@example.com",
        "domain": "Sales",
        "description": "One record per customer.",
    },
    "orders": {
        "data_product_name": "Sales Orders",
        "owner": "orders-data@example.com",
        "domain": "Sales",
        "description": "One record per order.",
    },
}


def make_client(files: dict[str, tuple[int, int]]):
    """Fake WorkspaceClient whose volume holds `files` ({path: (size, modified_ms)})."""
    listing: dict[str, list] = {ROOT: []}
    for path, (size, ms) in files.items():
        parent = PurePosixPath(path).parent
        child = PurePosixPath(path)
        entry = SimpleNamespace(path=str(child), is_directory=False, file_size=size, last_modified=ms)
        while True:
            listing.setdefault(str(parent), [])
            if entry not in listing[str(parent)]:
                listing[str(parent)].append(entry)
            if str(parent) == ROOT:
                break
            entry = SimpleNamespace(path=str(parent), is_directory=True, file_size=None, last_modified=None)
            parent = parent.parent
    files_api = SimpleNamespace(list_directory_contents=lambda d: iter(listing[d.rstrip("/")]))
    return SimpleNamespace(files=files_api)


def vf(path: str, size: int = 100, ms: int = 1_758_456_000_000) -> VolumeFile:
    return VolumeFile(path=path, size=size, modified_ms=ms)


# ---------- URN ----------

def test_build_urn_format():
    assert build_urn(ROOT + "/", "customers") == "urn:dch:dataset:databricks:dev:workspace.dch_demo.landing/customers"


def test_build_urn_is_stable_across_case_spaces_and_slashes():
    a = build_urn(ROOT, "Customers")
    b = build_urn(ROOT + "/", " customers ")
    c = build_urn("/Volumes/Workspace/DCH_Demo/Landing/", "CUSTOMERS")
    assert a == b == c


def test_normalize_replaces_unsafe_characters():
    assert normalize("Sales Orders 2026") == "sales_orders_2026"
    assert normalize("  web-logs  ") == "web-logs"


def test_normalize_rejects_empty():
    with pytest.raises(ValueError):
        normalize("!!!")


def test_parse_volume_path_rejects_non_volume_paths():
    with pytest.raises(ValueError):
        parse_volume_path("/dbfs/tmp/landing")
    with pytest.raises(ValueError):
        parse_volume_path("/Volumes/only_catalog")


# ---------- listing and grouping ----------

def test_list_files_walks_every_subfolder():
    client = make_client({
        f"{ROOT}/customers/customers_01.json": (120, 1),
        f"{ROOT}/customers/2026/09/customers_02.json": (80, 2),
        f"{ROOT}/orders/orders_01.json": (50, 3),
    })
    paths = [f.path for f in list_files(client, ROOT + "/")]
    assert paths == sorted([
        f"{ROOT}/customers/2026/09/customers_02.json",
        f"{ROOT}/customers/customers_01.json",
        f"{ROOT}/orders/orders_01.json",
    ])


def test_group_datasets_totals_and_rejects():
    files = [
        vf(f"{ROOT}/customers/customers_01.json", 100, 1_000),
        vf(f"{ROOT}/customers/deep/customers_02.JSON", 50, 5_000),
        vf(f"{ROOT}/customers/notes.csv", 10, 9_000),
        vf(f"{ROOT}/stray.json", 10, 9_000),
    ]
    datasets, rejected = group_datasets(files, ROOT + "/")
    assert list(datasets) == ["customers"]
    ds = datasets["customers"]
    assert ds.file_count == 2
    assert ds.total_bytes == 150
    assert ds.last_updated == "1970-01-01T00:00:05Z"
    assert ds.location == f"{ROOT}/customers/"
    reasons = {Path(r.path).name: r.reason for r in rejected}
    assert reasons == {"notes.csv": "not a .json file", "stray.json": "not inside a dataset folder"}


# ---------- reconcile (volume -> sheet) ----------

@pytest.fixture
def sheet(tmp_path):
    path = tmp_path / "dch_registry.xlsx"
    create_workbook(path)
    return path


def run(sheet_path, files, run_id="1"):
    registry = ExcelRegistry(sheet_path, run_id=run_id, commit_sha="abc", now="2026-09-21T12:00:00Z")
    summary = reconcile(files, ROOT + "/", registry, META)
    saved = registry.save_if_changed()
    return summary, saved


def test_first_file_creates_one_row(sheet):
    summary, saved = run(sheet, [vf(f"{ROOT}/customers/customers_01.json")])
    assert len(summary["created"]) == 1 and saved


def test_second_file_in_same_folder_updates_not_duplicates(sheet):
    run(sheet, [vf(f"{ROOT}/customers/customers_01.json")])
    summary, _ = run(sheet, [
        vf(f"{ROOT}/customers/customers_01.json"),
        vf(f"{ROOT}/customers/customers_02.json"),
    ], run_id="2")
    assert summary["created"] == [] and len(summary["updated"]) == 1
    registry = ExcelRegistry(sheet, run_id="x", commit_sha="x", now="x")
    assert len(registry.rows) == 1
    assert registry.get(build_urn(ROOT, "customers"))["file_count"] == 2


def test_rerun_with_no_new_files_changes_nothing(sheet):
    files = [vf(f"{ROOT}/customers/customers_01.json"), vf(f"{ROOT}/orders/orders_01.json")]
    run(sheet, files)
    before = sheet.read_bytes()
    summary, saved = run(sheet, files, run_id="2")
    assert len(summary["unchanged"]) == 2
    assert saved is False
    assert sheet.read_bytes() == before  # file untouched, so Git sees no change

