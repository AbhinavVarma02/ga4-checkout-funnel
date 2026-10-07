"""Validate Power BI source schemas, references, and verified CSVs entirely offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from analysis.powerbi_project import (
    CSV_TABLES,
    FACTS,
    LIMITS,
    MODEL,
    PAGE_NAMES,
    POWERBI,
    REPORT,
    build_files,
    column_type,
    parse_measures,
)
from pipeline.profile import ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)


def verify_csv_inputs(root: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on missing, altered, partial, wrongly typed, or unverified CSVs."""
    observations = {}
    dimensions: dict[str, set[str]] = {"device_category": set(), "country": set()}
    fact_dimensions: dict[str, set[str]] = {key: set() for key in dimensions}
    dates: set[str] = set()
    fact_dates: set[str] = set()
    funnel: dict[tuple[str, int], dict[str, Any]] = defaultdict(
        lambda: {"reached": 0, "next": 0, "revenue": Decimal(0)}
    )
    sessions, purchases, session_revenue = 0, 0, Decimal(0)
    item_revenue = Decimal(0)
    matched_products: set[tuple[str, str]] = set()
    category_rows = []
    segments: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "purchases": 0, "revenue": Decimal(0)}
    )
    for table in CSV_TABLES:
        record = metrics["bi_exports"][table]
        path = root / "exports" / (table + ".csv")
        if record["file"] != str(path.relative_to(root)):
            raise ValueError(f"Unexpected CSV provenance path: {table}")
        if not path.is_file():
            raise ValueError(f"Missing verified CSV: {path}")
        if table != "category_summary" and record.get("verification") != "passed":
            raise ValueError(f"Unverified export: {table}")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != record["sha256"]:
            raise ValueError(f"CSV hash differs from verified provenance: {table}")
        rows = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != record["columns"]:
                raise ValueError(f"CSV headers differ: {table}")
            types = {column: column_type(column)[0] for column in record["columns"]}
            for row in reader:
                rows += 1
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"Malformed CSV row: {table}:{rows}")
                for column, value in row.items():
                    typ = types[column]
                    if typ == "boolean" and value not in {"true", "false"}:
                        raise ValueError(
                            f"Invalid CSV boolean: {table}.{column}:{rows}"
                        )
                    if value:
                        if typ == "dateTime":
                            date.fromisoformat(value)
                        elif typ == "int64":
                            int(value)
                        elif typ == "decimal":
                            amount = Decimal(value)
                            if not amount.is_finite() or amount != amount.quantize(
                                Decimal("0.0001")
                            ):
                                raise ValueError(
                                    "Fixed decimal cannot represent verified money losslessly"
                                )
                if table == "dim_date":
                    if row["date_day"] in dates:
                        raise ValueError("Duplicate date dimension key")
                    dates.add(row["date_day"])
                if table in FACTS:
                    fact_dates.add(row["session_start_date"])
                    for key, members in dimensions.items():
                        fact_dimensions[key].add(row[key])
                        if table == "fct_sessions":
                            members.add(row[key])
                if table == "fct_sessions":
                    sessions += 1
                    purchases += row["has_purchase"] == "true"
                    session_revenue += Decimal(row["purchase_revenue_usd"])
                    for key in ["device_category", "country", "user_cohort"]:
                        segment = segments[key, row[key]]
                        segment["sessions"] += 1
                        segment["purchases"] += row["has_purchase"] == "true"
                        segment["revenue"] += Decimal(row["purchase_revenue_usd"])
                elif table == "fct_funnel_daily":
                    key = (row["funnel_mode"], int(row["step_order"]))
                    funnel[key]["reached"] += int(row["reached_sessions"])
                    funnel[key]["next"] += int(row["next_step_reached_sessions"] or 0)
                    funnel[key]["revenue"] += Decimal(
                        row["purchase_revenue_usd_among_reached"]
                    )
                elif table == "fct_product_daily":
                    item_revenue += Decimal(row["purchase_item_revenue_usd"])
                    if int(row["view_and_purchase_sessions"]):
                        matched_products.add((row["item_id"], row["item_category"]))
                elif table == "category_summary":
                    category_rows.append(row)
        if rows != record["rows"]:
            raise ValueError(f"CSV row count differs: {table}")
        observations[table] = {
            "status": "passed",
            "rows": rows,
            "sha256": digest,
            "source_key": "bi_exports." + table,
        }
        LOGGER.info("Verified %s: %d rows", table, rows)
    if any(not fact_dimensions[key] <= dimensions[key] for key in dimensions):
        raise ValueError("Fact key missing from session-derived dimension")
    if fact_dates != dates:
        raise ValueError("Date dimension does not cover all fact dates")
    analysis = metrics["analysis"]
    profile = metrics["profiling_summary"]
    for kind, key in [("by_device", "device_category"), ("by_country", "country")]:
        for row in analysis[kind]:
            actual = segments[key, row[key]]
            if (
                actual["sessions"] != row["all_sessions"]
                or actual["purchases"] != row["purchase_sessions"]
                or actual["revenue"] != Decimal(row["purchase_revenue_usd"])
            ):
                raise ValueError("CSV segment differs from saved evidence")
    for row in analysis["user_cohorts"]:
        actual = segments["user_cohort", row["cohort"]]
        if (
            actual["sessions"] != row["sessions"]
            or actual["purchases"] != row["purchase_sessions"]
        ):
            raise ValueError("CSV cohort differs from saved evidence")
    if (
        sessions != analysis["all_sessions"]
        or purchases != analysis["purchase_sessions"]
        or session_revenue != Decimal(profile["purchase_revenue_usd"])
        or item_revenue != Decimal(profile["purchase_item_revenue_usd"])
        or len(matched_products)
        != metrics["product_analysis"]["product_category_groups_with_matched_purchase"]
    ):
        raise ValueError("CSV business totals do not reconcile to saved evidence")
    for step in analysis["global_funnel"]:
        order = step["step_order"]
        if (
            funnel["any_order", order]["reached"] != step["any_order_sessions"]
            or funnel["strict_ordered", order]["reached"]
            != step["strict_ordered_sessions"]
        ):
            raise ValueError("CSV funnel differs from saved evidence")
    for transition in analysis["dropoff_opportunities"]:
        order = next(
            s["step_order"]
            for s in analysis["global_funnel"]
            if s["step_name"] == transition["from_step"]
        )
        entering, continuing = (
            funnel["any_order", order],
            funnel["any_order", order + 1],
        )
        exact = (
            (entering["reached"] - continuing["reached"])
            * Fraction(continuing["revenue"])
            / continuing["reached"]
        )
        expected = transition["all_dropouts_recovered_potential_usd_exact"]
        if (
            exact != Fraction(expected["numerator"], expected["denominator"])
            or entering["next"] != continuing["reached"]
        ):
            raise ValueError("CSV step opportunity differs from saved evidence")
    entry, view = funnel["any_order", 1], funnel["any_order", 2]
    opportunity = (
        (entry["reached"] - view["reached"])
        * Fraction(view["revenue"])
        / view["reached"]
    )
    for scenario in analysis["recovery_scenarios"]:
        value = opportunity * Fraction(scenario["recovery_fraction_assumption"])
        floor = (value * 100).numerator // (value * 100).denominator
        if Decimal(floor) / 100 != Decimal(
            scenario["incremental_revenue_usd_scenario_floor_cents"]
        ):
            raise ValueError("CSV scenario differs from saved evidence")
    source = metrics["readonly_category_summary"]["rows"]
    expected_categories = {
        row["item_category"]: {k: "" if v is None else str(v) for k, v in row.items()}
        for row in source
    }
    if {r["item_category"]: r for r in category_rows} != expected_categories:
        raise ValueError("Category CSV differs from direct distinct-category source")
    return {
        "files": observations,
        "date_dimension_members": len(dates),
        "device_dimension_members": len(dimensions["device_category"]),
        "country_dimension_members": len(dimensions["country"]),
        "dimension_coverage": "passed",
        "fixed_decimal_precision": "passed",
        "saved_totals_funnels_opportunities_scenarios_categories": "passed",
        "scope": "CSV and Python checks; not Power Query or DAX execution",
    }


def walk(value: Any) -> Iterator[dict[str, Any]]:
    """Traverse nested PBIR semantic-query and formatting objects."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def definition_hash(powerbi: Path = POWERBI) -> str:
    """Hash names and contents identically to the native Microsoft parser check."""
    root = powerbi / MODEL / "definition"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.tmdl")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def validate_project(powerbi: Path = POWERBI) -> dict[str, Any]:
    """Validate actual files against vendored Microsoft schemas and model references."""
    schemas_path = powerbi / "validation/schemas/microsoft-schemas.json"
    bundle = _read_json(schemas_path)
    registry = Registry().with_resources(
        (uri, Resource.from_contents(schema)) for uri, schema in bundle.items()
    )
    # No network retrieval is registered: every $ref must exist in the bundle.
    model_path = powerbi / MODEL / "definition"
    tables, measures = {}, set()
    for path in model_path.joinpath("tables").glob("*.tmdl"):
        text = path.read_text()
        tables[path.stem] = set(re.findall(r"^\tcolumn (\w+)$", text, re.MULTILINE))
        measures |= set(re.findall(r"^\tmeasure '([^']+)' =", text, re.MULTILINE))
    expected_measures = {}
    for name in ["measures.dax", "prototype_measures.dax"]:
        expected_measures.update(parse_measures((powerbi / name).read_text()))
    if measures != set(expected_measures):
        raise ValueError("Missing or unexpected TMDL measure")
    host = model_path.joinpath("tables/fct_sessions.tmdl").read_text()
    for name, expr in expected_measures.items():
        match = re.search(
            r"\tmeasure '" + re.escape(name) + r"' =\n((?:\t\t\t.*\n)+)", host
        )
        if (
            not match
            or "\n".join(line[3:] for line in match[1].splitlines()).strip() != expr
        ):
            raise ValueError(f"TMDL changes canonical DAX: {name}")
    references = 0
    documents = []
    for path in sorted(powerbi.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".json",
            ".pbip",
            ".pbir",
            ".pbism",
        }:
            continue
        if (
            path.name == "project_manifest.json"
            or "validation" in path.relative_to(powerbi).parts
            or ".pbi" in path.parts
        ):
            continue
        obj = _read_json(path)
        uri = obj.get("$schema")
        if uri not in bundle:
            raise ValueError(f"Missing Microsoft schema: {path}")
        Draft7Validator(bundle[uri], registry=registry).validate(obj)
        documents.append(str(path.relative_to(powerbi)))
        sources = {
            node["Name"]: node["Entity"]
            for node in walk(obj)
            if "Name" in node and "Entity" in node
        }
        for node in walk(obj):
            for kind in ["Column", "Measure"]:
                if kind not in node or "Property" not in node[kind]:
                    continue
                query = node[kind]
                ref = query["Expression"]["SourceRef"]
                table = ref.get("Entity") or sources.get(ref.get("Source"))
                prop = query["Property"]
                if table not in tables or prop not in (
                    tables[table] if kind == "Column" else measures
                ):
                    raise ValueError(
                        f"Broken {kind} reference: {table}.{prop} in {path}"
                    )
                if kind == "Measure" and table != "fct_sessions":
                    raise ValueError("Measure reference points to wrong host table")
                references += 1
    pages_root = powerbi / REPORT / "definition/pages"
    page_order = _read_json(pages_root / "pages.json")
    if (
        page_order["pageOrder"] != list(PAGE_NAMES)
        or page_order["activePageName"] != "summary"
    ):
        raise ValueError("Incorrect report page order")
    visual_count = 0
    for name, label in PAGE_NAMES.items():
        page = _read_json(pages_root / name / "page.json")
        if page["displayName"] != label:
            raise ValueError("Incorrect page label")
        visuals = {
            p.parent.name: _read_json(p)
            for p in (pages_root / name / "visuals").glob("*/visual.json")
        }
        visual_count += len(visuals)
        for key, visual in visuals.items():
            pos = visual["position"]
            if (
                key != visual["name"]
                or pos["x"] < 0
                or pos["y"] < 0
                or pos["x"] + pos["width"] > page["width"]
                or pos["y"] + pos["height"] > page["height"]
            ):
                raise ValueError("Visual name or canvas bounds invalid")
        for interaction in page["visualInteractions"]:
            if (
                interaction["source"] not in visuals
                or interaction["target"] not in visuals
            ):
                raise ValueError("Broken visual interaction reference")
        required_isolation = {
            "summary": [("cohorts", "global_funnel")],
            "products": [
                ("product_performance", "category_performance"),
                ("category_performance", "product_performance"),
            ],
            "dropoff": [
                (source, target)
                for source in ["losses", "exposure", "step_evidence"]
                for target in ["entry_loss", "scenario", "recovery_fraction"]
            ],
        }.get(name, [])
        for source, target in required_isolation:
            if {"source": source, "target": target, "type": "NoFilter"} not in page[
                "visualInteractions"
            ]:
                raise ValueError("Missing interaction isolation for mismatched grains")
        if name == "products" and any(
            v["visual"]["visualType"] == "slicer" or "syncGroup" in v["visual"]
            for v in visuals.values()
        ):
            raise ValueError("Full-window products page must have no shared slicers")
        if name != "products":
            for key in ["date_filter", "device_filter", "country_filter"]:
                if visuals[key]["visual"]["syncGroup"]["groupName"] != key:
                    raise ValueError("Missing dimension slicer synchronization")
        # Visual formatting objects accept arbitrary properties in Microsoft's schema.
        # Validate the known filter-value wrapper separately so defaults are usable.
        if name in {"summary", "segments", "dropoff"}:
            key = "recovery_fraction" if name == "dropoff" else "funnel_mode"
            default = "0.05D" if name == "dropoff" else "'any_order'"
            try:
                selected = visuals[key]["visual"]["objects"]["general"][0][
                    "properties"
                ]["filter"]["filter"]
            except KeyError as exc:
                raise ValueError(
                    "Missing persisted slicer filter-value wrapper"
                ) from exc
            semantic_uri = next(
                uri for uri in bundle if uri.endswith("semanticQuery/1.3.0/schema.json")
            )
            Draft7Validator(
                {"$ref": semantic_uri + "#/definitions/FilterDefinition"},
                registry=registry,
            ).validate(selected)
            literals = [
                node["Literal"]["Value"] for node in walk(selected) if "Literal" in node
            ]
            if literals != [default]:
                raise ValueError("Incorrect persisted slicer default")
    dropoff_text = (pages_root / "dropoff/visuals/all_limits/visual.json").read_text()
    if any(limit not in dropoff_text for limit in LIMITS):
        raise ValueError("Missing visible required limitations")
    return {
        "status": "passed",
        "json_documents": len(documents),
        "visuals": visual_count,
        "model_field_references": references,
        "tables": len(tables),
        "measures": len(measures),
        "microsoft_json_schemas": len(bundle),
        "schema_bundle_sha256": hashlib.sha256(schemas_path.read_bytes()).hexdigest(),
        "canonical_dax_preserved": "passed",
        "slicers_interactions_bounds": "passed",
        "tmdl_definition_sha256": definition_hash(powerbi),
        "limitations": "Schemas and structural checks do not execute DAX/M or render visuals.",
    }


def main() -> None:
    """Check source artifacts; optionally record observed checks without altering metrics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-csv",
        action="store_true",
        help="Require and reconcile all five verified CSVs",
    )
    parser.add_argument(
        "--native-result", type=Path, help="Attach the actual native parser JSON output"
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Save evidence under powerbi_project_validation only",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    metrics = _read_json(ROOT / "reports/metrics.json")
    evidence = validate_project()
    expected = build_files(metrics)
    for path, content in expected.items():
        if (POWERBI / path).read_bytes() != content:
            raise ValueError(f"Project is not reproducible: {path}")
    evidence["reproducible_source_files"] = len(expected)
    if args.with_csv:
        evidence["csv_inputs"] = verify_csv_inputs(ROOT, metrics)
    if args.native_result:
        native = _read_json(args.native_result)
        if (
            native["status"] != "passed"
            or native["tmdl_definition_sha256"] != definition_hash()
        ):
            raise ValueError("Native result does not validate this definition")
        evidence["native_tmdl"] = native
    evidence["needs_from_human"] = [
        "Power BI Desktop open/refresh and DAX/filter execution",
        "Four-page render/visual review",
        "Screenshots",
        "Breadcrumb.pbix save",
        "Owner review and Power BI version record",
    ]
    evidence["source_keys"] = [
        "bi_exports",
        "analysis",
        "profiling_summary",
        "readonly_category_summary.rows",
    ]
    if args.record:
        evidence["checked_at_utc"] = datetime.now(UTC).isoformat()
        metrics["powerbi_project_validation"] = evidence
        _write_json(ROOT / "reports/metrics.json", metrics)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
