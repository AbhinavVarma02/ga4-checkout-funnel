"""Lint sandbox dbt SQL with real macros and no warehouse connections."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from sqlfluff.core import FluffConfig, Linter
from sqlfluff_templater_dbt.templater import DbtTemplater

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def reject_connection(*args: object, **kwargs: object) -> NoReturn:
    """Fail closed if a macro tries to inspect or query a warehouse."""
    raise RuntimeError("Offline lint forbids warehouse connections")


class OfflineDbtTemplater(DbtTemplater):
    """Use the pinned dbt compiler while omitting SQLFluff's relation-cache reads.

    SQLFluff's dbt templater populates a warehouse schema cache even when the
    project SQL needs no introspection. The sandbox models can render without
    that cache. Connection opening is disabled on this adapter instance, so a
    future macro requiring database metadata fails instead of using local ADC.
    This deliberately supports sandbox SQL only; replay DML still needs cloud
    validation. The override depends on the versions pinned in uv.lock.
    """

    def __init__(self, project_dir: Path) -> None:
        super().__init__()
        self.local_project_dir = str(project_dir)

    def _get_project_dir(self) -> str:
        """Keep child SQLFluff configurations from changing the selected project."""
        return self.local_project_dir

    def _get_profiles_dir(self) -> str:
        """Use only the selected project's env-based profile."""
        return self.local_project_dir

    def _get_dbt_skip_compilation_error(self) -> bool:
        """A failed compilation must fail CI rather than count as a clean file."""
        return False

    @contextmanager
    def connection(self) -> Iterator[None]:
        """Register dbt's real macro context without opening a connection."""
        from dbt.adapters.factory import get_adapter
        from dbt.context.providers import generate_runtime_macro_context

        adapter = self.adapters.get(self.project_dir)
        if adapter is None:
            adapter = get_adapter(self.dbt_config)
            adapter.connections.open = reject_connection
            adapter.acquire_connection("offline_lint")
            adapter.set_macro_resolver(self.dbt_manifest)
            adapter.set_macro_context_generator(generate_runtime_macro_context)
            self.adapters[self.project_dir] = adapter
        yield


def lint_project(project_dir: Path) -> int:
    """Lint all sandbox models and the singular test, failing on every violation."""
    os.environ["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    config = FluffConfig.from_path(str(project_dir))
    config.set_value(["templater", "dbt", "project_dir"], str(project_dir))
    config.set_value(["templater", "dbt", "profiles_dir"], str(project_dir))
    config.set_value(["templater", "dbt", "dbt_skip_compilation_error"], False)
    linter = Linter(config=config)
    linter.templater = OfflineDbtTemplater(project_dir)
    results = linter.lint_paths(
        (
            str(project_dir / "models"),
            str(project_dir / "tests/ordered_funnel_nonincreasing.sql"),
        ),
        processes=1,
    )
    for record in results.as_records():
        for violation in record["violations"]:
            LOGGER.error(
                "%s:%s %s %s",
                record["filepath"],
                violation["start_line_no"],
                violation["code"],
                violation["description"],
            )
    stats = results.stats(fail_code=1, success_code=0)
    expected_files = len(list((project_dir / "models").rglob("*.sql"))) + 1
    if stats["files"] != expected_files:
        raise ValueError("Offline lint did not check every expected SQL file")
    LOGGER.info(
        "Offline dbt SQL lint: %s; %s files, %s violations; warehouse connections forbidden",
        stats["status"],
        stats["files"],
        stats["violations"],
    )
    return int(stats["exit code"])


def main() -> None:
    """Run the credential-free sandbox lint used by local checks and CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT / "dbt")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("sqlfluff").setLevel(logging.WARNING)
    project_dir = args.project_dir.resolve()
    os.chdir(project_dir)
    raise SystemExit(lint_project(project_dir))


if __name__ == "__main__":
    main()
