"""Synthetic checks for pre-build dbt SQL dry runs."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.dbt_dry_run import dry_run_model, main


def test_compiled_select_is_only_dry_run(tmp_path: Path) -> None:
    """No query execution or materialization occurs in the pre-build check."""
    compiled = tmp_path / "compiled" / "staging"
    compiled.mkdir(parents=True)
    (compiled / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_value", encoding="utf-8"
    )
    client = Mock()
    client.query.return_value = SimpleNamespace(total_bytes_processed=123)
    report = tmp_path / "dry_runs.json"

    assert (
        dry_run_model(
            client,
            "stg_ga4_events",
            compiled_root=tmp_path / "compiled",
            dry_runs_path=report,
        )
        == 123
    )
    config = client.query.call_args.kwargs["job_config"]
    assert config.dry_run is True
    assert config.use_query_cache is False
    assert '"estimated_bytes": 123' in report.read_text(encoding="utf-8")


def test_only_approved_models_can_be_submitted(tmp_path: Path) -> None:
    """A caller cannot dry-run an arbitrary local SQL path."""
    with pytest.raises(ValueError, match="approved"):
        dry_run_model(Mock(), "../other", compiled_root=tmp_path)


def test_session_dry_run_inlines_unbuilt_staging_view(tmp_path: Path) -> None:
    """Validate intermediate SQL without creating its upstream view."""
    compiled = tmp_path / "compiled"
    (compiled / "intermediate").mkdir(parents=True)
    (compiled / "staging").mkdir(parents=True)
    (compiled / "intermediate" / "int_sessions.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_events`",
        encoding="utf-8",
    )
    (compiled / "staging" / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_value", encoding="utf-8"
    )
    client = Mock(project="fixture-project")
    client.query.return_value = SimpleNamespace(total_bytes_processed=321)

    dry_run_model(
        client,
        "int_sessions",
        compiled_root=compiled,
        dry_runs_path=tmp_path / "dry_runs.json",
        analytics_dataset="fixture_dataset",
    )

    sql = client.query.call_args.args[0]
    assert "(SELECT 1 AS fixture_value)" in sql
    assert "`fixture-project`.`fixture_dataset`.`stg_ga4_events`" not in sql


def test_product_dry_run_inlines_items_and_sessions(tmp_path: Path) -> None:
    """Product SQL references only the public-source SELECT after inlining."""
    compiled = tmp_path / "compiled"
    for folder in ("marts", "intermediate", "staging"):
        (compiled / folder).mkdir(parents=True)
    (compiled / "marts" / "fct_product_daily.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_items` "
        "JOIN `fixture-project`.`fixture_dataset`.`int_sessions` USING (fixture_key)",
        encoding="utf-8",
    )
    (compiled / "intermediate" / "int_sessions.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_events`",
        encoding="utf-8",
    )
    (compiled / "staging" / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_event", encoding="utf-8"
    )
    (compiled / "staging" / "stg_ga4_items.sql").write_text(
        "SELECT 1 AS fixture_item", encoding="utf-8"
    )
    client = Mock(project="fixture-project")
    client.query.return_value = SimpleNamespace(total_bytes_processed=456)

    dry_run_model(
        client,
        "fct_product_daily",
        compiled_root=compiled,
        dry_runs_path=tmp_path / "dry_runs.json",
        analytics_dataset="fixture_dataset",
    )

    sql = client.query.call_args.args[0]
    assert "(SELECT 1 AS fixture_item)" in sql
    assert "(SELECT * FROM (SELECT 1 AS fixture_event))" in sql
    assert "`fixture-project`.`fixture_dataset`" not in sql


def test_preflight_cap_records_estimate_and_rejects_oversize(tmp_path: Path) -> None:
    """Manual workflow preflight must fail before an oversized model can build."""
    compiled = tmp_path / "staging"
    compiled.mkdir()
    (compiled / "stg_ga4_events.sql").write_text("SELECT 1", encoding="utf-8")
    client = Mock()
    client.query.return_value = SimpleNamespace(total_bytes_processed=100)
    with pytest.raises(ValueError, match="per-query bytes limit"):
        dry_run_model(
            client,
            "stg_ga4_events",
            compiled_root=tmp_path,
            dry_runs_path=tmp_path / "dry.json",
            max_bytes_limit=50,
        )
    assert client.query.call_count == 1
    assert client.query.call_args.kwargs["job_config"].dry_run is True
    assert (tmp_path / "dry.json").exists()


@pytest.mark.parametrize("estimate", [None, -1])
def test_unknown_estimate_cannot_be_published(
    tmp_path: Path, estimate: int | None
) -> None:
    """Unavailable metadata cannot pass a byte cap or replace saved evidence."""
    compiled = tmp_path / "staging"
    compiled.mkdir()
    (compiled / "stg_ga4_events.sql").write_text("SELECT 1", encoding="utf-8")
    report = tmp_path / "dry.json"
    report.write_text('{"historical":true}', encoding="utf-8")
    client = Mock()
    client.query.return_value = SimpleNamespace(total_bytes_processed=estimate)
    with pytest.raises(ValueError, match="missing or negative"):
        dry_run_model(
            client,
            "stg_ga4_events",
            compiled_root=tmp_path,
            dry_runs_path=report,
            max_bytes_limit=128 * 1024**2,
        )
    assert report.read_text() == '{"historical":true}'
    assert client.query.call_count == 1


@pytest.mark.parametrize("explicit", [False, True])
def test_cli_uses_configured_cap_and_keeps_separate_report(
    tmp_path: Path, monkeypatch, explicit: bool
) -> None:
    """Manual preflights honor the selected cost scope and evidence destination."""
    report = tmp_path / "current_preflight.json"
    arguments = ["dbt_dry_run", "--all", "--report-path", str(report)]
    if explicit:
        arguments += ["--max-bytes-limit", "64"]
    monkeypatch.setattr("sys.argv", arguments)
    monkeypatch.setenv("GCP_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("BQ_DATASET_ANALYTICS", "fixture_replay")
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "128")
    monkeypatch.setattr("pipeline.dbt_dry_run.load_dotenv", lambda: None)
    monkeypatch.setattr("pipeline.dbt_dry_run.bigquery.Client", Mock())
    submit = Mock()
    monkeypatch.setattr("pipeline.dbt_dry_run.dry_run_model", submit)
    main()
    assert submit.call_count == 7
    for call in submit.call_args_list:
        assert call.kwargs["max_bytes_limit"] == (64 if explicit else 128)
        assert call.kwargs["dry_runs_path"] == report
        assert call.kwargs["analytics_dataset"] == "fixture_replay"
