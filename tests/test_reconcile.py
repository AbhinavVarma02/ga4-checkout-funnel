"""Unit checks for source/raw quality gating with labeled fixture rows."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from pipeline.reconcile import COMPARE_FIELDS, reconcile_day, reconciliation_sql

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reconciliation.json"


class FixtureRow(dict):
    """Mimic the BigQuery Row mapping interface for fixture values."""


def _fixture_rows() -> list[FixtureRow]:
    """Read synthetic rows that are explicitly labeled as test fixtures."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["label"].startswith("Fixture synthetic")
    return [FixtureRow(data["source"]), FixtureRow(data["raw"])]


def test_reconciliation_sql_filters_one_raw_partition() -> None:
    """The raw side must prune to the selected event date."""
    sql = reconciliation_sql(date(2020, 11, 1), "sample-project", "ga4_raw")
    assert "events_20201101" in sql
    assert "event_date = @event_date" in sql


def test_reconcile_day_accepts_matching_counts() -> None:
    """Matching fixture rows pass the quality gate."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=lambda: _fixture_rows()),
    ]

    result = reconcile_day(client, date(2020, 11, 1), "sample-project", "ga4_raw")

    assert result is not None
    assert result.event_count == 3
    assert result.purchase_count == 1
    assert result.purchase_revenue_total == Decimal("12.34")
    assert client.query.call_count == 2
    assert client.query.call_args.kwargs["job_config"].maximum_bytes_billed > 0


def test_reconcile_day_fails_on_purchase_mismatch() -> None:
    """A row count match cannot hide a purchase or revenue mismatch."""
    rows = _fixture_rows()
    rows[1]["purchase_count"] = 0
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=lambda: rows),
    ]

    with pytest.raises(ValueError, match="purchase_count"):
        reconcile_day(client, date(2020, 11, 1), "sample-project", "ga4_raw")


@pytest.mark.parametrize("field", COMPARE_FIELDS)
def test_each_reconciliation_signal_independently_blocks_mismatch(field: str) -> None:
    """No agreement in the other seven fields can conceal one changed signal."""
    rows = _fixture_rows()
    rows[1][field] = Decimal(str(rows[1][field])) + 1
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=lambda: rows),
    ]

    with pytest.raises(ValueError, match=field):
        reconcile_day(client, date(2020, 11, 1), "sample-project", "ga4_raw")


def test_matching_missing_revenue_remains_missing() -> None:
    """An agreed missing revenue value must not be converted to reported zero."""
    rows = _fixture_rows()
    for row in rows:
        row["purchase_revenue_total"] = None
        row["purchase_revenue_usd_total"] = None
        row["purchase_revenue_count"] = 0
        row["purchase_revenue_usd_count"] = 0
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=lambda: rows),
    ]

    result = reconcile_day(client, date(2020, 11, 1), "sample-project", "ga4_raw")

    assert result is not None
    assert result.purchase_revenue_total is None


def test_missing_revenue_and_zero_revenue_do_not_reconcile() -> None:
    """A zero amount cannot disguise an absent source revenue value."""
    rows = _fixture_rows()
    rows[0]["purchase_revenue_total"] = None
    rows[1]["purchase_revenue_total"] = Decimal(0)
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=lambda: rows),
    ]

    with pytest.raises(ValueError, match="purchase_revenue_total"):
        reconcile_day(client, date(2020, 11, 1), "sample-project", "ga4_raw")


def test_reconcile_day_dry_run_never_reads_rows() -> None:
    """Dry-run mode leaves the cloud data unqueried."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = 123

    result = reconcile_day(
        client, date(2020, 11, 1), "sample-project", "ga4_raw", dry_run_only=True
    )

    assert result is None
    assert client.query.call_count == 1


@pytest.mark.parametrize("estimate", [None, -1, 129])
def test_invalid_or_oversized_estimate_stops_before_execution(
    estimate: int | None,
) -> None:
    """Missing metadata cannot bypass the exact approved reconciliation cap."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = estimate
    with pytest.raises(ValueError):
        reconcile_day(
            client, date(2020, 11, 1), "sample-project", "ga4_raw", max_bytes_billed=128
        )
    assert client.query.call_count == 1
    assert client.query.call_args.kwargs["job_config"].dry_run is True


@pytest.mark.parametrize("cap", [0, -1])
def test_invalid_cap_stops_before_any_query(cap: int) -> None:
    """No cloud request is needed to reject an undefined cost boundary."""
    client = MagicMock(spec=bigquery.Client)
    with pytest.raises(ValueError, match="Positive"):
        reconcile_day(
            client, date(2020, 11, 1), "sample-project", "ga4_raw", max_bytes_billed=cap
        )
    client.query.assert_not_called()
