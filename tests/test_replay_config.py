"""Verify actual dbt parsing keeps sandbox defaults and requires valid replay scope."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("replay", [False, True])
def test_dbt_parse_separates_sandbox_from_replay(tmp_path: Path, replay: bool) -> None:
    """Both modes parse offline; only explicit replay requests partitioned incrementals."""
    variables = {"pipeline_mode": "replay", "run_date": "2020-11-05"} if replay else {}
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/dbt"),
            "parse",
            "--project-dir",
            str(ROOT / "dbt"),
            "--profiles-dir",
            str(ROOT / "dbt"),
            "--target-path",
            str(tmp_path),
            "--no-partial-parse",
            "--vars",
            json.dumps(variables),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    for name in ("fct_sessions", "fct_funnel_daily", "fct_product_daily"):
        node = manifest["nodes"][f"model.ga4_checkout_funnel.{name}"]
        config = node["config"]
        assert "model.ga4_checkout_funnel.stg_ga4_events" in node["depends_on"]["nodes"]
        assert config["materialized"] == ("incremental" if replay else "table")
        if replay:
            assert config["incremental_strategy"] == "insert_overwrite"
            assert config["partition_by"]["field"] == "session_start_date"
            assert config["full_refresh"] is False
        else:
            assert config.get("partition_by") is None


def test_replay_without_run_date_is_rejected(tmp_path: Path) -> None:
    """An undefined daily write scope must fail during offline parsing."""
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/dbt"),
            "parse",
            "--project-dir",
            str(ROOT / "dbt"),
            "--profiles-dir",
            str(ROOT / "dbt"),
            "--target-path",
            str(tmp_path),
            "--no-partial-parse",
            "--vars",
            '{"pipeline_mode":"replay"}',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "replay requires run_date" in result.stdout + result.stderr
