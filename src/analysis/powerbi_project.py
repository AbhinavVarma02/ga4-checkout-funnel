"""Build a deterministic, CSV-only PBIP/PBIR/TMDL prototype without cloud access."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from pipeline.profile import ROOT, _read_json

LOGGER = logging.getLogger(__name__)
POWERBI = ROOT / "powerbi"
REPORT = "Breadcrumb.Report"
MODEL = "Breadcrumb.SemanticModel"
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/"
SCHEMAS = {
    "pbip": SCHEMA_BASE + "pbip/pbipProperties/1.0.0/schema.json",
    "pbir": SCHEMA_BASE + "item/report/definitionProperties/2.0.0/schema.json",
    "pbism": SCHEMA_BASE + "item/semanticModel/definitionProperties/1.0.0/schema.json",
    **{
        name: SCHEMA_BASE + f"item/report/definition/{kind}/{version}/schema.json"
        for name, kind, version in [
            ("report", "report", "1.0.0"),
            ("page", "page", "2.0.0"),
            ("visual", "visualContainer", "2.1.0"),
            ("pages", "pagesMetadata", "1.0.0"),
            ("version", "versionMetadata", "1.0.0"),
        ]
    },
}
CSV_TABLES = (
    "fct_sessions",
    "fct_funnel_daily",
    "fct_product_daily",
    "dim_date",
    "category_summary",
)
FACTS = CSV_TABLES[:3]
PAGE_NAMES = {
    "summary": "Summary",
    "segments": "Funnel by device and country",
    "dropoff": "Drop-off revenue by step",
    "products": "Product and category performance",
}
TEXT_COLUMNS = {
    "user_pseudo_id",
    "device_category",
    "country",
    "first_touch_source",
    "first_touch_medium",
    "first_touch_channel",
    "user_cohort",
    "user_cohort_label",
    "funnel_mode",
    "step_name",
    "item_id",
    "item_category",
    "item_name",
}
WINDOWS_EXPORTS = (
    r"\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\exports"
)
USD = '"$"#,0.00;("$"#,0.00);"$"0.00'
LIMITS = (
    "LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users",
    "LIMIT: obfuscated sample data; some totals don't fully reconcile",
    "LIMIT: channel results are first-touch unless session-level source exists in the data",
    "LIMIT: the daily pipeline replays historical daily tables as a simulated feed",
)
FOOTER = (
    "Hypothetical stakeholder · Public obfuscated GA4 sample · "
    "2020-11-01 to 2021-01-31 · Prototype; Desktop validation pending"
)


def json_bytes(value: Any) -> bytes:
    """Use stable UTF-8 formatting for reviewable source control diffs."""
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def parse_measures(text: str) -> dict[str, str]:
    """Extract the separately authored measures without changing their expressions."""
    clean = "\n".join(line for line in text.splitlines() if not line.startswith("//"))
    matches = list(re.finditer(r"^([A-Za-z][A-Za-z0-9 ]*) =", clean, re.MULTILINE))
    return {
        match[1]: clean[
            match.end() : matches[i + 1].start() if i + 1 < len(matches) else None
        ].strip()
        for i, match in enumerate(matches)
    }


def column_type(column: str) -> tuple[str, str]:
    """Map the verified CSV columns to explicit TOM and Power Query types."""
    if column in {"session_start_date", "date_day"}:
        return "dateTime", "type date"
    if column.startswith(("has_", "ordered_")):
        return "boolean", "type logical"
    if column.endswith("_usd") or "revenue_usd_" in column:
        return "decimal", "Currency.Type"
    if column == "fraction":
        return "double", "type number"
    if column in TEXT_COLUMNS:
        return "string", "type text"
    return "int64", "Int64.Type"


def lineage(name: str) -> str:
    """Provide stable object lineage IDs independent of the build date."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "breadcrumb-powerbi/" + name))


def m_csv_source(table: str, columns: list[str]) -> str:
    """Import exact UTF-8 CSV headers/types; preserve blank labels and null money."""
    pairs = ",\n        ".join(
        '{"' + column + '", ' + column_type(column)[1] + "}"
        for column in columns
        if column_type(column)[0] != "boolean"
    )
    flags = [column for column in columns if column_type(column)[0] == "boolean"]
    steps = [
        "let",
        f'    Source = Csv.Document(File.Contents(ExportsFolder & "\\{table}.csv"),',
        f'        [Delimiter=",", Columns={len(columns)}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        "    Typed = Table.TransformColumnTypes(Headers, {",
        "        " + pairs,
        '    }, "en-US")' + ("," if flags or table == "fct_sessions" else ""),
    ]
    last = "Typed"
    if flags:
        transforms = ",\n        ".join(
            '{"'
            + column
            + '", each if _ = "true" then true else if _ = "false" then false '
            'else error "Invalid verified CSV boolean", type logical}'
            for column in flags
        )
        steps += [
            "    Flags = Table.TransformColumns(Typed, {",
            "        " + transforms,
            "    })" + ("," if table == "fct_sessions" else ""),
        ]
        last = "Flags"
    if table == "fct_sessions":
        steps += [
            '    Labels = Table.AddColumn(Flags, "user_cohort_label", each',
            '        if [user_cohort] = "new_in_window" then "New in window"',
            '        else if [user_cohort] = "no_observed_first_visit" then "No observed first_visit"',
            "        else [user_cohort], type text)",
        ]
        last = "Labels"
    return "\n".join([*steps, "in", "    " + last])


def table_tmdl(
    table: str, columns: list[str], source: str, measures: dict[str, str]
) -> bytes:
    """Create a typed table with one import partition and explicit measure formats."""
    lines = [f"table {table}", f"\tlineageTag: {lineage(table)}"]
    if table == "dim_date":
        lines += ["\tdataCategory: Time"]
    for name, expression in measures.items():
        lines += ["", f"\tmeasure '{name}' ="]
        lines += ["\t\t\t" + line for line in expression.splitlines()]
        if name != "Product Display Name":
            fmt = (
                USD
                if "USD" in name
                else ("0.00%" if "Conversion" in name or "Fraction" in name else "#,0")
            )
            lines += [f"\t\tformatString: {fmt}"]
        folder = (
            "Products"
            if name.startswith(("Product ", "Item ", "Category "))
            else "Funnel"
            if name.startswith(("Funnel ", "Next Step "))
            else "Assumed opportunity"
            if "Any Order" in name
            or "Modeled" in name
            or "Assumed" in name
            or "Continuer" in name
            else "Sessions"
        )
        lines += [f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {lineage(name)}"]
    for column in columns:
        typ, _ = column_type(column)
        lines += ["", f"\tcolumn {column}", f"\t\tdataType: {typ}"]
        hidden = (
            table in FACTS
            and column
            not in {
                "user_cohort_label",
                "funnel_mode",
                "step_name",
                "item_id",
                "item_category",
            }
        ) or (table == "category_summary" and column != "item_category")
        if hidden:
            lines += ["\t\tisHidden"]
        if (table, column) in {
            ("dim_date", "date_day"),
            ("dim_device", "device_category"),
            ("dim_country", "country"),
        }:
            lines += ["\t\tisKey"]
        lines += [
            f"\t\tsourceColumn: {column}",
            "\t\tsummarizeBy: none",
            f"\t\tlineageTag: {lineage(table + '.' + column)}",
        ]
        if typ == "dateTime":
            lines += ["\t\tformatString: yyyy-MM-dd"]
        elif typ == "decimal":
            lines += [f"\t\tformatString: {USD}"]
        elif column == "fraction":
            lines += ["\t\tformatString: 0%"]
        elif typ == "int64":
            lines += ["\t\tformatString: #,0"]
        if column == "step_name":
            lines += ["\t\tsortByColumn: step_order"]
    lines += ["", f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t\t" + line for line in source.splitlines()]
    return ("\n".join(lines) + "\n").encode()


def field(table: str, name: str, *, measure: bool = False) -> dict[str, Any]:
    """Reference a native model object using the documented PBIR semantic query."""
    return {
        "Measure" if measure else "Column": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": name,
        }
    }


def projection(table: str, name: str, *, measure: bool = False) -> dict[str, Any]:
    """Bind a model field to a chart role without implicit fact aggregations."""
    return {
        "field": field(table, name, measure=measure),
        "queryRef": table + "." + name,
        "nativeQueryRef": name,
    }


def metric(name: str) -> dict[str, Any]:
    """Canonical and extra measures are hosted on fct_sessions."""
    return projection("fct_sessions", name, measure=True)


def literal(value: str | int | bool) -> dict[str, Any]:
    """Encode a Power BI formatting expression, including typed integer literals."""
    if isinstance(value, bool):
        content = "true" if value else "false"
    elif isinstance(value, int):
        content = str(value) + "L"
    else:
        content = "'" + value.replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": content}}}


def objects(**groups: dict[str, Any]) -> dict[str, Any]:
    """Wrap visual object properties in the PBIR formatting collection structure."""
    return {name: [{"properties": props}] for name, props in groups.items()}


def selection(table: str, column: str, value: str) -> dict[str, Any]:
    """Create a persisted slicer selection using a semantic In expression."""
    expression = {
        "Column": {
            "Expression": {"SourceRef": {"Source": "s"}},
            "Property": column,
        }
    }
    return {
        "filter": {
            "Version": 2,
            "From": [{"Name": "s", "Entity": table, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [expression],
                            "Values": [[{"Literal": {"Value": value}}]],
                        }
                    }
                }
            ],
        }
    }


def make_report() -> dict[str, bytes]:
    """Compose the four requested pages, slicers, interactions, and visible limits."""
    files: dict[str, bytes] = {}

    def put(path: str, value: dict[str, Any]) -> None:
        files[f"{REPORT}/definition/{path}"] = json_bytes(value)

    put("version.json", {"$schema": SCHEMAS["version"], "version": "2.0.0"})
    put(
        "report.json",
        {
            "$schema": SCHEMAS["report"],
            "layoutOptimization": "None",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU06",
                    "reportVersionAtImport": "5.55",
                    "type": "SharedResources",
                }
            },
            "resourcePackages": [
                {
                    "name": "SharedResources",
                    "type": "SharedResources",
                    "items": [
                        {
                            "name": "CY24SU06",
                            "path": "BaseThemes/CY24SU06.json",
                            "type": "BaseTheme",
                        }
                    ],
                }
            ],
            "settings": {"defaultDrillFilterOtherVisuals": True},
            "annotations": [
                {
                    "name": "validationStatus",
                    "value": "Desktop render and owner review pending",
                }
            ],
        },
    )
    put(
        "pages/pages.json",
        {
            "$schema": SCHEMAS["pages"],
            "pageOrder": list(PAGE_NAMES),
            "activePageName": "summary",
        },
    )
    for page, title in PAGE_NAMES.items():
        visuals: dict[str, dict[str, Any]] = {}
        interactions: list[dict[str, str]] = []

        def add(
            name: str,
            typ: str,
            title: str,
            box: tuple[int, int, int, int],
            roles: dict[str, list[dict[str, Any]]] | None = None,
            formatting: dict[str, Any] | None = None,
            sort: dict[str, Any] | None = None,
            *,
            page_visuals: dict[str, dict[str, Any]] = visuals,
        ) -> dict[str, Any]:
            x, y, w, h = box
            visual: dict[str, Any] = {
                "visualType": typ,
                "drillFilterOtherVisuals": True,
                "visualContainerObjects": objects(
                    title={
                        "show": literal(bool(title)),
                        "text": literal(title),
                        "fontSize": literal(13),
                        "titleWrap": literal(True),
                    },
                    background={
                        "show": literal(True),
                        "color": {"solid": {"color": literal("#FFFFFF")}},
                        "transparency": literal(0),
                    },
                ),
            }
            if roles:
                visual["query"] = {
                    "queryState": {
                        role: {"projections": fields} for role, fields in roles.items()
                    }
                }
                if sort:
                    visual["query"]["sortDefinition"] = {"sort": [sort]}
            if formatting:
                visual["objects"] = formatting
            obj = {
                "$schema": SCHEMAS["visual"],
                "name": name,
                "position": {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "z": len(page_visuals),
                    "tabOrder": len(page_visuals),
                },
                "visual": visual,
            }
            page_visuals[name] = obj
            return obj

        def text(
            name: str, content: str, box: tuple[int, int, int, int], size: int = 13
        ) -> None:
            paragraphs = [
                {
                    "textRuns": [
                        {
                            "value": line,
                            "textStyle": {
                                "fontFamily": "Segoe UI",
                                "fontSize": f"{size}pt",
                                "color": "#20352F",
                            },
                        }
                    ]
                }
                for line in content.splitlines()
            ]
            add(
                name,
                "textbox",
                "",
                box,
                formatting=objects(general={"paragraphs": paragraphs}),
            )

        def table(
            name: str,
            title: str,
            box: tuple[int, int, int, int],
            columns: list[dict[str, Any]],
            sort_by: dict[str, Any] | None = None,
        ) -> None:
            add(
                name,
                "tableEx",
                title,
                box,
                {"Values": columns},
                objects(
                    totals={"show": literal(False)},
                    grid={"rowPadding": literal(5)},
                    columnHeaders={"wordWrap": literal(True)},
                    values={"fontSize": literal(11)},
                ),
                sort_by,
            )

        def slicer(
            name: str,
            table_name: str,
            column: str,
            label: str,
            x: int,
            w: int,
            default: str | None = None,
            sync: bool = False,
        ) -> None:
            fmt = objects(
                data={"mode": literal("Dropdown")},
                selection={
                    "singleSelect": literal(default is not None),
                    "strictSingleSelect": literal(default is not None),
                },
            )
            if default is not None:
                fmt["general"] = [
                    {"properties": {"filter": selection(table_name, column, default)}}
                ]
            obj = add(
                name,
                "slicer",
                label,
                (x, 74, w, 84),
                {"Values": [projection(table_name, column)]},
                fmt,
            )
            if sync:
                obj["visual"]["syncGroup"] = {
                    "groupName": name,
                    "fieldChanges": True,
                    "filterChanges": True,
                }

        text("heading", "BREADCRUMB  /  " + title, (24, 10, 1512, 52), 23)
        text("footer", FOOTER, (24, 944, 1512, 36), 11)
        if page != "products":
            slicer(
                "date_filter",
                "dim_date",
                "date_day",
                "Session start date",
                24,
                310,
                sync=True,
            )
            slicer(
                "device_filter",
                "dim_device",
                "device_category",
                "Device",
                354,
                280,
                sync=True,
            )
            slicer(
                "country_filter",
                "dim_country",
                "country",
                "Country",
                654,
                540,
                sync=True,
            )
        if page in {"summary", "segments"}:
            slicer(
                "funnel_mode",
                "fct_funnel_daily",
                "funnel_mode",
                "Funnel mode",
                1214,
                322,
                "'any_order'",
                sync=True,
            )
        stats = [
            "Sessions",
            "Purchase Sessions",
            "Session Conversion",
            "Purchase Revenue USD",
        ]
        asc_step = {
            "field": field("fct_funnel_daily", "step_name"),
            "direction": "Ascending",
        }
        if page == "summary":
            for i, name in enumerate(stats):
                add(
                    "kpi_" + str(i),
                    "card",
                    name,
                    (24 + i * 384, 182, 360, 128),
                    {"Values": [metric(name)]},
                    objects(
                        labels={
                            "labelDisplayUnits": literal(1),
                            "fontSize": literal(25),
                        }
                    ),
                )
            add(
                "conversion_trend",
                "lineChart",
                "Purchase-session conversion by start date",
                (24, 334, 864, 260),
                {
                    "Category": [projection("dim_date", "date_day")],
                    "Y": [metric("Session Conversion")],
                },
                sort={"field": field("dim_date", "date_day"), "direction": "Ascending"},
            )
            table(
                "cohorts",
                "Observed first_visit cohorts",
                (912, 334, 624, 260),
                [
                    projection("fct_sessions", "user_cohort_label"),
                    *map(metric, stats[:3]),
                ],
            )
            table(
                "global_funnel",
                "Cumulative session reach · next step / current step",
                (24, 618, 864, 252),
                [
                    projection("fct_funnel_daily", "step_name"),
                    *map(
                        metric,
                        [
                            "Funnel Reached Sessions",
                            "Funnel Lost Sessions",
                            "Next Step Conversion",
                        ],
                    ),
                ],
                asc_step,
            )
            text(
                "definitions",
                "Both funnels require all preceding steps.\n"
                "Any order: timestamps may occur in any sequence.\n"
                "Strict ordered: each next timestamp must be strictly later; ties do not progress.\n"
                "Overall purchase conversion includes purchases without every funnel step.\n"
                "Cohort selection does not filter the funnel mart.",
                (912, 618, 624, 252),
            )
            interactions.append(
                {"source": "cohorts", "target": "global_funnel", "type": "NoFilter"}
            )
            # Funnel-mode slicer has no cohort/session meaning; isolate session facts explicitly.
            for target in [
                "cohorts",
                "conversion_trend",
                *["kpi_" + str(i) for i in range(4)],
            ]:
                interactions.append(
                    {"source": "funnel_mode", "target": target, "type": "NoFilter"}
                )
        elif page == "segments":
            add(
                "devices",
                "pivotTable",
                "Device performance",
                (24, 182, 736, 300),
                {
                    "Rows": [projection("dim_device", "device_category")],
                    "Values": list(map(metric, stats)),
                },
                objects(
                    subTotals={
                        "rowSubtotals": literal(False),
                        "columnSubtotals": literal(False),
                    },
                    grid={"rowPadding": literal(8)},
                ),
            )
            add(
                "countries",
                "pivotTable",
                "All countries · scroll; no Top N subtotal",
                (784, 182, 752, 420),
                {
                    "Rows": [projection("dim_country", "country")],
                    "Values": list(map(metric, stats)),
                },
                objects(
                    subTotals={
                        "rowSubtotals": literal(False),
                        "columnSubtotals": literal(False),
                    },
                    grid={"rowPadding": literal(6)},
                ),
                sort={
                    "field": field("fct_sessions", "Sessions", measure=True),
                    "direction": "Descending",
                },
            )
            add(
                "device_funnel",
                "pivotTable",
                "Cumulative funnel by device and step · one selected mode",
                (24, 506, 736, 364),
                {
                    "Rows": [projection("dim_device", "device_category")],
                    "Columns": [projection("fct_funnel_daily", "step_name")],
                    "Values": [metric("Funnel Reached Sessions")],
                },
                objects(
                    subTotals={
                        "rowSubtotals": literal(False),
                        "columnSubtotals": literal(False),
                    },
                    rowHeaders={"stepped": literal(False)},
                    grid={"rowPadding": literal(8)},
                ),
                asc_step,
            )
            text(
                "segment_notes",
                "Clicking device or country filters the other data visuals.\n"
                "Differences are descriptive; they do not establish a causal defect.\n"
                "Channel dimensions, if added, must say First-touch source / medium.\n"
                "Counts use session start date, including sessions crossing midnight.",
                (784, 626, 752, 244),
            )
            for source in ["devices", "countries"]:
                for target in ["devices", "countries", "device_funnel"]:
                    if source != target:
                        interactions.append(
                            {"source": source, "target": target, "type": "DataFilter"}
                        )
        elif page == "dropoff":
            slicer(
                "recovery_fraction",
                "recovery_assumption",
                "fraction",
                "Assumed recovery",
                1214,
                322,
                "0.05D",
            )
            add(
                "losses",
                "barChart",
                "Any-order dropouts by transition",
                (24, 182, 736, 282),
                {
                    "Category": [projection("fct_funnel_daily", "step_name")],
                    "Y": [metric("Funnel Lost Sessions")],
                },
                sort=asc_step,
            )
            add(
                "exposure",
                "barChart",
                "Modeled exposure at 100% recovery · USD",
                (784, 182, 752, 282),
                {
                    "Category": [projection("fct_funnel_daily", "step_name")],
                    "Y": [metric("Modeled Dropoff Opportunity USD")],
                },
                sort=asc_step,
            )
            table(
                "step_evidence",
                "Any-order transitions · terminal purchase has no next step",
                (24, 488, 736, 246),
                [
                    projection("fct_funnel_daily", "step_name"),
                    *map(
                        metric,
                        [
                            "Funnel Lost Sessions",
                            "Next Step Conversion",
                            "Modeled Dropoff Opportunity USD",
                        ],
                    ),
                ],
                asc_step,
            )
            for name, measure_name, x in [
                ("entry_loss", "Entry Dropouts Any Order", 784),
                ("scenario", "Modeled Recovery USD", 1168),
            ]:
                add(
                    name,
                    "card",
                    measure_name,
                    (x, 488, 368, 130),
                    {"Values": [metric(measure_name)]},
                    objects(
                        labels={
                            "labelDisplayUnits": literal(1),
                            "fontSize": literal(24),
                        }
                    ),
                )
            text(
                "recommendation",
                "Assumed incremental USD, observed window; not causal lift or profit.\n"
                "Scenario always uses any-order entry → view, with the selected segment.\n"
                "Hypothesis: make the entry-page ‘Shop products’ action clearer.\n"
                "Assumption: recovered dropouts behave like observed continuers.\n"
                "Experiment outcome: purchase-session conversion. No experiment occurred.\n"
                "Evidence and proposal: docs/memo.md and reports/opportunity.md.",
                (784, 642, 752, 232),
                12,
            )
            text("all_limits", "\n".join(LIMITS), (24, 766, 736, 164), 10)
            for target in ["losses", "exposure", "step_evidence"]:
                obj = visuals[target]
                obj["filterConfig"] = {
                    "filters": [
                        {
                            "name": "any_order_" + target,
                            "field": field("fct_funnel_daily", "funnel_mode"),
                            "type": "Categorical",
                            **selection(
                                "fct_funnel_daily", "funnel_mode", "'any_order'"
                            ),
                            "howCreated": "User",
                            "isHiddenInViewMode": True,
                            "isLockedInViewMode": True,
                        }
                    ]
                }
                # Selection of a step is not a parameter for the fixed entry scenario.
                for dest in ["entry_loss", "scenario", "recovery_fraction"]:
                    interactions.append(
                        {"source": target, "target": dest, "type": "NoFilter"}
                    )
        else:
            text(
                "window_scope",
                "2020-11-01 to 2021-01-31, all devices and countries.\n"
                "This page has no synced slicers. Item revenue is diagnostic; purchase-event revenue is canonical.",
                (24, 74, 1512, 84),
                14,
            )
            table(
                "product_performance",
                "Product key = item ID + unchanged category · revenue sorted",
                (24, 182, 1512, 360),
                [
                    projection("fct_product_daily", "item_id"),
                    projection("fct_product_daily", "item_category"),
                    *map(
                        metric,
                        [
                            "Product Display Name",
                            "Item Revenue USD",
                            "Product Viewing Sessions",
                            "Product Purchase without View Sessions",
                            "Product View to Purchase Conversion",
                        ],
                    ),
                ],
                {
                    "field": field("fct_sessions", "Item Revenue USD", measure=True),
                    "direction": "Descending",
                },
            )
            table(
                "category_performance",
                "Distinct category sessions · full window; disconnected rollup",
                (24, 566, 1512, 266),
                [
                    projection("category_summary", "item_category"),
                    *map(
                        metric,
                        [
                            "Category Item Revenue USD Full Window",
                            "Category Viewing Sessions Full Window",
                            "Category Conversion Full Window",
                        ],
                    ),
                ],
                {
                    "field": field(
                        "fct_sessions",
                        "Category Item Revenue USD Full Window",
                        measure=True,
                    ),
                    "direction": "Descending",
                },
            )
            text(
                "matching_limit",
                "No item/category groups have a matched view and purchase in this sample. "
                "Missing/mismatched keys and obfuscation limit conversion interpretation; this does not prove "
                "product pages never convert. Category matches may involve different products. "
                "Distinct product-session counts cannot be summed across groups.",
                (24, 846, 1512, 88),
                12,
            )
            interactions += [
                {
                    "source": "product_performance",
                    "target": "category_performance",
                    "type": "NoFilter",
                },
                {
                    "source": "category_performance",
                    "target": "product_performance",
                    "type": "NoFilter",
                },
            ]
        page_obj = {
            "$schema": SCHEMAS["page"],
            "name": page,
            "displayName": title,
            "displayOption": "FitToPage",
            "height": 984,
            "width": 1560,
            "visualInteractions": interactions,
            "objects": objects(
                background={
                    "color": {"solid": {"color": literal("#F3F6F4")}},
                    "transparency": literal(0),
                }
            ),
        }
        put(f"pages/{page}/page.json", page_obj)
        for name, obj in visuals.items():
            put(f"pages/{page}/visuals/{name}/visual.json", obj)
    return files


def validation_query(metrics: dict[str, Any]) -> bytes:
    """Prepare owner-executable DAX checks against saved measurements, not new data."""
    checks: list[str] = []

    def add(label: str, expected: str | int, actual: str, tolerance: str = "0") -> None:
        escaped = label.replace('"', '""')
        checks.append(
            f'    ROW("Check", "{escaped}", "Expected", {expected}, '
            f'"Actual", {actual}, "Tolerance", {tolerance})'
        )

    analysis = metrics["analysis"]
    profile = metrics["profiling_summary"]
    add("analysis.all_sessions", analysis["all_sessions"], "[Sessions]")
    add(
        "analysis.purchase_sessions",
        analysis["purchase_sessions"],
        "[Purchase Sessions]",
    )
    add(
        "profiling_summary.purchase_revenue_usd",
        profile["purchase_revenue_usd"],
        "[Purchase Revenue USD]",
        "0.005",
    )
    add(
        "profiling_summary.purchase_events",
        profile["purchase_events"],
        "[Purchase Events]",
    )
    add(
        "profiling_summary.purchase_item_revenue_usd",
        profile["purchase_item_revenue_usd"],
        "[Item Revenue USD]",
        "0.005",
    )
    for mode in ["any_order", "strict_ordered"]:
        for step in analysis["global_funnel"]:
            order = step["step_order"]
            add(
                f"analysis.global_funnel {mode} {step['step_name']}",
                step[mode + "_sessions"],
                f'CALCULATE([Funnel Reached Sessions], fct_funnel_daily[funnel_mode] = "{mode}", '
                f"fct_funnel_daily[step_order] = {order})",
            )
    for transition in analysis["dropoff_opportunities"]:
        order = next(
            s["step_order"]
            for s in analysis["global_funnel"]
            if s["step_name"] == transition["from_step"]
        )
        exact = transition["all_dropouts_recovered_potential_usd_exact"]
        context = f'fct_funnel_daily[funnel_mode] = "any_order", fct_funnel_daily[step_order] = {order}'
        add(
            f"analysis.dropoff_opportunities {transition['from_step']} losses",
            transition["lost_sessions"],
            f"CALCULATE([Funnel Lost Sessions], {context})",
        )
        add(
            f"analysis.dropoff_opportunities {transition['from_step']} exposure",
            f"DIVIDE({exact['numerator']}, {exact['denominator']})",
            f"CALCULATE([Modeled Dropoff Opportunity USD], {context})",
            "0.005",
        )
    for scenario in analysis["recovery_scenarios"]:
        fraction = scenario["recovery_fraction_assumption"]
        add(
            f"analysis.recovery_scenarios {fraction}",
            scenario["incremental_revenue_usd_scenario_floor_cents"],
            f"CALCULATE([Modeled Recovery USD], recovery_assumption[fraction] = {fraction})",
            "0.005",
        )
    for kind, dimension, column in [
        ("by_device", "dim_device", "device_category"),
        ("by_country", "dim_country", "country"),
    ]:
        for segment in analysis[kind]:
            member = segment[column].replace('"', '""')
            context = f'{dimension}[{column}] = "{member}"'
            for measure, key in [
                ("Sessions", "all_sessions"),
                ("Purchase Sessions", "purchase_sessions"),
                ("Purchase Revenue USD", "purchase_revenue_usd"),
            ]:
                add(
                    f"analysis.{kind} {member} {key}",
                    segment[key],
                    f"CALCULATE([{measure}], {context})",
                    "0.005" if measure.endswith("USD") else "0",
                )
    for cohort in analysis["user_cohorts"]:
        context = f'fct_sessions[user_cohort] = "{cohort["cohort"]}"'
        add(
            "analysis.user_cohorts " + cohort["cohort"],
            cohort["sessions"],
            f"CALCULATE([Sessions], {context})",
        )
        add(
            "analysis.user_cohorts purchase " + cohort["cohort"],
            cohort["purchase_sessions"],
            f"CALCULATE([Purchase Sessions], {context})",
        )
    apparel = next(
        row
        for row in metrics["readonly_category_summary"]["rows"]
        if row["item_category"] == "Apparel"
    )
    for measure, key in [
        ("Category Viewing Sessions Full Window", "viewing_sessions"),
        ("Category Item Revenue USD Full Window", "purchase_item_revenue_usd"),
    ]:
        add(
            "readonly_category_summary.rows Apparel " + key,
            apparel[key],
            f'CALCULATE([{measure}], category_summary[item_category] = "Apparel")',
            "0.005" if "USD" in measure else "0",
        )
        add(
            "Disconnected category ignores United States " + key,
            apparel[key],
            f'CALCULATE([{measure}], category_summary[item_category] = "Apparel", dim_country[country] = "United States")',
            "0.005" if "USD" in measure else "0",
        )
    text = (
        "// OWNER VALIDATION PENDING: run after local CSV refresh in Desktop DAX query view.\n"
        "// Expected values come only from saved reports/metrics.json source keys.\n"
        "// Queries ignore page slicers. All numeric checks should return Passed = TRUE.\n"
        "EVALUATE\nVAR Checks = UNION(\n" + ",\n".join(checks) + "\n)\n"
        'RETURN ADDCOLUMNS(Checks, "Passed", NOT ISBLANK([Actual]) && ABS([Expected] - [Actual]) <= [Tolerance])\n'
        "ORDER BY [Check]\n\n"
        "// Blank-context guards: all columns below should return TRUE.\n"
        "EVALUATE\nROW(\n"
        '    "Multiple modes are blank", ISBLANK([Funnel Reached Sessions]),\n'
        '    "No assumption is blank", ISBLANK([Modeled Recovery USD]),\n'
        '    "Product reach total is blank", ISBLANK([Product Viewing Sessions]),\n'
        '    "Category reach total is blank", ISBLANK([Category Viewing Sessions Full Window]),\n'
        '    "Terminal loss is blank", ISBLANK(CALCULATE([Funnel Lost Sessions], '
        'fct_funnel_daily[funnel_mode] = "any_order", fct_funnel_daily[step_order] = 5)),\n'
        '    "Empty date context is blank", ISBLANK(CALCULATE([Session Conversion], FILTER(ALL(dim_date), FALSE())))\n'
        ")\n"
    )
    return text.encode()


def build_files(metrics: dict[str, Any], powerbi: Path = POWERBI) -> dict[str, bytes]:
    """Return source artifacts only; data/cache files never enter the generated project."""
    measures = {}
    for filename in ["measures.dax", "prototype_measures.dax"]:
        measures.update(parse_measures((powerbi / filename).read_text()))
    files = make_report()
    files[f"{MODEL}/DAXQueries/Validate verified exports.dax"] = validation_query(
        metrics
    )
    files["Breadcrumb.pbip"] = json_bytes(
        {
            "$schema": SCHEMAS["pbip"],
            "version": "1.0",
            "artifacts": [{"report": {"path": REPORT}}],
            "settings": {"enableAutoRecovery": True},
        }
    )
    files[f"{REPORT}/definition.pbir"] = json_bytes(
        {
            "$schema": SCHEMAS["pbir"],
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../" + MODEL}},
        }
    )
    files[f"{MODEL}/definition.pbism"] = json_bytes(
        {
            "$schema": SCHEMAS["pbism"],
            "version": "4.0",
            "settings": {"qnaEnabled": False},
        }
    )
    prefix = f"{MODEL}/definition/"
    files[prefix + "database.tmdl"] = b"database\n\tcompatibilityLevel: 1604\n"
    files[prefix + "expressions.tmdl"] = (
        'expression ExportsFolder = "' + WINDOWS_EXPORTS + '" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        "\tlineageTag: " + lineage("ExportsFolder") + "\n"
    ).encode()
    table_names = [*CSV_TABLES, "dim_device", "dim_country", "recovery_assumption"]
    model_lines = [
        "model Model",
        "\tculture: en-US",
        "\tsourceQueryCulture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "annotation PBI_QueryOrder = " + json.dumps(["ExportsFolder", *table_names]),
        "",
    ]
    model_lines += ["ref table " + name for name in table_names]
    model_lines += ["", "ref expression ExportsFolder", ""]
    files[prefix + "model.tmdl"] = "\n".join(model_lines).encode()
    for table in CSV_TABLES:
        columns = metrics["bi_exports"][table]["columns"]
        source = m_csv_source(table, columns)
        if table == "fct_sessions":
            columns = [*columns, "user_cohort_label"]
        files[prefix + f"tables/{table}.tmdl"] = table_tmdl(
            table, columns, source, measures if table == "fct_sessions" else {}
        )
    for table, column in [
        ("dim_device", "device_category"),
        ("dim_country", "country"),
    ]:
        source = (
            f'let\n    Source = Table.SelectColumns(fct_sessions, {{"{column}"}}),\n'
        )
        source += "    Unique = Table.Distinct(Source)\nin\n    Unique"
        files[prefix + f"tables/{table}.tmdl"] = table_tmdl(table, [column], source, {})
    files[prefix + "tables/recovery_assumption.tmdl"] = table_tmdl(
        "recovery_assumption",
        ["fraction"],
        "#table(type table [fraction = number], {{0.05}, {0.10}, {0.20}})",
        {},
    )
    relations = []
    for fact in FACTS:
        for dimension, key, fact_key in [
            ("dim_date", "date_day", "session_start_date"),
            ("dim_device", "device_category", "device_category"),
            ("dim_country", "country", "country"),
        ]:
            relations += [
                f"relationship {fact}_{dimension}",
                f"\tfromColumn: {fact}.{fact_key}",
                f"\ttoColumn: {dimension}.{key}",
                "\tfromCardinality: many",
                "\ttoCardinality: one",
                "\tcrossFilteringBehavior: oneDirection",
                "\tisActive: true",
                "",
            ]
    files[prefix + "relationships.tmdl"] = "\n".join(relations).encode()
    return files


def publish(files: dict[str, bytes], powerbi: Path = POWERBI) -> None:
    """Publish idempotently; reject edits to existing generated or owner artifacts."""
    manifest_path = powerbi / "project_manifest.json"
    old = _read_json(manifest_path).get("files", {}) if manifest_path.exists() else {}
    for name, content in files.items():
        target = powerbi / name
        if target.exists() and target.read_bytes() != content:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if old.get(name) != digest:
                raise ValueError(
                    f"Owner-modified or unmanaged file requires review: {target}"
                )
    stale = set(old) - set(files)
    if stale:
        raise ValueError(
            f"Removing generated files requires owner review: {sorted(stale)}"
        )
    for name, content in files.items():
        target = powerbi / name
        if target.exists() and target.read_bytes() == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {
        "scope": "Human Step #6 prototype; Desktop validation pending",
        "files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(files.items())
        },
    }
    content = json_bytes(manifest)
    if not manifest_path.exists() or manifest_path.read_bytes() != content:
        manifest_path.write_bytes(content)
    LOGGER.info("Prepared %d source files under %s", len(files), powerbi)


def main() -> None:
    """Build from verified local inputs, or check that the generated project is current."""
    from analysis.powerbi_validate import verify_csv_inputs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check reproducibility without writes"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    metrics = _read_json(ROOT / "reports/metrics.json")
    verify_csv_inputs(ROOT, metrics)
    files = build_files(metrics)
    if args.check:
        for name, content in files.items():
            if (POWERBI / name).read_bytes() != content:
                raise ValueError(f"Generated file differs: {name}")
        LOGGER.info("Reproducible project: %d files", len(files))
    else:
        publish(files)


if __name__ == "__main__":
    main()
