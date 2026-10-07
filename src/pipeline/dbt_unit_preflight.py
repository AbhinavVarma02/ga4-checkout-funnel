"""Compile pinned native dbt unit fixtures and dry-run their synthetic SQL only."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any
from unittest.mock import patch

from dbt.cli.main import dbtRunner
from dbt.context.providers import generate_runtime_model_context
from dbt.graph import ResourceTypeSelector
from dbt.node_types import NodeType
from dbt.parser.unit_tests import UnitTestManifestLoader
from dbt.task.compile import CompileRunner, CompileTask
from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.mart_validation import CHECKS, sha256
from pipeline.profile import DRY_RUNS_PATH, _read_json, _write_json

LOGGER = logging.getLogger(__name__)


def reject_execution(*_: Any, **__: Any) -> None:
    """Reject any attempted SQL execution during fixture compilation."""
    raise RuntimeError(
        "Unit preflight permits metadata APIs and BigQuery dry runs only"
    )


def unit_selector(task: CompileTask) -> ResourceTypeSelector:
    """Select native unit definitions, which ordinary dbt compile excludes."""
    return ResourceTypeSelector(
        graph=task.graph,
        manifest=task.manifest,
        previous_state=task.previous_state,
        resource_types=[NodeType.Unit],
        selectors=task.config.selectors,
    )


class UnitCompileRunner(CompileRunner):
    """Use TestRunner's pinned manifest/compiler path without its materialization."""

    def compile(self, manifest: Any) -> Any:
        """Dry-run native main/expected SQL before any temporary-table operation."""
        with self.adapter.connection_named(self.node.unique_id):
            return self._compile_fixture(manifest)

    def _compile_fixture(self, manifest: Any) -> Any:
        """Retain a native metadata connection while all SQL execution is blocked."""
        loader = UnitTestManifestLoader(manifest, self.config, {self.node.unique_id})
        fixture_manifest = loader.load()
        node = self.compiler.compile_node(
            fixture_manifest.nodes[self.node.unique_id], fixture_manifest, {}
        )
        client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"], location="US")

        def dry_run(sql: str) -> bigquery.QueryJob:
            job = client.query(
                sql,
                location="US",
                job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
            )
            if job.total_bytes_processed != 0:
                raise ValueError(
                    "Synthetic unit preflight must scan zero warehouse bytes"
                )
            return job

        main = dry_run(node.compiled_code)
        context = generate_runtime_model_context(node, self.config, fixture_manifest)
        native_columns = [
            self.adapter.Column.create_from_field(field) for field in main.schema
        ]
        types = {column.name.lower(): column.data_type for column in native_columns}
        quoted = {column.name.lower(): column.quoted for column in native_columns}
        expected_rows = node.config.expected_rows
        columns = list(expected_rows[0]) if expected_rows else list(types)
        expected_sql = node.config.expected_sql or context["get_expected_sql"](
            expected_rows, types, quoted
        )
        sql = context["get_unit_test_sql"](
            node.compiled_code, expected_sql, [quoted[name] for name in columns]
        )
        dry_run(sql)
        # Native materialization uses one empty scratch CTAS, one synthetic
        # comparison SELECT, then adapter cleanup of that table. No replay DML.
        target = context["this"].incorporate(type="table")
        temporary = context["make_temp_relation"](target)
        scratch_sql = context["get_create_table_as_sql"](
            True, temporary, context["get_empty_subquery_sql"](node.compiled_code)
        )
        dry_run(scratch_sql)
        CHECKS.mkdir(parents=True, exist_ok=True)
        (CHECKS / f"unit_{node.name}.sql").write_text(sql)
        evidence = {
            "unique_id": node.unique_id,
            "estimated_comparison_bytes": 0,
            "estimated_empty_scratch_ctas_bytes": 0,
            "compiled_model_sql_sha256": sha256(node.compiled_code),
            "comparison_sql_sha256": sha256(sql),
            "scratch_ctas_sql_sha256": sha256(scratch_sql),
            "expected_columns": columns,
            "executed": False,
            "checked_at_utc": datetime.now(UTC),
        }
        _write_json(CHECKS / f"unit_{node.name}.json", evidence)
        LOGGER.info(
            "Synthetic unit %s: zero-byte SELECT and empty scratch CTAS", node.name
        )
        return node


def main() -> None:
    """Compile and dry-run three fixtures, never substituting for native test passes."""
    if version("dbt-core") != "1.12.5" or version("dbt-bigquery") != "1.12.1":
        raise RuntimeError(
            "Unit compilation adapter requires the repository's exact pins"
        )
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dbt.adapters.bigquery.impl import BigQueryAdapter

    with (
        patch.object(CompileTask, "get_node_selector", unit_selector),
        patch.object(CompileTask, "get_runner_type", lambda *_: UnitCompileRunner),
        patch.object(BigQueryAdapter, "execute", reject_execution),
    ):
        result = dbtRunner().invoke(
            [
                "compile",
                "--project-dir",
                "dbt",
                "--profiles-dir",
                "dbt",
                "--select",
                "test_type:unit",
                "--no-introspect",
                "--target-path",
                str(CHECKS / "unit_compile"),
            ]
        )
    if not result.success:
        raise RuntimeError(
            "Native fixture compilation/dry-run failed"
        ) from result.exception
    assert len(result.result.results) == 3
    report = _read_json(DRY_RUNS_PATH)
    report["p2_5_unit_preflight"] = {
        "method": "Pinned native UnitTestManifestLoader/compiler and unit SQL macros; adapter SQL execution forbidden; metadata APIs plus zero-byte BigQuery dry runs only",
        "fixtures": [
            _read_json(CHECKS / f"unit_{r.node.name}.json")
            for r in result.result.results
        ],
        "native_unit_pass_claim": False,
    }
    _write_json(DRY_RUNS_PATH, report)


if __name__ == "__main__":
    main()
