# Databricks notebook source
# Tells GitHub that a new file landed in the DCH demo volume.
# Owner: Teammate 1. The Databricks job "dch-notify-github" runs this notebook
# every time its file arrival trigger fires. GitHub then runs dch-excel.yml.
import requests

GITHUB_REPO = "jeevss131436/cummins-cicd-dummy"  # the shared repo, for example "dch-team/dch-demo"
SECRET_SCOPE = "dch-demo"
SECRET_KEY = "github-dispatch-token"

# COMMAND ----------

token = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)  # dbutils is built into Databricks notebooks

response = requests.post(
    f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
    headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    json={"event_type": "databricks_file_arrival", "client_payload": {"source": "databricks"}},
    timeout=15,
)

# GitHub answers 204 No Content when it accepts the dispatch.
if response.status_code != 204:
    raise RuntimeError(f"GitHub dispatch failed with {response.status_code}: {response.text}")

print(f"Triggered the DCH Excel workflow in {GITHUB_REPO}.")
