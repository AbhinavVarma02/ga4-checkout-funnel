"""Execute the portable cohort CTE from the real dbt model on its synthetic fixture."""

import sqlite3
from pathlib import Path

import yaml

from pipeline.analysis_validation import trace_reach

ROOT = Path(__file__).resolve().parents[1]


def test_sessionless_first_visit_is_kept_by_actual_cohort_sql() -> None:
    """The actual CTE classifies valid sessions using sessionless first_visit rows."""
    model_dir = ROOT / "dbt/models/intermediate"
    tests = yaml.safe_load((model_dir / "_unit_tests.yml").read_text())["unit_tests"]
    fixture = next(
        item
        for item in tests
        if item["name"]
        == "session_logic_handles_ties_missing_keys_and_late_first_visit"
    )
    rows = fixture["given"][0]["rows"]
    columns = (
        "user_pseudo_id",
        "ga_session_id",
        "event_date",
        "event_timestamp_micros",
        "event_name",
    )
    sql = (model_dir / "int_sessions.sql").read_text()
    prefix, separator, _ = sql.partition("grouped_sessions AS (")
    assert separator, (
        "Actual cohort CTE boundary changed; update this portable SQL check"
    )
    portable = (
        prefix.rstrip()
        .removesuffix(",")
        .replace("{{ ref('stg_ga4_events') }}", "stg_ga4_events")
    )
    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE stg_ga4_events (user_pseudo_id TEXT, ga_session_id INTEGER, "
            "event_date TEXT, event_timestamp_micros INTEGER, event_name TEXT)"
        )
        connection.executemany(
            "INSERT INTO stg_ga4_events VALUES (?, ?, ?, ?, ?)",
            [tuple(row.get(column) for column in columns) for row in rows],
        )
        observed = connection.execute(
            portable + " SELECT user_pseudo_id FROM first_visit_users"
        ).fetchall()
    assert observed == [("cohort_user",)]
    tied = [row for row in rows if row["user_pseudo_id"] == "tied_user"]
    assert trace_reach(tied) == ([True] * 5, [True, False, False, False, False])
