"""Validate a real dbt catalog against actual warehouse metadata and descriptions."""

from __future__ import annotations

import re
from typing import Any


def normalize_type(value: str) -> str:
    """Compare BigQuery API/SQL aliases while retaining nested field/type structure."""
    result = re.sub(r"\s+|`", "", value.upper())
    for alias, sql_type in (
        ("INTEGER", "INT64"),
        ("BOOLEAN", "BOOL"),
        ("FLOAT", "FLOAT64"),
    ):
        result = re.sub(rf"\b{alias}\b", sql_type, result)
    return result


def verify_catalog(
    catalog: dict[str, Any],
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
    public_schema: list[dict[str, str]],
) -> dict[str, Any]:
    """Require every model/column and the real public source; raw remains unbuilt."""
    if catalog["errors"]:
        raise ValueError("Actual catalog contains generation errors")
    if catalog["metadata"]["invocation_id"] != manifest["metadata"]["invocation_id"]:
        raise ValueError("Catalog and manifest come from different invocations")
    models = {
        uid: node
        for uid, node in manifest["nodes"].items()
        if node["resource_type"] == "model"
    }
    if not models or set(catalog["nodes"]) != set(models):
        raise ValueError("Actual catalog does not cover every model")
    counts = {}
    for uid, node in models.items():
        actual = snapshot["relations"][node["name"]]
        entry = catalog["nodes"][uid]
        metadata = entry["metadata"]
        if (
            metadata["database"] != node["database"]
            or metadata["schema"] != node["schema"]
            or metadata["name"] != node["alias"]
            or metadata["type"].upper() != actual["relation_type"]
        ):
            raise ValueError("Catalog relation identity/type mismatch")
        columns = sorted(entry["columns"].values(), key=lambda column: column["index"])
        actual_columns = actual["schema"]
        names = [column["name"] for column in actual_columns]
        if [column["name"] for column in columns] != names or list(
            node["columns"]
        ) != names:
            raise ValueError("Actual catalog column names/order mismatch")
        if not node["description"].strip() or any(
            not column["description"].strip() for column in node["columns"].values()
        ):
            raise ValueError("Model or column lacks a dbt description")
        for column, field in zip(columns, actual_columns, strict=True):
            if normalize_type(column["type"]) != normalize_type(field["type"]):
                raise ValueError("Actual catalog column type mismatch")
        counts[node["name"]] = len(columns)
    source_id = "source.ga4_checkout_funnel.ga4_public.events"
    if set(catalog["sources"]) != {source_id}:
        raise ValueError(
            "Actual public wildcard catalog missing or includes unbuilt raw"
        )
    source = catalog["sources"][source_id]
    columns = source["columns"]
    expected = {field["name"]: normalize_type(field["type"]) for field in public_schema}
    actual_types = {
        column["name"]: normalize_type(column["type"]) for column in columns.values()
    }
    if actual_types != expected:
        raise ValueError(
            "Public catalog schema differs from actual latest source table"
        )
    stats = source["stats"]
    if (
        int(stats["date_shards"]["value"]) != 92
        or int(stats["date_shard_min"]["value"]) != 20201101
        or int(stats["date_shard_max"]["value"]) != 20210131
    ):
        raise ValueError("Public catalog shard coverage differs from approved sample")
    return {
        "status": "passed",
        "models": len(models),
        "described_actual_model_columns": sum(counts.values()),
        "model_column_counts": counts,
        "names_order_types_match_actual_metadata": True,
        "actual_public_source_fields": len(columns),
        "actual_public_source_shards": int(stats["date_shards"]["value"]),
        "public_schema_matches_latest_source_table": True,
        "raw_source_status": "declared in manifest; warehouse resource intentionally uncreated and absent from actual catalog",
        "description_scope": "dbt manifest model/column descriptions; catalog supplies actual types, not warehouse comment persistence",
    }
