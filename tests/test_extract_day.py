"""Unit checks for a simulated GA4 day load; no real data or cloud writes."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from google.cloud import bigquery

from pipeline.extract_day import (
    ensure_destination,
    extract_day,
    extract_sql,
    source_table_id,
)


def test_source_table_rejects_dates_outside_sample() -> None:
    """Never generate a source table outside the stated public window."""
    with pytest.raises(ValueError, match="Day must be within"):
        source_table_id(date(2021, 2, 1))


def test_extract_sql_casts_date_for_partitioning() -> None:
    """The raw event_date must be a DATE column without duplicate names."""
    sql = extract_sql(date(2020, 11, 1))
    assert "PARSE_DATE('%Y%m%d', event_date) AS event_date" in sql
    assert "* EXCEPT(event_date)" in sql
    assert "events_20201101" in sql


def test_dry_run_does_not_read_metadata_or_write() -> None:
    """A dry run estimates one day without creating cloud resources."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = 123

    result = extract_day(
        client,
        date(2020, 11, 1),
        "portfolio-project",
        "ga4_raw",
        run_label="fixture_run",
        dry_run_only=True,
    )

    assert result.estimated_bytes == 123
    assert result.billed_bytes is None
    assert client.query.call_count == 1
    assert client.query.call_args.kwargs["job_config"].dry_run is True
    client.get_table.assert_not_called()


def test_estimate_limit_prevents_creation() -> None:
    """A too-large estimate stops before any dataset or table work."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = 124

    with pytest.raises(ValueError, match="exceeds"):
        extract_day(
            client,
            date(2020, 11, 1),
            "portfolio-project",
            "ga4_raw",
            run_label="fixture_run",
            max_bytes_billed=123,
        )

    client.get_table.assert_not_called()
    client.create_dataset.assert_not_called()
    client.create_table.assert_not_called()


@pytest.mark.parametrize("billed_bytes", [123, None])
def test_full_day_replaces_only_selected_partition(billed_bytes: int | None) -> None:
    """Reruns target the same partition with WRITE_TRUNCATE."""
    client = MagicMock(spec=bigquery.Client)
    estimate = MagicMock(total_bytes_processed=123)
    job = MagicMock(total_bytes_billed=billed_bytes, job_id="fixture-job")
    client.query.side_effect = [estimate, job]
    source = bigquery.Table(
        "bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_20201101"
    )
    source.schema = [
        bigquery.SchemaField("event_date", "STRING"),
        bigquery.SchemaField("event_name", "STRING"),
    ]
    client.get_table.return_value = source

    with patch(
        "pipeline.extract_day.ensure_destination",
        return_value="portfolio-project.ga4_raw.ga4_events",
    ):
        result = extract_day(
            client,
            date(2020, 11, 1),
            "portfolio-project",
            "ga4_raw",
            run_label="fixture_run",
        )

    config = client.query.call_args.kwargs["job_config"]
    assert config.destination.table_id == "ga4_events$20201101"
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    assert config.create_disposition == bigquery.CreateDisposition.CREATE_NEVER
    assert config.labels["ga4_run"] == "fixture_run"
    assert result.job_id == "fixture-job"
    assert result.billed_bytes == billed_bytes


@pytest.mark.parametrize("incompatible", ["nested_schema", "expires", "hour_partition"])
def test_existing_raw_metadata_is_rejected_before_load(incompatible: str) -> None:
    """Reruns reject nested schema drift, expiring data, and non-daily partitions."""
    client = MagicMock(spec=bigquery.Client)
    dataset = bigquery.Dataset("portfolio-project.ga4_raw")
    dataset.location = "US"
    client.get_dataset.return_value = dataset
    schema = [
        bigquery.SchemaField("event_date", "DATE"),
        bigquery.SchemaField(
            "event_params",
            "RECORD",
            mode="REPEATED",
            fields=[bigquery.SchemaField("key", "STRING")],
        ),
    ]
    table = bigquery.Table("portfolio-project.ga4_raw.ga4_events", schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="event_date", type_="DAY")
    table.clustering_fields = ["event_name"]
    if incompatible == "nested_schema":
        table.schema = [
            schema[0],
            bigquery.SchemaField(
                "event_params",
                "RECORD",
                mode="REPEATED",
                fields=[bigquery.SchemaField("key", "INTEGER")],
            ),
        ]
    elif incompatible == "expires":
        table.expires = datetime(2026, 10, 5, tzinfo=UTC)
    else:
        table.time_partitioning = bigquery.TimePartitioning(
            field="event_date", type_="HOUR"
        )
    client.get_table.return_value = table
    with pytest.raises(ValueError):
        ensure_destination(client, "portfolio-project", "ga4_raw", "US", schema)
    client.create_dataset.assert_not_called()
    client.create_table.assert_not_called()


@pytest.mark.parametrize("cap", [0, -1])
def test_invalid_extraction_cap_prevents_any_query(cap: int) -> None:
    """Direct extractor callers must also supply a positive cost boundary."""
    client = MagicMock(spec=bigquery.Client)
    with pytest.raises(ValueError, match="Positive"):
        extract_day(
            client,
            date(2020, 11, 1),
            "portfolio-project",
            "ga4_raw",
            run_label="fixture",
            max_bytes_billed=cap,
        )
    client.query.assert_not_called()
    client.query.assert_not_called()


@pytest.mark.parametrize("estimate", [None, -1])
def test_unknown_estimate_prevents_resource_creation(estimate: int | None) -> None:
    """An unavailable extraction estimate cannot be interpreted as a free load."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = estimate
    with pytest.raises(ValueError, match="missing or negative"):
        extract_day(
            client,
            date(2020, 11, 1),
            "portfolio-project",
            "ga4_raw",
            run_label="fixture",
        )
    assert client.query.call_count == 1
    client.create_dataset.assert_not_called()
    client.create_table.assert_not_called()
