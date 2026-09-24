# Databricks Data Catalog Demo

This project demonstrates how new data files in a Databricks volume can be registered in a simple Excel data catalog. It uses GitHub Actions to validate dataset metadata, track changes, and keep the catalog up to date.

## How it works

1. Data files arrive in a Databricks Unity Catalog volume, organized into folders by dataset.
2. A Databricks file-arrival job runs `databricks/notify_github.py`, which sends a repository dispatch event to GitHub.
3. The `DCH Excel update` GitHub Actions workflow runs `dch-cli/update_dch.py`.
4. The updater scans the volume and reads dataset descriptions and ownership details from `metadata/datasets.json`.
5. Datasets with complete metadata are added to or updated in `dch/dch_registry.xlsx`. Incomplete datasets are skipped and recorded as validation failures. Non-JSON files are rejected.
6. The workbook is committed to the repository when its contents change. The workflow can also run when metadata changes or be started manually.

## What it does

- Treats each top-level folder in the volume as a dataset and counts its JSON files.
- Creates a stable URN for each dataset and records its metadata, location, file count, size, and update time.
- Adds new datasets, updates changed datasets, and leaves unchanged datasets alone.
- Keeps an audit history of dataset creation, updates, and metadata validation failures.
- Reports rejected files and validation results in the GitHub Actions run summary.

The Excel workbook has two sheets: **Assets**, with one row per registered dataset, and **Audit**, with the history of changes and validation failures.

`sample-data/` contains example inputs, and `metadata/datasets.json` contains their metadata. The current updater scans the configured Databricks volume; it does not scan the checked-in sample files directly.
