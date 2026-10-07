"""Prevent invalid native expected-row fixtures and execution during preflight."""

import pytest
import yaml

from pipeline.dbt_unit_preflight import reject_execution
from pipeline.profile import ROOT


def test_expected_rows_use_same_columns_for_native_union() -> None:
    """BigQuery requires all expected fixture UNION branches to share a shape."""
    paths = (
        ROOT / "dbt/models/intermediate/_unit_tests.yml",
        ROOT / "dbt/models/marts/_unit_tests.yml",
    )
    fixtures = [
        fixture
        for path in paths
        for fixture in yaml.safe_load(path.read_text())["unit_tests"]
    ]
    assert len(fixtures) == 3
    for fixture in fixtures:
        rows = fixture["expect"]["rows"]
        assert rows and all(set(row) == set(rows[0]) for row in rows)


def test_preflight_rejects_sql_execution_instead_of_simulating_test_passes() -> None:
    """Unexpected adapter execution must fail, including temporary-table writes."""
    with pytest.raises(RuntimeError, match="dry runs only"):
        reject_execution("CREATE TABLE owner_data AS SELECT 1")
