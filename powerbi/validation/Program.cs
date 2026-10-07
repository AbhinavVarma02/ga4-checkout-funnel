using Microsoft.AnalysisServices.Tabular;
using System.Text.Json;
using System.Security.Cryptography;
using System.Text;

// Parse metadata offline. This does not connect, process CSVs, or execute DAX/M.
if (args.Length != 1) throw new ArgumentException("Pass the semantic model definition folder.");
var definitionPath = Path.GetFullPath(args[0]);
var database = TmdlSerializer.DeserializeDatabaseFromFolder(definitionPath);
var model = database.Model ?? throw new InvalidDataException("Missing model.");
if (model.Tables.Count != 8) throw new InvalidDataException("Expected eight tables.");
if (model.Relationships.Count != 9) throw new InvalidDataException("Expected nine relationships.");
var expectedRelationships = new HashSet<string>();
foreach (var fact in new [] { "fct_sessions", "fct_funnel_daily", "fct_product_daily" })
{
    expectedRelationships.Add($"{fact}.session_start_date->dim_date.date_day");
    expectedRelationships.Add($"{fact}.device_category->dim_device.device_category");
    expectedRelationships.Add($"{fact}.country->dim_country.country");
}
foreach (var relationship in model.Relationships.Cast<SingleColumnRelationship>())
{
    if (!relationship.IsActive || relationship.CrossFilteringBehavior != CrossFilteringBehavior.OneDirection
        || relationship.FromCardinality != RelationshipEndCardinality.Many
        || relationship.ToCardinality != RelationshipEndCardinality.One)
        throw new InvalidDataException($"Invalid relationship: {relationship.Name}");
    if (relationship.FromTable.Name == "category_summary" || relationship.ToTable.Name == "category_summary")
        throw new InvalidDataException("Category summary must remain disconnected.");
    if (!expectedRelationships.Remove($"{relationship.FromTable.Name}.{relationship.FromColumn.Name}->"
        + $"{relationship.ToTable.Name}.{relationship.ToColumn.Name}"))
        throw new InvalidDataException("Unexpected relationship endpoints.");
}
if (expectedRelationships.Count != 0) throw new InvalidDataException("Missing dimension relationships.");
if (model.Tables["dim_date"].DataCategory != "Time" || !model.Tables["dim_date"].Columns["date_day"].IsKey)
    throw new InvalidDataException("Missing date-table designation.");
if (model.Tables["fct_funnel_daily"].Columns["step_name"].SortByColumn.Name != "step_order")
    throw new InvalidDataException("Funnel step sort order is missing.");
foreach (var table in model.Tables)
{
    if (table.Partitions.Count != 1 || table.Partitions[0].Mode != ModeType.Import
        || table.Partitions[0].Source is not MPartitionSource)
        throw new InvalidDataException($"Expected one M Import partition: {table.Name}");
    foreach (var column in table.Columns)
    {
        if (column.Name.StartsWith("has_") || column.Name.StartsWith("ordered_"))
            if (column.DataType != DataType.Boolean) throw new InvalidDataException("Flags must be Boolean.");
        if (column.Name.EndsWith("_usd") || column.Name.Contains("revenue_usd_"))
            if (column.DataType != DataType.Decimal) throw new InvalidDataException("Money must be fixed decimal.");
    }
}
// Exercise both directions of Microsoft's serializer and compare the metadata.
var roundtripPath = Path.Combine(Path.GetTempPath(), "breadcrumb-tmdl-roundtrip-" + Guid.NewGuid().ToString("N"));
TmdlSerializer.SerializeDatabaseToFolder(database, roundtripPath);
var roundtrip = TmdlSerializer.DeserializeDatabaseFromFolder(roundtripPath);
if (roundtrip.Model.Tables.Count != model.Tables.Count
    || roundtrip.Model.Relationships.Count != model.Relationships.Count)
    throw new InvalidDataException("TMDL round trip changed the model.");
using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
foreach (var path in Directory.GetFiles(definitionPath, "*.tmdl", SearchOption.AllDirectories)
    .OrderBy(p => Path.GetRelativePath(definitionPath, p).Replace('\\', '/'), StringComparer.Ordinal))
{
    hash.AppendData(Encoding.UTF8.GetBytes(Path.GetRelativePath(definitionPath, path).Replace('\\', '/') + "\0"));
    hash.AppendData(File.ReadAllBytes(path));
    hash.AppendData(new byte[] { 0 });
}
Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new {
    status = "passed",
    parser = "Microsoft.AnalysisServices 19.117.0",
    assemblyVersion = typeof(TmdlSerializer).Assembly.GetName().Version?.ToString(),
    runtimeVersion = Environment.Version.ToString(),
    compatibilityLevel = database.CompatibilityLevel,
    tables = model.Tables.Count,
    columns = model.Tables.Sum(t => t.Columns.Count),
    measures = model.Tables.Sum(t => t.Measures.Count),
    relationships = model.Relationships.Count,
    importPartitions = model.Tables.Sum(t => t.Partitions.Count),
    roundtrip = "passed",
    tmdl_definition_sha256 = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant(),
    limitations = "Offline metadata only; no Power BI Desktop render or DAX/M execution."
}));
