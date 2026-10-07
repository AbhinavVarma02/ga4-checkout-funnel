"""Exercise real dbt macro compilation without ADC or warehouse access."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("query_macro", [False, True])
def test_offline_lint_compiles_or_rejects_database_macro(
    tmp_path: Path, query_macro: bool
) -> None:
    """Actual SQL renders; introducing run_query fails before credential lookup."""
    project = tmp_path / "dbt"
    shutil.copytree(
        ROOT / "dbt",
        project,
        ignore=shutil.ignore_patterns("target", "logs", ".user.yml"),
    )
    if query_macro:
        model = project / "models/marts/dim_date.sql"
        model.write_text(
            "{% set forbidden = run_query('SELECT 1') %}\n" + model.read_text()
        )
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=str(ROOT / "src"),
        GOOGLE_APPLICATION_CREDENTIALS=str(tmp_path / "nonexistent-credentials.json"),
        GCP_PROJECT_ID="pending-project",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.local_dbt_lint",
            "--project-dir",
            str(project),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    output = result.stdout + result.stderr
    if query_macro:
        assert result.returncode != 0, output
        assert "Offline lint forbids warehouse connections" in output
    else:
        assert result.returncode == 0, output
        assert "8 files, 0 violations" in output
