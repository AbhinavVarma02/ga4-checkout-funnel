"""Check native preflight cannot execute a macro or expand the rerun scope."""

from unittest.mock import Mock, patch

import pytest
from dbt.adapters.bigquery.impl import BigQueryAdapter

from pipeline import replay_rerun_preflight as module


def test_querying_compile_macro_is_blocked_before_query_submission() -> None:
    """Even an unexpected execute() in native compilation cannot submit SQL."""
    client = Mock()

    def unsafe_compile(_: list[str]) -> None:
        BigQueryAdapter.execute(None, "SELECT 1")

    runner = Mock()
    runner.invoke.side_effect = unsafe_compile
    with (
        patch.object(module, "verify_metadata", return_value={"raw_rows": 10}),
        patch.object(module, "dbtRunner", return_value=runner),
        pytest.raises(RuntimeError, match="forbids SQL execution"),
    ):
        module.prepare_rerun(client)
    client.query.assert_not_called()


@pytest.mark.parametrize("change", ["unfiltered", "full_refresh", "table", "merge"])
def test_initial_or_expanded_materialization_cannot_pass_rerun_preflight(
    change: str,
) -> None:
    """An initial CTAS/full refresh is not evidence for the approved rerun plan."""
    code = "WHERE session_start_date IN (SELECT DATE '2020-11-01' WHERE event_name = 'first_visit')"
    config = {
        "materialized": "incremental",
        "incremental_strategy": "insert_overwrite",
        "full_refresh": False,
    }
    if change == "unfiltered":
        code = "SELECT * FROM sessions"
    elif change == "full_refresh":
        config["full_refresh"] = True
    elif change == "table":
        config["materialized"] = "table"
    else:
        config["incremental_strategy"] = "merge"
    with pytest.raises(ValueError, match="incremental"):
        module.require_incremental_filter(code, config)
