# Human Step #6 Power BI prototype validation

Historical scope: source-controlled Power BI preparation. This checkpoint was
superseded by the repository-backed PBIX/four screenshots and owner Desktop
DAX/model/filter/interaction validation; **P4.2 is complete**. Walkthrough:
**Removed by owner / Not required.** Exact Desktop version/build
**2.158.1177.0 64-bit** is now owner-supplied and recorded under completed P6.2.
The table below retains the observed preparation evidence. No cloud queries, connections, resources, billing, loads, backfills,
pipeline executions, push, or release were performed.

Observed evidence is saved under `powerbi_project_validation` in
`reports/metrics.json`. Earlier metrics and the five original verified CSV hashes
remain unchanged. Input provenance is `bi_exports`; count/revenue/funnel/scenario
comparisons use `analysis` and `profiling_summary`; categories are independently
checked against `readonly_category_summary.rows`.

| Local check | Observed result | Evidence |
| --- | --- | --- |
| Microsoft PBIP/PBIR/PBISM JSON schemas | 53 documents pass against 14 vendored schemas, resolving offline | `powerbi_project_validation.json_documents`, `microsoft_json_schemas` |
| Visual/model references and page structure | 43 visuals; model field references resolve; four requested pages, slicer groups, isolation interactions, and canvas bounds pass | `visuals`, `model_field_references`, `slicers_interactions_bounds` |
| Native Microsoft TMDL parser | Eight tables, 68 columns, 29 measures, nine relationships, eight M Import partitions; deserialize/serialize/deserialize passes | `native_tmdl`; definition SHA binds the result to actual files |
| Canonical measures | All 26 expressions are preserved exactly; three supplemental exposure/name measures are separate | `canonical_dax_preserved`; unchanged `powerbi/measures.dax` |
| Reproducibility | 66 generated source files match the deterministic builder | `reproducible_source_files`; `powerbi/project_manifest.json` |
| Verified CSV integrity and reconciliation | All five exact hashes, headers, rows, types, fixed-decimal precision, dimension coverage, global/segment/cohort totals, funnels, opportunities, scenarios, and category rows pass | `csv_inputs` |
| Negative/regression checks | All 105 Python tests pass, including 13 Power BI checks for schema/reference/DAX corruption, missing grain isolation, malformed slicer defaults, invalid CSV flags, missing/changed files, idempotence, and owner-edit protection | `python_tests`; ignored JUnit/log paths recorded there |
| Python lint/format | Both pass | `python_lint` |

Native validation used Microsoft.AnalysisServices 19.117.0, a locked NuGet graph,
and a temporary Microsoft .NET 8.0.425 SDK verified against Microsoft's download
SHA-512. It loaded only local metadata and wrote a retained temporary round-trip
folder. No Desktop/Analysis Services engine connection was opened. The committed
C# checker can run with .NET 8; the SDK download itself is not committed.

The first Python CSV verification stopped after two CSVs with an `unknown opcode`
SystemError and native exit 139 before publishing project files. A run with the
previously documented `PYTHONMALLOC=malloc` workaround completed; subsequent
checks use that setting. The cause remains unconfirmed. No export, dependency
version, or business definition was replaced to hide the failure.

Schema and TMDL validity cannot establish that Power BI Desktop will execute DAX
or M, render charts, apply formatting/default selections, or synchronize filters
as intended. The prepared DAX query has **not** run in Desktop. The owner subsequently confirmed model/DAX/filter/interaction review and all
four pages; saved PBIX/screenshots are independently verified. Specific DAX
query logs remain unclaimed. Walkthrough: Removed by owner / Not required.
Exact Desktop version/build **2.158.1177.0 64-bit** is owner-supplied and recorded in
docs/versions.md, completing P6.2. Current evidence and reopening instructions are in
docs/runbook.md and docs/powerbi_build_guide.md.

## Monetary presentation

The saved drop-off page differs slightly from canonical exact-rational calculations.
Written results use metrics.json and the memo; the screenshot is preserved.

| Transition / scenario | Screenshot USD | Saved reference USD |
|---|---:|---:|
| session_start → view_item | 1,274,940.12 | 1,274,927.91 |
| view_item → add_to_cart | 818,079.77 | 818,082.49 |
| add_to_cart → begin_checkout | 310,595.79 | 310,595.75 |
| begin_checkout → purchase | 218,774.99 | 218,775.08 |
| Assumed 5% entry recovery | 63,747.00 | 63,746.39 |

The first four saved references use the exact fractions in
`analysis.dropoff_opportunities[0..3].all_dropouts_recovered_potential_usd_exact`,
rounded to cents for comparison. The last is the canonical floored
`analysis.recovery_scenarios[0].incremental_revenue_usd_scenario_floor_cents`.
Rounding continuer revenue per session to four decimals reproduces the displayed
values, but a Desktop engine cause is not established. This comparison records
artifact precision limits without changing the canonical results or report files.
