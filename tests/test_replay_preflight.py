"""Check initial replay isolation and SQL inlining without cloud execution."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from pipeline.replay_preflight import initial_target_metadata, inline_test_sql


@pytest.mark.parametrize("target", ["ga4_analytics", "ga4_raw", "bad.dataset"])
def test_unsafe_target_is_rejected_before_cloud_access(target: str) -> None:
    """Preparation cannot select existing analysis or raw as a replay destination."""
    client = Mock(project="fixture-project")
    with pytest.raises(ValueError):
        initial_target_metadata(client, "ga4_raw", target)
    client.get_dataset.assert_not_called()
    client.query.assert_not_called()


def test_existing_target_is_rejected_without_scanning_or_mutating() -> None:
    """A populated or previously created target needs its own reviewed scope."""
    client = Mock(project="fixture-project")
    with pytest.raises(ValueError, match="already exists"):
        initial_target_metadata(client, "ga4_raw", "ga4_replay_analytics")
    client.query.assert_not_called()
    client.create_dataset.assert_not_called()


@pytest.mark.parametrize("expiration", [False, True])
def test_initial_target_reads_raw_metadata_only(expiration: bool) -> None:
    """Compatible US history passes; expiring raw is rejected without a write."""
    client = Mock(project="fixture-project")
    raw = bigquery.Dataset("fixture-project.ga4_raw")
    raw.location = "US"
    if expiration:
        raw.default_partition_expiration_ms = 1000
    client.get_dataset.side_effect = [NotFound("fixture absent"), raw]
    table = bigquery.Table.from_api_repr(
        {
            "tableReference": {
                "projectId": "fixture-project",
                "datasetId": "ga4_raw",
                "tableId": "ga4_events",
            },
            "id": "fixture-project:ga4_raw.ga4_events",
            "location": "US",
            "numRows": "3",
            "numBytes": "100",
            "timePartitioning": {"field": "event_date", "type": "DAY"},
            "clustering": {"fields": ["event_name"]},
        }
    )
    client.get_table.return_value = table
    if expiration:
        with pytest.raises(ValueError, match="incompatible"):
            initial_target_metadata(client, "ga4_raw", "ga4_replay_analytics")
    else:
        result = initial_target_metadata(client, "ga4_raw", "ga4_replay_analytics")
        assert result["analytics_dataset_exists"] is False
        assert result["raw_rows"] == 3
    client.query.assert_not_called()
    client.create_dataset.assert_not_called()
    client.create_table.assert_not_called()


def test_native_test_inlines_full_model_and_rejects_unknown_relation(
    tmp_path: Path,
) -> None:
    """A native test uses source SELECTs rather than relying on absent replay tables."""
    client = Mock(project="fixture-project")
    (tmp_path / "marts").mkdir()
    (tmp_path / "marts/dim_date.sql").write_text("SELECT DATE '2020-11-01' AS date_day")
    relation = "`fixture-project`.`replay`.`dim_date`"
    sql = inline_test_sql(
        f"SELECT * FROM {relation} WHERE date_day IS NULL", client, tmp_path, "replay"
    )
    assert relation not in sql
    assert "SELECT DATE '2020-11-01' AS date_day" in sql
    with pytest.raises(ValueError, match="Unresolved"):
        inline_test_sql(
            "SELECT * FROM `fixture-project`.`replay`.`unknown`",
            client,
            tmp_path,
            "replay",
        )
