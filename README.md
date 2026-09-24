# DCH Excel demo

When a JSON file lands in the Databricks volume below, GitHub Actions adds or
updates that dataset's row in `dch/dch_registry.xlsx`.

## Values

| What | Value |
| --- | --- |
| Workspace | <workspace-url> |
| Volume path | /Volumes/<catalog>/dch_demo/landing/ |
| Databricks job | dch-notify-github |
| Update workflow | .github/workflows/dch-excel.yml |
| Reset workflow | .github/workflows/dch-reset.yml |

## Rules

- Never edit `dch/dch_registry.xlsx` by hand. The workflow is its only writer.
- Never commit tokens. They live in GitHub secrets and the Databricks secret scope `dch-demo`.
- One dataset = one top-level folder in the volume. Only `.json` files count.
- `metadata/datasets.json` is edited by people, through a PR or commit to `main`. Each dataset
  folder needs `data_product_name`, `owner`, `domain`, and `description`; a dataset with any of
  them missing or blank is not registered and is logged as `validation_failed`.

## Add a dataset

    databricks fs mkdir dbfs:/Volumes/<catalog>/dch_demo/landing/<dataset>
    databricks fs cp my_file.json dbfs:/Volumes/<catalog>/dch_demo/landing/<dataset>/my_file.json

Add a `<dataset>` entry to `metadata/datasets.json` first. The sheet updates within about three
minutes. To update it right away, open Actions, then DCH Excel update, then Run workflow.

## Run the tests

    pip install -r dch-cli/requirements.txt pytest
    pytest dch-cli/tests -q

## Demo scenarios (DCH)

| # | Scenario | How to show it | Expected |
| --- | --- | --- | --- |
| 1 | New dataset → new entry created | Upload `customers/customers_01.json` | Created 1 |
| 2 | Same dataset processed again → no duplicate | Click Run workflow two or three times | Unchanged, no new row, commit step skipped |
| 3 | Dataset metadata updated → existing entry updated | Change `customers` owner in `metadata/datasets.json`, commit to `main` | Updated 1, same row, Audit shows old/new owner |
| 4 | Missing required metadata → validation failure logged | Upload `inventory/inventory_01.json` | Invalid 1, no Assets row, Audit `validation_failed` row listing owner, domain. Then fill in owner/domain and commit → Created 1 |

## Test plan

Start from a clean state (DCH demo reset, type `RESET`). Run in order; sample files are in `sample-data/`.

- **T1 Wiring**: Run workflow on an empty volume → all counts 0, commit step skipped, headers only.
- **T2 New asset**: upload `customers/customers_01.json` → Created 1; 1 Assets row, file_count 1.
- **T3 Existing asset**: upload `customers/customers_02.json` → Updated 1; still 1 row, file_count 2.
- **T4 No duplicates**: Run workflow again → Unchanged 1, commit step skipped.
- **T5 Second asset**: upload `orders/orders_01.json` → Created 1, Unchanged 1; 2 Assets rows.
- **T6 Bad input**: upload `stray.json` to the root and `customers/notes.csv` → Rejected 2, Unchanged 2.
- **T7 Same-name overwrite**: `databricks fs cp --overwrite` `customers_02.json`, wait, Run workflow → no Databricks run; manual run shows Updated 1.
- **T8 Reset**: DCH demo reset, type `RESET` → files and folders deleted, headers only, `databricks fs ls` empty.
- **T9 Metadata update**: change `customers` owner in `metadata/datasets.json`, commit to `main` → Updated 1, Audit shows old/new owner.
- **T10 Missing metadata**: upload `inventory/inventory_01.json` → Invalid (missing metadata) 1, no Assets row, Audit `validation_failed` listing owner, domain.

## Owners

| Part | Owner |
| --- | --- |
| Databricks setup | Teammate 1 |
| Repo and workflows | Teammate 2 |
| Volume reader and update command | Teammate 3 |
| Excel registry | Teammate 4 |
| Testing, reset, demo | Teammate 5 |

## Mentor answers

- Existing manual method and its shortcomings:
- Should we host the CI/CD workflow ourselves:
