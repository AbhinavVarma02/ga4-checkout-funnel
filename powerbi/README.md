# Breadcrumb Power BI project prototype

Open [Breadcrumb.pbip](Breadcrumb.pbip) in Windows Power BI Desktop, then refresh
the existing local CSVs. The report pages, semantic model, relationships, Power
Query imports, and measures are already prepared. The saved PBIX and four screenshots are repository-backed; Desktop rendering,
model/DAX/filter behavior and interactions were reviewed against verified CSVs.

Windows reopening/refresh steps are in [the build guide](../docs/powerbi_build_guide.md);
[validation and display limits](../reports/powerbi_validation.md) distinguish
archive/schema checks from Desktop review.

| Source artifact | Purpose |
| --- | --- |
| `Breadcrumb.pbip` | Desktop project entry point |
| `Breadcrumb.Report/definition.pbir` | Relative local semantic-model reference |
| `Breadcrumb.Report/definition/` | Four PBIR pages and bound visuals |
| `Breadcrumb.SemanticModel/definition/` | TMDL model, eight Import tables, nine relationships |
| `measures.dax` | Unchanged canonical metric definitions; 26 measures |
| `prototype_measures.dax` | Three supplementary measures for modeled exposure and descriptive product name |
| `Breadcrumb.SemanticModel/DAXQueries/Validate verified exports.dax` | Owner-run numerical and blank-context acceptance checks |
| `project_manifest.json` | Generated source hashes and owner-edit protection |
| `validation/` | Microsoft schema bundle and a pinned native TMDL validator |

Five CSV partitions load **only** the verified files named in `bi_exports` in
`reports/metrics.json`. The `ExportsFolder` M parameter defaults to
`\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\exports`.
Two dimension queries reference session facts and retain distinct blank members;
the disconnected recovery table contains the explicitly assumed 5%, 10%, and 20%.
IDs/labels stay text, flags require literal `true`/`false`, dates use start date,
and money uses fixed decimal. Category labels are unchanged. No raw events,
incomplete `.bi_*.csv`, cloud connection, or embedded business-data cache is included.

Pages are **Summary**, **Funnel by device and country**, **Drop-off revenue by
step**, and **Product and category performance**. Dimension slicers synchronize
among the first three pages. The product page deliberately has no shared slicers;
its category rollup remains disconnected and full-window. Funnel mode is shared
only between the first two pages. The opportunity page fixes any-order transitions,
and its recovery scenario always uses entry-to-view. Tables hide totals where
distinct-session counts overlap; cohort selection is isolated from the funnel.

The supplementary modeled-exposure measure is exactly losses × next-step
continuers' purchase-event revenue ÷ next-step continuing sessions, matching
`analysis.dropoff_opportunities`. It is a 100% recovery exposure assumption, not
measured lost revenue. The canonical scenario still floors amounts to cents.
The product display-name measure selects one lexical label at the item/category
grain; it does not split or merge product keys. These decisions are documented in [metric definitions](../docs/metric_definitions.md)
and [Power BI validation](../reports/powerbi_validation.md).

From the WSL repository root:

```bash
make powerbi-check          # source schemas/references/reproducibility; no CSV needed
make powerbi-check-csv      # also require/reconcile all five verified local CSVs
make powerbi-build          # deterministic generation; rejects owner-modified files
PYTHONMALLOC=malloc UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked pytest tests/test_powerbi_project.py -q
```

These use Python 3.12 and the repository's pinned uv environment. `PYTHONMALLOC=malloc`
is the recorded workaround for an observed allocator/interpreter failure during
CSV verification; the cause is unconfirmed. Generated files are unchanged on an
idempotent run. After editing/saving in Desktop, keep those edits and inspect
`git diff`; do not replace them with regeneration. The generator refuses to
overwrite changed/unmanaged generated files or delete stale ones.

If .NET 8 SDK is available, independently validate TMDL without connecting to a
Power BI engine:

```bash
dotnet restore powerbi/validation/TmdlCheck.csproj --locked-mode
dotnet run --no-restore --project powerbi/validation/TmdlCheck.csproj -- \
  powerbi/Breadcrumb.SemanticModel/definition
```

The native checker uses Microsoft's `Microsoft.AnalysisServices` **19.117.0**
with committed NuGet dependency hashes. It parses and round-trips the complete
model, checks dimension relationships, Import partitions, date designation,
funnel sorting, and flag/money types. It writes a temporary round-trip folder,
retained under the OS temporary directory. It does not refresh CSVs, run DAX/M,
open Desktop, or render visuals. Desktop caches and validator build outputs are
ignored. Actual local results are saved under `powerbi_project_validation` in
`reports/metrics.json` and described in [the validation record](../reports/powerbi_validation.md).

The JSON definitions use documented [PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview),
[PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report),
and [TMDL](https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview)
formats. The pinned schema bundle includes all 14 transitive schemas fetched
from each Microsoft `$id` URL on 2026-10-04. Their source is
[microsoft/json-schemas](https://github.com/microsoft/json-schemas/tree/8db0a644e856e3941ebc127618d095a8ef7a7727),
with the MIT license retained at `validation/schemas/LICENSE`. The bundled bytes
and checksum are authoritative for offline checks. Chart role patterns were
cross-checked against Microsoft's
[Revenue Opportunities sample](https://github.com/microsoft/powerbi-desktop-samples/blob/main/2026%20Power%20BI%20Samples%20Revamp/Revenue%20Opportunities.pbix);
Slicer filter-value wrappers were also checked against Microsoft's
[April 2018 Desktop sample](https://github.com/microsoft/powerbi-desktop-samples/blob/main/Monthly%20Desktop%20Blog%20Samples/2018/2018SU04%20Blog%20Demo%20-%20April.pbix).
No sample data or report definitions are copied here. Because formatting objects
permit arbitrary values in the JSON schemas, persisted single-select defaults
receive an additional structural check.

Structural validation proves schema/reference and TMDL validity, rather than
DAX/M execution or visual behavior. The subsequent Desktop review, saved PBIX and
four screenshots provide that separate evidence. Source imports need complete
local CSVs; the PBIX contains its imported model. Monetary screenshot precision
differences remain [disclosed](../reports/powerbi_validation.md#monetary-presentation).
