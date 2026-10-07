"""Guard consequential manual CI scope and retain failed/incomplete accounting."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from google.api_core.exceptions import ServiceUnavailable

from pipeline.manual_workflow import (
    DATASET,
    MATERIALIZATIONS,
    MAX_BYTES,
    PROJECT,
    account_jobs,
    preflight,
    scope_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def approved_env() -> dict[str, str]:
    """Return a synthetic approved first dispatch; no real credentials required."""
    return {
        "GCP_PROJECT_ID": PROJECT,
        "BQ_DATASET_ANALYTICS": DATASET,
        "BQ_LOCATION": "US",
        "BQ_MAX_BYTES_BILLED": str(MAX_BYTES),
        "GITHUB_REPOSITORY": "AbhinavVarma02/ga4-checkout-funnel",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "1234",
        "GA4_RUN_LABEL": "p5_9_1234_1",
        "CONFIRM_CLOUD_WRITE": "go",
        "GITHUB_SHA": "a" * 40,
        "REVIEWED_COMMIT": "a" * 40,
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("GCP_PROJECT_ID", "another-project"),
        ("BQ_DATASET_ANALYTICS", "ga4_analytics"),
        ("BQ_DATASET_ANALYTICS", "ga4_replay"),
        ("BQ_LOCATION", "EU"),
        ("BQ_MAX_BYTES_BILLED", str(20 * 1024**3)),
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REPOSITORY", "someone/else"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GA4_RUN_LABEL", "manual"),
        ("CONFIRM_CLOUD_WRITE", "cancel"),
        ("REVIEWED_COMMIT", "b" * 40),
        ("REVIEWED_COMMIT", "main"),
        ("GITHUB_RUN_ID", "invalid"),
    ],
)
def test_scope_rejects_unapproved_dispatch(key: str, value: str) -> None:
    """Changed destinations, costs, code and reruns cannot reach authentication."""
    env = approved_env() | {key: value}
    with pytest.raises(ValueError):
        scope_plan(env)


def compiled_fixture(evidence: Path) -> Mock:
    """Build an independent tiny seven-model/fourteen-test synthetic manifest."""
    compiled = evidence / "compile" / "compiled" / "ga4_checkout_funnel" / "models"
    from pipeline.dbt_dry_run import MODEL_PATHS

    nodes = {}
    for name, relative in MODEL_PATHS.items():
        sql = "SELECT 1 AS value"
        if name.startswith("stg_"):
            sql += " FROM public_source WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201101'"
        if name == "int_sessions":
            sql = f"SELECT * FROM `{PROJECT}`.`{DATASET}`.`stg_ga4_events`"
        if name == "fct_sessions":
            sql = f"SELECT * FROM `{PROJECT}`.`{DATASET}`.`int_sessions`"
        if name == "fct_funnel_daily":
            sql = f"SELECT * FROM `{PROJECT}`.`{DATASET}`.`fct_sessions`"
        if name == "fct_product_daily":
            sql = f"SELECT * FROM `{PROJECT}`.`{DATASET}`.`stg_ga4_items` JOIN `{PROJECT}`.`{DATASET}`.`int_sessions` USING (value)"
        path = compiled / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sql)
        nodes[name] = {
            "name": name,
            "resource_type": "model",
            "database": PROJECT,
            "schema": DATASET,
            "config": {"materialized": MATERIALIZATIONS[name]},
        }
    for index in range(14):
        name = f"test.{index}"
        nodes[name] = {
            "name": name,
            "unique_id": name,
            "resource_type": "test",
            "database": PROJECT,
            "schema": DATASET,
            "config": {},
            "compiled_code": f"SELECT * FROM `{PROJECT}`.`{DATASET}`.`fct_sessions`",
        }
    (evidence / "compile" / "manifest.json").write_text(json.dumps({"nodes": nodes}))
    client = Mock(project=PROJECT)
    client.get_dataset.return_value = SimpleNamespace(location="US")
    client.list_tables.return_value = []
    client.query.return_value = SimpleNamespace(total_bytes_processed=123)
    return client


def test_preflight_only_dry_runs_all_selects(tmp_path: Path) -> None:
    """Tests inline unbuilt dependencies and never alter canonical reports."""
    client = compiled_fixture(tmp_path)
    report = preflight(client, tmp_path)
    assert report["status"] == "passed"
    assert len(report["selects"]) == client.query.call_count == 21
    for call in client.query.call_args_list:
        assert call.kwargs["job_config"].dry_run is True
        assert call.kwargs["job_retry"] is None
        assert f"`{DATASET}`" not in call.args[0]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["compile", "preflight.json"]


def test_default_test_schema_is_allowed_without_persistence(tmp_path: Path) -> None:
    """Actual dbt test metadata names an audit schema even for SELECT-only tests."""
    client = compiled_fixture(tmp_path)
    path = tmp_path / "compile" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["nodes"]["test.0"]["schema"] = f"{DATASET}_dbt_test__audit"
    path.write_text(json.dumps(manifest))
    assert preflight(client, tmp_path)["status"] == "passed"
    manifest["nodes"]["test.0"]["config"]["store_failures"] = True
    path.write_text(json.dumps(manifest))
    client.query.reset_mock()
    with pytest.raises(ValueError, match="Persisted test"):
        preflight(client, tmp_path)
    client.query.assert_not_called()


@pytest.mark.parametrize(
    "case",
    [
        "occupied",
        "location",
        "project",
        "materialization",
        "source",
        "node_schema",
        "test_count",
    ],
)
def test_unsafe_target_or_compilation_stops_before_query(
    tmp_path: Path, case: str
) -> None:
    """Old tables and changed compiled scope cannot be overwritten."""
    client = compiled_fixture(tmp_path)
    manifest_path = tmp_path / "compile" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if case == "occupied":
        client.list_tables.return_value = [object()]
    elif case == "location":
        client.get_dataset.return_value.location = "EU"
    elif case == "project":
        client.project = "another-project"
    elif case == "materialization":
        manifest["nodes"]["fct_sessions"]["config"]["materialized"] = "incremental"
    elif case == "source":
        path = (
            tmp_path
            / "compile/compiled/ga4_checkout_funnel/models/staging/stg_ga4_events.sql"
        )
        path.write_text(
            path.read_text().replace(
                "20201101' AND '20201101", "20201101' AND '20210131"
            )
        )
    elif case == "node_schema":
        manifest["nodes"]["test.0"]["schema"] = "ga4_analytics"
    else:
        del manifest["nodes"]["test.0"]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        preflight(client, tmp_path)
    client.query.assert_not_called()


@pytest.mark.parametrize("estimate", [None, -1, MAX_BYTES + 1])
def test_estimate_fails_closed_and_retains_receipt(
    tmp_path: Path, estimate: int | None
) -> None:
    """Unavailable and oversized dry runs cannot permit a build."""
    client = compiled_fixture(tmp_path)
    client.query.return_value.total_bytes_processed = estimate
    with pytest.raises(ValueError, match="dry-run estimate"):
        preflight(client, tmp_path)
    assert client.query.call_count == 1
    assert "status" not in json.loads((tmp_path / "preflight.json").read_text())


def job_fixture(job_id: str, **updates: object) -> SimpleNamespace:
    """Make native job metadata without any SDK query submission."""
    return SimpleNamespace(
        **{
            "job_id": job_id,
            "job_type": "query",
            "project": PROJECT,
            "query": "SELECT 1",
            "labels": {"ga4_run": "p5_9_1234_1"},
            "state": "DONE",
            "statement_type": "SELECT",
            "error_result": None,
            "total_bytes_processed": 5,
            "total_bytes_billed": 10,
            "maximum_bytes_billed": MAX_BYTES,
            "location": "US",
            "cache_hit": False,
        }
        | updates
    )


def test_accounting_counts_failed_leaves_and_excludes_script_parent(
    tmp_path: Path,
) -> None:
    """API receipts retain failed bytes without duplicating parent summaries."""
    jobs = [
        job_fixture("parent", statement_type="SCRIPT"),
        job_fixture("child"),
        job_fixture("failed", error_result={"reason": "fixture"}),
        job_fixture("other", labels={"ga4_run": "previous"}),
    ]
    client = Mock()
    client.list_jobs.return_value = jobs
    client.get_job.side_effect = jobs[:3]
    report = account_jobs(
        client, scope_plan(approved_env()), tmp_path, build_outcome="failure"
    )
    assert report["bytes_billed"] == 20
    assert report["failed_query_jobs"] == 1
    assert len(report["jobs"]) == 3
    assert client.list_jobs.call_args.kwargs["all_users"] is False
    client.query.assert_not_called()


@pytest.mark.parametrize(
    "updates",
    [
        {"state": "RUNNING"},
        {"total_bytes_billed": None},
        {"maximum_bytes_billed": 20 * 1024**3},
        {"total_bytes_processed": -1},
        {"location": "EU"},
    ],
)
def test_incomplete_job_inventory_never_claims_zero(
    tmp_path: Path, updates: dict
) -> None:
    """Preserve IDs and unknown totals after partial or malformed native metadata."""
    job = job_fixture("unfinished", **updates)
    client = Mock()
    client.list_jobs.return_value = [job]
    client.get_job.return_value = job
    with pytest.raises(ValueError, match="Accounting incomplete"):
        account_jobs(
            client, scope_plan(approved_env()), tmp_path, build_outcome="failure"
        )
    report = json.loads((tmp_path / "accounting.json").read_text())
    assert report["bytes_billed"] is None
    assert report["jobs"][0]["job_id"] == "unfinished"
    client.query.assert_not_called()


def test_empty_job_inventory_is_incomplete(tmp_path: Path) -> None:
    """A missing receipt cannot be published as a free successful run."""
    client = Mock()
    client.list_jobs.return_value = []
    with pytest.raises(ValueError, match="Accounting incomplete"):
        account_jobs(
            client, scope_plan(approved_env()), tmp_path, build_outcome="skipped"
        )
    assert (
        json.loads((tmp_path / "accounting.json").read_text())["bytes_billed"] is None
    )


def test_api_failure_keeps_partial_inventory(tmp_path: Path) -> None:
    """A metadata API failure retains collected IDs and the next unresolved ID."""
    client = Mock()
    client.list_jobs.return_value = [job_fixture("saved"), job_fixture("unresolved")]
    client.get_job.side_effect = [
        job_fixture("saved"),
        ServiceUnavailable("private text"),
    ]
    with pytest.raises(ValueError, match="Accounting incomplete"):
        account_jobs(
            client, scope_plan(approved_env()), tmp_path, build_outcome="failure"
        )
    report = json.loads((tmp_path / "accounting.json").read_text())
    assert report["jobs"][0]["job_id"] == "saved"
    assert report["unresolved_job_id"] == "unresolved"
    assert report["bytes_billed"] is None
    assert "private text" not in (tmp_path / "accounting.json").read_text()


@pytest.mark.parametrize("case", ["valid", "skipped", "missing_job"])
def test_success_requires_all_native_nodes(tmp_path: Path, case: str) -> None:
    """Successful workflow status alone cannot stand in for all model/test results."""
    client = Mock()
    jobs = [job_fixture(f"native_{index}") for index in range(21)]
    if case == "missing_job":
        jobs.pop()
    client.list_jobs.return_value = jobs
    client.get_job.side_effect = jobs
    folder = tmp_path / "build"
    folder.mkdir()
    results = [
        {
            "status": "success" if index < 7 else "pass",
            "adapter_response": {"job_id": f"native_{index}"},
        }
        for index in range(21)
    ]
    if case == "skipped":
        results[-1]["status"] = "skipped"
    (folder / "run_results.json").write_text(json.dumps({"results": results}))
    if case == "valid":
        assert account_jobs(
            client, scope_plan(approved_env()), tmp_path, build_outcome="success"
        )["accounting_complete"]
    else:
        with pytest.raises(ValueError, match="Accounting incomplete"):
            account_jobs(
                client, scope_plan(approved_env()), tmp_path, build_outcome="success"
            )
    assert (tmp_path / "accounting.json").exists()


def test_local_cli_plan_and_repeat_reject_without_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    """The pre-authentication plan does not open ADC or permit a repeated attempt."""
    from pipeline.manual_workflow import main

    for key, value in approved_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("pipeline.manual_workflow.EVIDENCE", tmp_path)
    monkeypatch.setattr("sys.argv", ["manual_workflow", "plan"])
    client = Mock(side_effect=AssertionError("ADC forbidden"))
    monkeypatch.setattr("pipeline.manual_workflow.bigquery.Client", client)
    main()
    with pytest.raises(ValueError, match="attempt receipt"):
        main()
    client.assert_not_called()


def test_workflow_enforces_owner_gate_and_separate_receipts() -> None:
    """Review actual YAML ordering, target settings and artifact allowlist."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/dbt_bigquery.yml").read_text())
    trigger = workflow.get("on", workflow.get(True))
    assert set(trigger) == {"workflow_dispatch"}
    assert (
        trigger["workflow_dispatch"]["inputs"]["confirm_cloud_write"]["default"]
        == "cancel"
    )
    job = workflow["jobs"]["dbt-build"]
    assert job["env"]["BQ_DATASET_ANALYTICS"] == DATASET
    steps = job["steps"]
    auth_index = next(i for i, step in enumerate(steps) if step.get("id") == "auth")
    assert "manual_workflow plan" in steps[auth_index - 1]["run"]
    build = next(step for step in steps if step.get("id") == "build")
    assert "--target ci" in build["run"] and "--exclude test_type:unit" in build["run"]
    assert "--fail-fast" in build["run"]
    artifact = steps[-1]["with"]
    assert artifact["include-hidden-files"] is True
    assert len(artifact["path"].splitlines()) == 5
    assert "gha-creds" not in artifact["path"]
