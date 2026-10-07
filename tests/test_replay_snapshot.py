"""Verify a rerun snapshot fails closed and preserves charged job evidence."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pipeline import replay_snapshot as module


def snapshot() -> dict:
    """Return synthetic internally consistent first-day data, never real results."""
    return {
        "relations": [
            {
                "relation_name": name,
                "row_count": 92 if name == "dim_date" else 2,
                "null_date_rows": 0,
                "distinct_dates": 92 if name == "dim_date" else 1,
                "first_date": "2020-11-01",
                "last_date": "2021-01-31" if name == "dim_date" else "2020-11-01",
                "fingerprint": "a" * 64,
            }
            for name in sorted(module.RELATIONS)
        ],
        "raw_source": {
            "raw_rows": 10,
            "valid_sessions": 2,
            "keyed_purchase_events": 1,
            "keyed_missing_revenue_events": 0,
            "keyed_purchase_revenue_usd": "1.25",
        },
        "sessions": {
            "sessions": 2,
            "purchase_events": 1,
            "missing_revenue_events": 0,
            "purchase_revenue_usd": "1.25",
        },
    }


def client_and_job(estimate: int | None = 100) -> tuple[Mock, Mock]:
    """Separate the metadata-free dry job from the simulated charged SELECT."""
    job = Mock(
        job_id="fixture-job",
        total_bytes_processed=100,
        total_bytes_billed=1024,
        error_result=None,
        statement_type="SELECT",
    )
    job.result.return_value = [{"snapshot_json": json.dumps(snapshot())}]
    client = Mock(project=module.PROJECT)
    client.query.side_effect = [Mock(total_bytes_processed=estimate), job]
    return client, job


@pytest.mark.parametrize("estimate", [None, -1, module.CAP + 1])
def test_bad_estimate_prevents_execution_and_publication(
    tmp_path: Path, estimate: int | None
) -> None:
    """Unknown or out-of-scope bytes cannot silently become a paid SELECT."""
    client, _ = client_and_job(estimate)
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        pytest.raises(ValueError),
    ):
        module.take_snapshot(client, tmp_path / "record.json", execute=True)
    assert client.query.call_count == 1
    assert not (tmp_path / "record.json").exists()


def test_default_only_dry_runs(tmp_path: Path) -> None:
    """Preparation never executes or publishes invented validation results."""
    client, job = client_and_job()
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        record = module.take_snapshot(client, tmp_path / "record.json")
    assert client.query.call_count == 1
    assert client.query.call_args.kwargs["job_config"].dry_run
    assert record["executed"] is False and "snapshot" not in record
    job.result.assert_not_called()


@pytest.mark.parametrize(
    "mismatch", ["revenue", "date", "duplicate", "missing", "null_date", "calendar"]
)
def test_bad_reconciliation_is_rejected(mismatch: str) -> None:
    """Grain/date scope and source revenue are checked independently of hashes."""
    value = snapshot()
    if mismatch == "revenue":
        value["sessions"]["purchase_revenue_usd"] = "1.26"
    elif mismatch == "date":
        value["relations"][1]["last_date"] = "2020-11-02"
    elif mismatch == "duplicate":
        value["relations"][1] = copy.deepcopy(value["relations"][2])
    elif mismatch == "null_date":
        value["relations"][2]["null_date_rows"] = 1
    elif mismatch == "calendar":
        value["relations"][0]["distinct_dates"] = 91
    else:
        value["relations"].pop()
    with pytest.raises(ValueError):
        module.verify_snapshot(value)


def test_paid_snapshot_and_repeat_protection(tmp_path: Path) -> None:
    """Success retains actual bytes and refuses a second charge at the same path."""
    client, _ = client_and_job()
    path = tmp_path / "record.json"
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        record = module.take_snapshot(client, path, execute=True)
    assert record["status"] == "passed" and record["billed_bytes"] == 1024
    assert (
        client.query.call_args.kwargs["job_config"].maximum_bytes_billed == module.CAP
    )
    assert client.query.call_args.kwargs["job_retry"] is None
    saved_bytes = path.read_bytes()
    client.query.reset_mock()
    with pytest.raises(ValueError, match="charge twice"):
        module.take_snapshot(client, path, execute=True)
    client.query.assert_not_called()
    assert path.read_bytes() == saved_bytes


@pytest.mark.parametrize("changed", [False, True])
def test_before_after_checks_entire_row_fingerprints(
    tmp_path: Path, changed: bool
) -> None:
    """Unchanged aggregates cannot conceal a different persisted row value."""
    client, _ = client_and_job()
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        module.take_snapshot(client, before, execute=True)
    client, job = client_and_job()
    value = snapshot()
    if changed:
        value["relations"][2]["fingerprint"] = "B" * 64
    job.result.return_value = [{"snapshot_json": json.dumps(value)}]
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        if changed:
            with pytest.raises(ValueError, match="fingerprints"):
                module.take_snapshot(client, after, execute=True, compare_with=before)
            record = json.loads(after.read_text())
            assert record["status"] == "verification_pending"
        else:
            record = module.take_snapshot(
                client, after, execute=True, compare_with=before
            )
            assert record["identical_to_before"] is True
    assert record["executed"] and record["billed_bytes"] == 1024


@pytest.mark.parametrize("unknown_bytes", [False, True])
def test_failed_or_unknown_job_preserves_evidence(
    tmp_path: Path, unknown_bytes: bool
) -> None:
    """A charged or failed attempt is saved and cannot be overwritten on retry."""
    client, job = client_and_job()
    if unknown_bytes:
        job.total_bytes_billed = None
    else:
        job.error_result = {"reason": "fixture-failure"}
        job.result.side_effect = RuntimeError("fixture-failure")
    path = tmp_path / "record.json"
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        pytest.raises((ValueError, RuntimeError)),
    ):
        module.take_snapshot(client, path, execute=True)
    record = json.loads(path.read_text())
    assert record["executed"] and record["job_id"] == "fixture-job"
    assert record["status"] != "passed"
    assert record["billed_bytes"] == (None if unknown_bytes else 1024)


def test_wrong_project_fails_before_metadata_or_query() -> None:
    """A local environment setting cannot redirect this approved fixed scope."""
    client = Mock(project="unapproved-project")
    with pytest.raises(ValueError, match="approved project"):
        module.verify_metadata(client)
    client.get_table.assert_not_called()
    client.query.assert_not_called()


def test_ambiguous_submission_preserves_id_and_prevents_retry(tmp_path: Path) -> None:
    """A lost submission response cannot trigger an unaccounted duplicate charge."""
    client, _ = client_and_job()
    client.query.side_effect = [
        Mock(total_bytes_processed=100),
        RuntimeError("fixture-response-lost"),
    ]
    path = tmp_path / "record.json"
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        pytest.raises(RuntimeError),
    ):
        module.take_snapshot(client, path, execute=True)
    record = json.loads(path.read_text())
    assert record["execution_requested"] and record["executed"] is False
    assert record["job_id"] == client.query.call_args.kwargs["job_id"]
    assert record["status"] == "submission_pending"
    client.query.reset_mock()
    with pytest.raises(ValueError, match="charge twice"):
        module.take_snapshot(client, path, execute=True)
    client.query.assert_not_called()


def test_existing_extra_relation_is_protected_before_any_query() -> None:
    """Owner-created scratch data cannot be silently replaced by a native rerun."""
    modified = datetime(2026, 10, 5, tzinfo=UTC)
    client = Mock(project=module.PROJECT)
    client.get_table.return_value = Mock(
        num_rows=10,
        num_bytes=100,
        modified=modified,
        full_table_id=f"{module.PROJECT}:ga4_raw.ga4_events",
    )
    client.get_dataset.return_value = Mock(
        location="US",
        default_table_expiration_ms=None,
        default_partition_expiration_ms=None,
    )
    client.list_tables.return_value = [
        Mock(table_id=name)
        for name in module.RELATIONS
        | {"stg_ga4_events", "stg_ga4_items", "int_sessions", "fct_sessions__dbt_tmp"}
    ]
    metrics = {
        "warehouse_builds": {
            "p5_2_raw_extraction": {
                "verification": {"only_20201101_partition": True},
                "execution": {
                    "raw_metadata": {
                        "num_rows": 10,
                        "num_bytes": 100,
                        "modified": modified.isoformat(),
                        "table": f"{module.PROJECT}.ga4_raw.ga4_events",
                    }
                },
            }
        }
    }
    with (
        patch.object(module, "_read_json", return_value=metrics),
        pytest.raises(ValueError, match="owner data"),
    ):
        module.verify_metadata(client)
    client.query.assert_not_called()
    client.delete_table.assert_not_called()


@pytest.mark.parametrize(
    ("fingerprint", "valid"),
    [("a" * 64, True), ("A" * 64, True), ("g" * 64, False), ("a" * 63, False)],
)
def test_native_hex_case_and_invalid_fingerprints(
    fingerprint: str, valid: bool
) -> None:
    """BigQuery returns lowercase hex; invalid hex or length must still fail."""
    value = snapshot()
    value["relations"][0]["fingerprint"] = fingerprint
    if valid:
        module.verify_snapshot(value)
    else:
        with pytest.raises(ValueError):
            module.verify_snapshot(value)


@pytest.mark.parametrize("mismatch", [None, "cap", "result", "failed_job"])
def test_completed_snapshot_revalidation_never_submits_query(
    tmp_path: Path, mismatch: str | None
) -> None:
    """A local validator repair can reuse real results without a duplicate charge."""
    client, job = client_and_job()
    path = tmp_path / "record.json"
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        module.take_snapshot(client, path, execute=True)
    record = json.loads(path.read_text())
    record["status"] = "verification_pending"
    path.write_text(json.dumps(record))
    job.state = "DONE"
    job.location = "US"
    job.project = module.PROJECT
    job.query = module.SQL_PATH.read_text()
    job.maximum_bytes_billed = module.CAP
    job.labels = {"ga4_run": "owner_replay_rerun_validation"}
    client.get_job.return_value = job
    client.query.reset_mock()
    saved = path.read_bytes()
    if mismatch == "cap":
        job.maximum_bytes_billed += 1
    elif mismatch == "result":
        job.result.return_value = [{"snapshot_json": json.dumps({"changed": True})}]
    elif mismatch == "failed_job":
        job.error_result = {"reason": "fixture-failure"}
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        if mismatch:
            with pytest.raises(ValueError):
                module.revalidate_saved_snapshot(client, path)
            assert path.read_bytes() == saved
        else:
            recovered = module.revalidate_saved_snapshot(client, path)
            assert recovered["status"] == "passed"
            assert (
                recovered["revalidation"]["previous_status"] == "verification_pending"
            )
    client.query.assert_not_called()


def test_failed_after_comparison_cannot_be_revalidated_as_equal(tmp_path: Path) -> None:
    """Recovery retains the before path and cannot hide a native row mismatch."""
    client, _ = client_and_job()
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    with patch.object(module, "verify_metadata", return_value={"raw_rows": 10}):
        module.take_snapshot(client, before, execute=True)
    client, job = client_and_job()
    changed = snapshot()
    changed["relations"][2]["fingerprint"] = "b" * 64
    job.result.return_value = [{"snapshot_json": json.dumps(changed)}]
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        pytest.raises(ValueError, match="fingerprints"),
    ):
        module.take_snapshot(client, after, execute=True, compare_with=before)
    record = json.loads(after.read_text())
    assert record["compared_with"] == str(before)
    job.state = "DONE"
    job.location = "US"
    job.project = module.PROJECT
    job.query = module.SQL_PATH.read_text()
    job.maximum_bytes_billed = module.CAP
    job.labels = {"ga4_run": "owner_replay_rerun_validation"}
    client.get_job.return_value = job
    client.query.reset_mock()
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        pytest.raises(ValueError, match="before snapshot"),
    ):
        module.revalidate_saved_snapshot(client, after)
    client.query.assert_not_called()
    assert json.loads(after.read_text())["status"] == "verification_pending"
