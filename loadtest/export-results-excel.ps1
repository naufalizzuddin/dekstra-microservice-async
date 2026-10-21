param(
    [string]$ResultsRoot = (Join-Path $PSScriptRoot "results"),
    [string]$OutputPath,
    [string]$Architecture = "",
    [switch]$SkipRawLocust
)

$ErrorActionPreference = "Stop"
$culture = [System.Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path $ResultsRoot)) {
    throw "Results directory was not found: $ResultsRoot"
}

$resultsPath = (Resolve-Path $ResultsRoot).Path
if (-not $OutputPath) {
    $leaf = Split-Path -Leaf $resultsPath
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        $leaf = "loadtest-results"
    }
    $OutputPath = Join-Path $resultsPath ("{0}.xlsx" -f $leaf)
}

function ConvertTo-SafeXmlText([object]$Value) {
    if ($null -eq $Value) {
        return ""
    }
    $text = [string]$Value
    $text = [regex]::Replace(
        $text,
        "[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD]",
        ""
    )
    return [System.Security.SecurityElement]::Escape($text)
}

function ConvertTo-SheetName([string]$Name, [hashtable]$Seen) {
    $safe = [regex]::Replace($Name, "[\\/\?\*\[\]:]", "_")
    if ([string]::IsNullOrWhiteSpace($safe)) {
        $safe = "Sheet"
    }
    if ($safe.Length -gt 31) {
        $safe = $safe.Substring(0, 31)
    }
    $base = $safe
    $index = 2
    while ($Seen.ContainsKey($safe.ToLowerInvariant())) {
        $suffix = "_$index"
        $maxLength = 31 - $suffix.Length
        $safe = $base
        if ($safe.Length -gt $maxLength) {
            $safe = $safe.Substring(0, $maxLength)
        }
        $safe = "$safe$suffix"
        $index += 1
    }
    $Seen[$safe.ToLowerInvariant()] = $true
    return $safe
}

function ConvertTo-ExcelColumnName([int]$ColumnNumber) {
    $name = ""
    while ($ColumnNumber -gt 0) {
        $ColumnNumber -= 1
        $name = [char](65 + ($ColumnNumber % 26)) + $name
        $ColumnNumber = [math]::Floor($ColumnNumber / 26)
    }
    return $name
}

function ConvertTo-RelativePath([string]$Path, [string]$Root) {
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathFull.Substring($rootFull.Length).TrimStart(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    }
    return $pathFull
}

function ConvertTo-CellValue([object]$Value) {
    if ($null -eq $Value) {
        return ""
    }
    if ($Value -is [System.ValueType] -or $Value -is [string]) {
        return $Value
    }
    return ($Value | ConvertTo-Json -Compress -Depth 20)
}

function Test-NumericCell([object]$Value) {
    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [byte] -or
        $Value -is [int16] -or
        $Value -is [int32] -or
        $Value -is [int64] -or
        $Value -is [single] -or
        $Value -is [double] -or
        $Value -is [decimal]) {
        return $true
    }
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $false
    }
    if ($text -match "^0\d+$") {
        return $false
    }
    $number = 0.0
    return [double]::TryParse(
        $text,
        [System.Globalization.NumberStyles]::Float,
        $culture,
        [ref]$number
    )
}

function ConvertTo-NumberText([object]$Value) {
    if ($Value -is [decimal]) {
        return $Value.ToString($culture)
    }
    if ($Value -is [double] -or $Value -is [single]) {
        return ([double]$Value).ToString("G17", $culture)
    }
    if ($Value -is [byte] -or
        $Value -is [int16] -or
        $Value -is [int32] -or
        $Value -is [int64]) {
        return ([int64]$Value).ToString($culture)
    }
    return ([double]::Parse([string]$Value, $culture)).ToString("G17", $culture)
}

function Get-ObjectColumns([object[]]$Rows) {
    $columns = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($row in $Rows) {
        foreach ($property in $row.PSObject.Properties) {
            if (-not $seen.ContainsKey($property.Name)) {
                $seen[$property.Name] = $true
                $columns.Add($property.Name)
            }
        }
    }
    return $columns.ToArray()
}

function New-Row([hashtable]$Base, [object]$Data) {
    $ordered = [ordered]@{}
    foreach ($key in $Base.Keys) {
        $ordered[$key] = $Base[$key]
    }
    foreach ($property in $Data.PSObject.Properties) {
        if (-not $ordered.Contains($property.Name)) {
            $ordered[$property.Name] = ConvertTo-CellValue $property.Value
        }
    }
    return [pscustomobject]$ordered
}

function Get-RunContext([System.IO.FileInfo]$File) {
    $runDirectory = $File.Directory.FullName
    $summaryPath = Join-Path $runDirectory "summary.json"
    $metadataPath = Join-Path $runDirectory "metadata.json"
    $data = $null
    if (Test-Path $summaryPath) {
        $data = Get-Content $summaryPath -Raw | ConvertFrom-Json
    }
    elseif (Test-Path $metadataPath) {
        $data = Get-Content $metadataPath -Raw | ConvertFrom-Json
    }

    $arch = $Architecture
    if ([string]::IsNullOrWhiteSpace($arch) -and $null -ne $data) {
        $arch = [string]$data.architecture
    }
    if ([string]::IsNullOrWhiteSpace($arch)) {
        $arch = "unknown"
    }

    return [ordered]@{
        architecture = $arch
        source_run = ConvertTo-RelativePath $runDirectory $resultsPath
        source_file = ConvertTo-RelativePath $File.FullName $resultsPath
    }
}

function Import-JsonObjectRows([string]$FileName) {
    $rows = @()
    foreach ($file in Get-ChildItem $resultsPath -Recurse -Filter $FileName) {
        $data = Get-Content $file.FullName -Raw | ConvertFrom-Json
        $rows += New-Row (Get-RunContext $file) $data
    }
    return $rows
}

function Import-CsvRowsByName([string]$FileName) {
    $rows = @()
    foreach ($file in Get-ChildItem $resultsPath -Recurse -Filter $FileName) {
        foreach ($row in Import-Csv $file.FullName) {
            $rows += New-Row (Get-RunContext $file) $row
        }
    }
    return $rows
}

function Import-PrometheusMetricRows {
    $rows = @()
    foreach ($file in Get-ChildItem $resultsPath -Recurse -Filter "prometheus-metrics.json") {
        $metrics = Get-Content $file.FullName -Raw | ConvertFrom-Json
        if ($null -eq $metrics.series) {
            continue
        }
        $context = Get-RunContext $file
        foreach ($metricProperty in $metrics.series.PSObject.Properties) {
            foreach ($series in @($metricProperty.Value)) {
                $labels = ""
                if ($null -ne $series.metric) {
                    $labels = $series.metric | ConvertTo-Json -Compress -Depth 10
                }
                foreach ($point in @($series.values)) {
                    if ($null -eq $point -or $point.Count -lt 2) {
                        continue
                    }
                    $timestamp = [double]::Parse([string]$point[0], $culture)
                    $rows += [pscustomobject][ordered]@{
                        architecture = $context.architecture
                        source_run = $context.source_run
                        source_file = $context.source_file
                        metric = $metricProperty.Name
                        labels = $labels
                        timestamp_epoch = $timestamp
                        timestamp_utc = [DateTimeOffset]::FromUnixTimeSeconds(
                            [long][math]::Floor($timestamp)
                        ).ToString("o")
                        value = $point[1]
                    }
                }
            }
        }
    }
    return $rows
}

function Write-WorksheetXml(
    [string]$Path,
    [string]$SheetName,
    [object[]]$Rows
) {
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Encoding = New-Object System.Text.UTF8Encoding($false)
    $settings.Indent = $false
    $writer = [System.Xml.XmlWriter]::Create($Path, $settings)
    try {
        $columns = Get-ObjectColumns $Rows
        if ($columns.Count -eq 0) {
            $columns = @("message")
            $Rows = @([pscustomobject]@{ message = "No rows found." })
        }
        $lastColumn = ConvertTo-ExcelColumnName $columns.Count
        $lastRow = [math]::Max(1, $Rows.Count + 1)
        $dimension = "A1:{0}{1}" -f $lastColumn, $lastRow

        $writer.WriteStartDocument($true)
        $writer.WriteStartElement("worksheet", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
        $writer.WriteAttributeString("xmlns", "r", $null, "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
        $writer.WriteStartElement("dimension")
        $writer.WriteAttributeString("ref", $dimension)
        $writer.WriteEndElement()
        $writer.WriteStartElement("sheetViews")
        $writer.WriteStartElement("sheetView")
        $writer.WriteAttributeString("workbookViewId", "0")
        $writer.WriteStartElement("pane")
        $writer.WriteAttributeString("ySplit", "1")
        $writer.WriteAttributeString("topLeftCell", "A2")
        $writer.WriteAttributeString("activePane", "bottomLeft")
        $writer.WriteAttributeString("state", "frozen")
        $writer.WriteEndElement()
        $writer.WriteEndElement()
        $writer.WriteEndElement()

        $writer.WriteStartElement("cols")
        for ($columnIndex = 1; $columnIndex -le $columns.Count; $columnIndex++) {
            $writer.WriteStartElement("col")
            $writer.WriteAttributeString("min", [string]$columnIndex)
            $writer.WriteAttributeString("max", [string]$columnIndex)
            $writer.WriteAttributeString("width", "18")
            $writer.WriteAttributeString("customWidth", "1")
            $writer.WriteEndElement()
        }
        $writer.WriteEndElement()

        $writer.WriteStartElement("sheetData")
        $writer.WriteStartElement("row")
        $writer.WriteAttributeString("r", "1")
        for ($columnIndex = 0; $columnIndex -lt $columns.Count; $columnIndex++) {
            $cellRef = "{0}1" -f (ConvertTo-ExcelColumnName ($columnIndex + 1))
            $writer.WriteStartElement("c")
            $writer.WriteAttributeString("r", $cellRef)
            $writer.WriteAttributeString("s", "1")
            $writer.WriteAttributeString("t", "inlineStr")
            $writer.WriteStartElement("is")
            $writer.WriteElementString("t", $columns[$columnIndex])
            $writer.WriteEndElement()
            $writer.WriteEndElement()
        }
        $writer.WriteEndElement()

        $rowNumber = 2
        foreach ($row in $Rows) {
            $writer.WriteStartElement("row")
            $writer.WriteAttributeString("r", [string]$rowNumber)
            for ($columnIndex = 0; $columnIndex -lt $columns.Count; $columnIndex++) {
                $columnName = $columns[$columnIndex]
                $cellRef = "{0}{1}" -f (
                    ConvertTo-ExcelColumnName ($columnIndex + 1)
                ), $rowNumber
                $value = $row.$columnName
                $writer.WriteStartElement("c")
                $writer.WriteAttributeString("r", $cellRef)
                if (Test-NumericCell $value) {
                    $writer.WriteElementString("v", (ConvertTo-NumberText $value))
                }
                else {
                    $writer.WriteAttributeString("t", "inlineStr")
                    $writer.WriteStartElement("is")
                    $writer.WriteStartElement("t")
                    $writer.WriteString([string](ConvertTo-CellValue $value))
                    $writer.WriteEndElement()
                    $writer.WriteEndElement()
                }
                $writer.WriteEndElement()
            }
            $writer.WriteEndElement()
            $rowNumber += 1
        }
        $writer.WriteEndElement()
        if ($Rows.Count -gt 0) {
            $writer.WriteStartElement("autoFilter")
            $writer.WriteAttributeString("ref", $dimension)
            $writer.WriteEndElement()
        }
        $writer.WriteEndElement()
        $writer.WriteEndDocument()
    }
    finally {
        $writer.Close()
    }
}

function Write-TextFile([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$sheets = New-Object System.Collections.Generic.List[object]
$sheetSources = @(
    @{ Name = "run_summary"; Rows = Import-JsonObjectRows "summary.json" },
    @{ Name = "run_metadata"; Rows = Import-JsonObjectRows "metadata.json" },
    @{ Name = "summary_csv"; Rows = Import-CsvRowsByName "summary.csv" },
    @{ Name = "endpoint_summary"; Rows = Import-CsvRowsByName "endpoint-summary.csv" },
    @{ Name = "endpoint_allocation"; Rows = Import-CsvRowsByName "endpoint-allocation.csv" },
    @{ Name = "periodic_summary"; Rows = Import-CsvRowsByName "periodic-summary.csv" },
    @{ Name = "phase_summary"; Rows = Import-CsvRowsByName "phase-summary.csv" },
    @{ Name = "phase_endpoint_summary"; Rows = Import-CsvRowsByName "phase-endpoint-summary.csv" },
    @{ Name = "prometheus_metrics"; Rows = Import-PrometheusMetricRows }
)

if (-not $SkipRawLocust) {
    $sheetSources += @(
        @{ Name = "locust_stats"; Rows = Import-CsvRowsByName "locust_stats.csv" },
        @{ Name = "locust_failures"; Rows = Import-CsvRowsByName "locust_failures.csv" },
        @{ Name = "locust_exceptions"; Rows = Import-CsvRowsByName "locust_exceptions.csv" },
        @{ Name = "locust_history"; Rows = Import-CsvRowsByName "locust_stats_history.csv" }
    )
}

foreach ($source in $sheetSources) {
    if (@($source.Rows).Count -gt 0) {
        $sheets.Add([pscustomobject]@{
            Name = $source.Name
            Rows = @($source.Rows)
        })
    }
}

if ($sheets.Count -eq 0) {
    throw "No load-test result files were found in $resultsPath."
}

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "dekstra-xlsx-{0}" -f ([guid]::NewGuid().ToString("N"))
)

New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
try {
    $workbookDir = Join-Path $temporaryRoot "xl"
    $worksheetsDir = Join-Path $workbookDir "worksheets"
    $relsDir = Join-Path $temporaryRoot "_rels"
    $workbookRelsDir = Join-Path $workbookDir "_rels"
    New-Item -ItemType Directory -Force -Path $worksheetsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $relsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $workbookRelsDir | Out-Null

    $seenSheetNames = @{}
    for ($index = 0; $index -lt $sheets.Count; $index++) {
        $sheet = $sheets[$index]
        $sheetName = ConvertTo-SheetName $sheet.Name $seenSheetNames
        $sheet | Add-Member -NotePropertyName SheetName -NotePropertyValue $sheetName
        $sheetPath = Join-Path $worksheetsDir ("sheet{0}.xml" -f ($index + 1))
        Write-WorksheetXml $sheetPath $sheetName $sheet.Rows
    }

    $contentTypesBuilder = New-Object System.Text.StringBuilder
    [void]$contentTypesBuilder.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$contentTypesBuilder.AppendLine('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">')
    [void]$contentTypesBuilder.AppendLine('  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>')
    [void]$contentTypesBuilder.AppendLine('  <Default Extension="xml" ContentType="application/xml"/>')
    [void]$contentTypesBuilder.AppendLine('  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>')
    [void]$contentTypesBuilder.AppendLine('  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>')
    for ($index = 0; $index -lt $sheets.Count; $index++) {
        [void]$contentTypesBuilder.AppendLine(
            '  <Override PartName="/xl/worksheets/sheet{0}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' -f
            ($index + 1)
        )
    }
    [void]$contentTypesBuilder.AppendLine('</Types>')
    Write-TextFile (Join-Path $temporaryRoot "[Content_Types].xml") $contentTypesBuilder.ToString()

    Write-TextFile (Join-Path $relsDir ".rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"@

    $workbookBuilder = New-Object System.Text.StringBuilder
    [void]$workbookBuilder.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$workbookBuilder.AppendLine('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">')
    [void]$workbookBuilder.AppendLine('  <sheets>')
    for ($index = 0; $index -lt $sheets.Count; $index++) {
        $sheetId = $index + 1
        $workbookLine = '    <sheet name="{0}" sheetId="{1}" r:id="rId{1}"/>' -f
            (ConvertTo-SafeXmlText $sheets[$index].SheetName),
            $sheetId
        [void]$workbookBuilder.AppendLine($workbookLine)
    }
    [void]$workbookBuilder.AppendLine('  </sheets>')
    [void]$workbookBuilder.AppendLine('</workbook>')
    Write-TextFile (Join-Path $workbookDir "workbook.xml") $workbookBuilder.ToString()

    $relationshipsBuilder = New-Object System.Text.StringBuilder
    [void]$relationshipsBuilder.AppendLine('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    [void]$relationshipsBuilder.AppendLine('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    for ($index = 0; $index -lt $sheets.Count; $index++) {
        $sheetId = $index + 1
        $relationshipLine = '  <Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{0}.xml"/>' -f
            $sheetId
        [void]$relationshipsBuilder.AppendLine($relationshipLine)
    }
    $styleRelationshipLine = '  <Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' -f
        ($sheets.Count + 1)
    [void]$relationshipsBuilder.AppendLine($styleRelationshipLine)
    [void]$relationshipsBuilder.AppendLine('</Relationships>')
    Write-TextFile (Join-Path $workbookRelsDir "workbook.xml.rels") $relationshipsBuilder.ToString()

    Write-TextFile (Join-Path $workbookDir "styles.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"@

    if (Test-Path $outputFullPath) {
        Remove-Item $outputFullPath -Force
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $temporaryRoot,
        $outputFullPath
    )
}
finally {
    if (Test-Path $temporaryRoot) {
        Remove-Item $temporaryRoot -Recurse -Force
    }
}

Write-Host "Excel workbook saved to $outputFullPath"
foreach ($sheet in $sheets) {
    Write-Host ("  {0}: {1} rows" -f $sheet.SheetName, $sheet.Rows.Count)
}
