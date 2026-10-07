"""Unit checks for billed-byte recording with fixture job metadata only."""

import csv
from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from pipeline.bytes_log import (
    FAILURE_FIELDNAMES,
    LEGACY_FIELDNAMES,
    jobs_query,
    record_bytes,
)


def test_jobs_query_rejects_untrusted_project_id() -> None:
    """Dynamic INFORMATION_SCHEMA identifiers cannot accept SQL syntax."""
    with pytest.raises(ValueError, match="Invalid Google Cloud project ID"):
        jobs_query("project`; DROP TABLE x")


def test_record_bytes_upserts_one_run(tmp_path) -> None:
    """Repeated reports for the same run update one CSV row."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=64),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=100,
                    total_bytes_billed=1024,
                    error_result=None,
                ),
                SimpleNamespace(
                    total_bytes_processed=200,
                    total_bytes_billed=1024,
                    error_result=None,
                ),
            ]
        ),
        SimpleNamespace(total_bytes_processed=64),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=300,
                    total_bytes_billed=2048,
                    error_result=None,
                ),
            ]
        ),
    ]
    report = tmp_path / "bytes_billed.csv"
    start = datetime(2026, 10, 4, tzinfo=UTC)
    end = datetime(2026, 10, 5, tzinfo=UTC)

    first = record_bytes(
        client, "sample-project", "fixture_run", date(2020, 11, 1), start, end, report
    )
    second = record_bytes(
        client, "sample-project", "fixture_run", date(2020, 11, 1), start, end, report
    )

    with report.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert first["query_jobs"] == "2"
    assert first["bytes_billed"] == "2048"
    assert second["bytes_billed"] == "2048"
    assert len(rows) == 1
    assert rows[0]["bytes_processed"] == "300"
    assert "UNNEST(labels)" in client.query.call_args.args[0]
    assert "error_result IS NULL" not in client.query.call_args.args[0]
    assert client.query.call_args.kwargs["job_retry"] is None


def test_failed_query_bytes_are_counted_and_legacy_rows_preserved(tmp_path) -> None:
    """Failed jobs can incur bytes; older records must not invent failure counts."""
    report = tmp_path / "bytes_billed.csv"
    legacy = dict.fromkeys(LEGACY_FIELDNAMES, "fixture")
    legacy.update(run_label="older_fixture", event_date="2020-11-01")
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_FIELDNAMES)
        writer.writeheader()
        writer.writerow(legacy)
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=0),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=100,
                    total_bytes_billed=1024,
                    error_result={"reason": "fixtureFailure"},
                ),
                SimpleNamespace(
                    total_bytes_processed=200,
                    total_bytes_billed=2048,
                    error_result=None,
                ),
            ]
        ),
    ]
    result = record_bytes(
        client,
        "sample-project",
        "fixture_run",
        date(2020, 11, 1),
        datetime(2026, 10, 4, tzinfo=UTC),
        datetime(2026, 10, 5, tzinfo=UTC),
        report,
    )
    assert result["bytes_billed"] == "3072"
    assert result["failed_query_jobs"] == "1"
    with report.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert (
        next(row for row in rows if row["run_label"] == "older_fixture")[
            "failed_query_jobs"
        ]
        == "not_recorded"
    )


def test_reused_label_preserves_each_execution_window(tmp_path) -> None:
    """Same-label reprocessing appends; retries of the same UTC window upsert."""
    client = MagicMock(spec=bigquery.Client)
    report = tmp_path / "bytes_billed.csv"
    first_start = datetime(2026, 10, 5, 22, tzinfo=UTC)
    second_start = datetime(2026, 10, 5, 23, tzinfo=UTC)
    for start, billed in [
        (first_start, 1024),
        (second_start, 2048),
        (second_start.astimezone(timezone(timedelta(hours=5))), 3072),
    ]:
        client.query.side_effect = [
            SimpleNamespace(total_bytes_processed=0),
            SimpleNamespace(
                result=lambda billed=billed: [
                    SimpleNamespace(
                        total_bytes_processed=100,
                        total_bytes_billed=billed,
                        error_result=None,
                    )
                ]
            ),
        ]
        record_bytes(
            client,
            "sample-project",
            "reused_fixture_run",
            date(2020, 11, 1),
            start,
            datetime(2026, 10, 6, tzinfo=UTC),
            report,
        )
    with report.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert {row["window_start_utc"]: row["bytes_billed"] for row in rows} == {
        first_start.isoformat(): "1024",
        second_start.isoformat(): "3072",
    }


@pytest.mark.parametrize("header", [LEGACY_FIELDNAMES, FAILURE_FIELDNAMES])
def test_older_headers_preserve_same_label_history(tmp_path, header: list[str]) -> None:
    """Migration must retain original values without inventing their start window."""
    report = tmp_path / "bytes_billed.csv"
    old_row = dict.fromkeys(header, "legacy_fixture")
    old_row.update(run_label="fixture_run", event_date="2020-11-01")
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerow(old_row)
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=0),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=100,
                    total_bytes_billed=1024,
                    error_result=None,
                )
            ]
        ),
    ]
    record_bytes(
        client,
        "sample-project",
        "fixture_run",
        date(2020, 11, 1),
        datetime(2026, 10, 5, tzinfo=UTC),
        datetime(2026, 10, 6, tzinfo=UTC),
        report,
    )
    with report.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    migrated = next(row for row in rows if row["window_start_utc"] == "not_recorded")
    assert {key: migrated[key] for key in old_row} == old_row


def test_null_billed_bytes_cannot_be_published_as_zero(tmp_path) -> None:
    """Unknown byte metadata stops publication even on a failed query."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=0),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=0,
                    total_bytes_billed=None,
                    error_result={"reason": "fixtureFailure"},
                )
            ]
        ),
    ]
    report = tmp_path / "bytes_billed.csv"
    with pytest.raises(ValueError, match="no on-demand billed-byte"):
        record_bytes(
            client,
            "sample-project",
            "fixture_run",
            date(2020, 11, 1),
            datetime(2026, 10, 4, tzinfo=UTC),
            datetime(2026, 10, 5, tzinfo=UTC),
            report,
        )
    assert not report.exists()


def test_record_bytes_does_not_write_empty_result(tmp_path) -> None:
    """Missing run labels cannot be reported as a zero-cost run."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=0),
        SimpleNamespace(result=list),
    ]
    report = tmp_path / "bytes_billed.csv"
    start = datetime(2026, 10, 4, tzinfo=UTC)
    end = datetime(2026, 10, 5, tzinfo=UTC)

    with pytest.raises(ValueError, match="No completed labeled"):
        record_bytes(
            client,
            "sample-project",
            "fixture_run",
            date(2020, 11, 1),
            start,
            end,
            report,
        )
    assert not report.exists()


@pytest.mark.parametrize("estimate", [None, -1, 129])
def test_metadata_preflight_cannot_bypass_cap(tmp_path, estimate: int | None) -> None:
    """Unknown or excessive metadata-query bytes stop before execution/publication."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = estimate
    report = tmp_path / "bytes_billed.csv"
    with pytest.raises(ValueError):
        record_bytes(
            client,
            "sample-project",
            "fixture_run",
            date(2020, 11, 1),
            datetime(2026, 10, 4, tzinfo=UTC),
            datetime(2026, 10, 5, tzinfo=UTC),
            report,
            max_bytes_billed=128,
        )
    assert client.query.call_count == 1
    assert client.query.call_args.kwargs["job_config"].dry_run is True
    assert not report.exists()


def test_unknown_processed_bytes_preserve_existing_report(tmp_path) -> None:
    """Known billed bytes do not justify publishing unknown processed bytes as zero."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=0),
        SimpleNamespace(
            result=lambda: [
                SimpleNamespace(
                    total_bytes_processed=None,
                    total_bytes_billed=0,
                    error_result=None,
                )
            ]
        ),
    ]
    report = tmp_path / "bytes_billed.csv"
    report.write_text("owner record must remain intact\n")
    with pytest.raises(ValueError, match="no processed-byte"):
        record_bytes(
            client,
            "sample-project",
            "fixture_run",
            date(2020, 11, 1),
            datetime(2026, 10, 4, tzinfo=UTC),
            datetime(2026, 10, 5, tzinfo=UTC),
            report,
            max_bytes_billed=128,
        )
    assert client.query.call_args.kwargs["job_config"].maximum_bytes_billed == 128
    assert report.read_text() == "owner record must remain intact\n"
