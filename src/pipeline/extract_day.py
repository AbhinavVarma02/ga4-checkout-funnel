"""Replace one historical GA4 day in a date-partitioned BigQuery raw table.

This is a simulated feed over public historical data. Running a non-dry load
creates cloud resources when absent and requires the owner's hard-stop approval.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from dataclasses import dataclass
from datetime import date

from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

LOGGER = logging.getLogger(__name__)
PUBLIC_PROJECT = "bigquery-public-data"
PUBLIC_DATASET = "ga4_obfuscated_sample_ecommerce"
FIRST_DAY = date(2020, 11, 1)
LAST_DAY = date(2021, 1, 31)
type SchemaSignature = tuple[tuple[str, str, str, SchemaSignature], ...]


@dataclass(frozen=True)
class LoadResult:
    """BigQuery job evidence for one daily extraction."""

    day: date
    estimated_bytes: int
    billed_bytes: int | None
    job_id: str | None


def source_table_id(day: date) -> str:
    """Return the exact public daily table after validating the sample window."""
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError(f"Day must be within {FIRST_DAY} and {LAST_DAY}")
    return f"{PUBLIC_PROJECT}.{PUBLIC_DATASET}.events_{day:%Y%m%d}"


def extract_sql(day: date) -> str:
    """Cast the GA4 string date to DATE for partitioning, preserving other fields."""
    source = source_table_id(day)
    return (
        "SELECT PARSE_DATE('%Y%m%d', event_date) AS event_date, "
        f"* EXCEPT(event_date) FROM `{source}`"
    )


def _target_schema(source: bigquery.Table) -> list[bigquery.SchemaField]:
    """Derive raw schema from actual source metadata and validate key fields."""
    fields = {field.name: field for field in source.schema}
    if fields.get("event_date") is None or fields["event_date"].field_type != "STRING":
        raise ValueError("Source event_date must exist as STRING")
    if fields.get("event_name") is None or fields["event_name"].field_type != "STRING":
        raise ValueError("Source event_name must exist as STRING")
    return [
        bigquery.SchemaField("event_date", "DATE", mode=field.mode)
        if field.name == "event_date"
        else field
        for field in source.schema
    ]


def _schema_signature(
    schema: list[bigquery.SchemaField],
) -> SchemaSignature:
    """Compare field names, types, modes, and nested shapes on reruns."""
    return tuple(
        (
            field.name,
            field.field_type,
            field.mode,
            _schema_signature(list(field.fields)),
        )
        for field in schema
    )


def ensure_destination(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    location: str,
    schema: list[bigquery.SchemaField],
) -> str:
    """Create the US raw dataset and table once; reject incompatible existing ones."""
    if location.upper() != "US":
        raise ValueError("The public source is in the US multi-region")
    dataset_name = f"{project_id}.{dataset_id}"
    try:
        dataset = client.get_dataset(dataset_name)
    except NotFound:
        dataset = bigquery.Dataset(dataset_name)
        dataset.location = "US"
        dataset = client.create_dataset(dataset, exists_ok=True)
        LOGGER.info("Created raw dataset %s", dataset_name)
    if dataset.location.upper() != "US":
        raise ValueError("Raw dataset must be in the US multi-region")
    if dataset.default_table_expiration_ms or dataset.default_partition_expiration_ms:
        raise ValueError("Remove dataset table and partition expiration before loading")

    table_name = f"{dataset_name}.ga4_events"
    try:
        table = client.get_table(table_name)
    except NotFound:
        table = bigquery.Table(table_name, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="event_date",
        )
        table.clustering_fields = ["event_name"]
        table = client.create_table(table, exists_ok=True)
        LOGGER.info("Created partitioned raw table %s", table_name)
    if (
        table.time_partitioning is None
        or table.time_partitioning.field != "event_date"
        or table.time_partitioning.type_ != bigquery.TimePartitioningType.DAY
    ):
        raise ValueError("Raw table must be partitioned daily by event_date")
    if table.expires is not None:
        raise ValueError("Remove raw table expiration before loading")
    if table.time_partitioning.expiration_ms:
        raise ValueError("Remove raw table partition expiration before loading")
    if table.clustering_fields != ["event_name"]:
        raise ValueError("Raw table must be clustered by event_name")
    if _schema_signature(list(table.schema)) != _schema_signature(schema):
        raise ValueError("Raw table schema differs from the public source schema")
    return table_name


def extract_day(
    client: bigquery.Client,
    day: date,
    project_id: str,
    dataset_id: str,
    *,
    run_label: str,
    location: str = "US",
    max_bytes_billed: int = 10 * 1024**3,
    dry_run_only: bool = False,
) -> LoadResult:
    """Dry-run first, then replace exactly one partition if permitted."""
    if max_bytes_billed <= 0:
        raise ValueError("Positive extraction byte cap required")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", run_label) is None:
        raise ValueError("run_label must be a valid BigQuery label value")
    sql = extract_sql(day)
    estimate = client.query(
        sql,
        location=location,
        job_config=bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            labels={"app": "ga4_checkout_funnel", "ga4_run": run_label},
        ),
    )
    if estimate.total_bytes_processed is None or estimate.total_bytes_processed < 0:
        raise ValueError("Extraction dry-run estimate is missing or negative")
    estimated_bytes = int(estimate.total_bytes_processed)
    LOGGER.info("Dry run for %s estimated %d bytes", day, estimated_bytes)
    if estimated_bytes > max_bytes_billed:
        raise ValueError("Dry-run estimate exceeds the per-day bytes limit")
    if dry_run_only:
        return LoadResult(day, estimated_bytes, None, None)

    source = client.get_table(source_table_id(day))
    table_name = ensure_destination(
        client, project_id, dataset_id, location, _target_schema(source)
    )
    destination = f"{table_name}${day:%Y%m%d}"
    job = client.query(
        sql,
        location=location,
        job_config=bigquery.QueryJobConfig(
            destination=destination,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
            maximum_bytes_billed=max_bytes_billed,
            use_query_cache=False,
            labels={"app": "ga4_checkout_funnel", "ga4_run": run_label},
        ),
    )
    job.result()
    billed_bytes = (
        int(job.total_bytes_billed) if job.total_bytes_billed is not None else None
    )
    LOGGER.info(
        "Replaced %s; job=%s, billed_bytes=%s", destination, job.job_id, billed_bytes
    )
    return LoadResult(day, estimated_bytes, billed_bytes, job.job_id)


def main() -> None:
    """Run a validated single-day extraction from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "day", type=date.fromisoformat, help="YYYY-MM-DD in sample window"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Estimate bytes without writes"
    )
    parser.add_argument("--max-bytes-billed", type=int)
    parser.add_argument(
        "--run-label", required=True, help="Unique lowercase BigQuery job label"
    )
    args = parser.parse_args()
    load_dotenv()
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = bigquery.Client(
        project=project_id, location=os.getenv("BQ_LOCATION", "US")
    )
    extract_day(
        client,
        args.day,
        project_id,
        os.getenv("BQ_DATASET_RAW", "ga4_raw"),
        run_label=args.run_label,
        location=os.getenv("BQ_LOCATION", "US"),
        max_bytes_billed=(
            args.max_bytes_billed
            if args.max_bytes_billed is not None
            else int(os.getenv("BQ_MAX_BYTES_BILLED", str(10 * 1024**3)))
        ),
        dry_run_only=args.dry_run,
    )


if __name__ == "__main__":
    main()
