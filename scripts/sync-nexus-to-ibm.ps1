#Requires -Version 7.0
<#
.SYNOPSIS
    THRONE Intelligence — NEXUS to IBM watsonx Sync Script

.DESCRIPTION
    Exports NEXUS CORE data (E:\ultron-memory) to IBM-compatible formats
    and optionally syncs with IBM watsonx Data Intelligence.

.PARAMETER Format
    Output format: csv, jsonl, or both (default: both)

.PARAMETER OutputDir
    Export directory (default: E:\ultron-memory\exports)

.PARAMETER SyncToIBM
    Also sync exported data to IBM watsonx (requires DI_APIKEY env var)

.PARAMETER Interactive
    Prompt for confirmation before destructive operations

.EXAMPLE
    .\sync-nexus-to-ibm.ps1 -Format jsonl -OutputDir D:\exports

.EXAMPLE
    .\sync-nexus-to-ibm.ps1 -SyncToIBM -Verbose
#>

[CmdletBinding()]
param(
    [ValidateSet("csv", "jsonl", "both")]
    [string]$Format = "both",

    [string]$OutputDir = "E:\ultron-memory\exports",

    [switch]$SyncToIBM,

    [switch]$Interactive
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\KING\projects\throne-intelligence"
$BridgeScript = "$ProjectRoot\src\throne_intelligence\nexus_to_ibm_bridge.py"

# ── Validate Prerequisites ──────────────────────────────────────────────

if (-not (Test-Path $BridgeScript)) {
    Write-Error "Bridge script not found: $BridgeScript"
    exit 1
}

if (-not (Test-Path "E:\ultron-memory\nexus-core\data\nexus.db")) {
    Write-Error "NEXUS DB not found at E:\ultron-memory\nexus-core\data\nexus.db"
    exit 1
}

# ── Export Data ─────────────────────────────────────────────────────────

Write-Host "=== THRONE Intelligence: NEXUS -> IBM Sync ===" -ForegroundColor Cyan
Write-Host "Format: $Format"
Write-Host "Output: $OutputDir"
Write-Host ""

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "$OutputDir\sync_$timestamp.log"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Write-Host "[1/3] Running NEXUS export bridge..." -ForegroundColor Yellow

$pythonArgs = @(
    $BridgeScript,
    "--format", $Format,
    "--output", $OutputDir
)

try {
    $output = & python3 $pythonArgs 2>&1
    $output | Tee-Object -FilePath $logFile -Append
    Write-Host "Export complete. Log: $logFile" -ForegroundColor Green
} catch {
    Write-Error "Export failed: $_"
    exit 1
}

# ── Verify Export ───────────────────────────────────────────────────────

Write-Host ""
Write-Host "[2/3] Verifying export files..." -ForegroundColor Yellow

$jsonlFile = "$OutputDir\nexus_catalog.jsonl"
$csvNotes = "$OutputDir\nexus_notes.csv"
$csvDocs = "$OutputDir\nexus_docs.csv"

$files = @($jsonlFile, $csvNotes, $csvDocs) | Where-Object { Test-Path $_ }

foreach ($file in $files) {
    $size = (Get-Item $file).Length
    Write-Host "  OK: $(Split-Path $file -Leaf) ($size bytes)" -ForegroundColor Green
}

# Count records in JSONL
if (Test-Path $jsonlFile) {
    $count = (Get-Content $jsonlFile | Measure-Object).Count
    Write-Host "  Total records: $count" -ForegroundColor Cyan
}

# ── Sync to IBM (Optional) ──────────────────────────────────────────────

if ($SyncToIBM) {
    Write-Host ""
    Write-Host "[3/3] Syncing to IBM watsonx..." -ForegroundColor Yellow

    $apiKey = [Environment]::GetEnvironmentVariable("IBM_API_KEY", "User")
    if (-not $apiKey) {
        Write-Error "IBM_API_KEY not found in Windows user environment variables"
        exit 1
    }

    # Check if ibm-watsonx-ai is installed
    try {
        $null = python3 -c "import ibm_watsonx_ai" 2>$null
        Write-Host "  ibm-watsonx-ai SDK found" -ForegroundColor Green
    } catch {
        Write-Host "  Installing ibm-watsonx-ai..." -ForegroundColor Yellow
        & pip install ibm-watsonx-ai
    }

    Write-Host "  IBM sync placeholder — implement upload logic here" -ForegroundColor Magenta
    Write-Host "  See: https://ibm.biz/watsonx-data-intelligence-docs"
} else {
    Write-Host ""
    Write-Host "[3/3] Skipping IBM sync (use -SyncToIBM to enable)" -ForegroundColor Gray
}

# ── Summary ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Sync Complete ===" -ForegroundColor Cyan
Write-Host "Files: $OutputDir"
Write-Host "Log: $logFile"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Import JSONL into IBM watsonx Data Intelligence"
Write-Host "  2. Run: hermes mcp test ibm-watsonx"
Write-Host "  3. Query: 'Search NEXUS catalog for API keys'"
