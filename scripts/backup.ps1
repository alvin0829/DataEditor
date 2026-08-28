<#
.SYNOPSIS
    Backup the PostgreSQL database to a dump file.
.DESCRIPTION
    Creates a pg_dump of the app database into the backups/ directory.
    Uses the running container - no host PostgreSQL client needed.
.PARAMETER OutputPath
    Custom output file path. Default: backups/YYYY-MM-DD_HHMMSS.dump
.PARAMETER Format
    Dump format: custom (default), plain, directory, tar.
#>
param(
    [string]$OutputPath,
    [ValidateSet("custom", "plain", "directory", "tar")]
    [string]$Format = "custom"
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

# Load env for database credentials
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[FAIL] .env not found. Run deploy.bat first." -ForegroundColor Red
    exit 1
}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.+)$') {
        [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
    }
}

$dbName = $env:POSTGRES_DB
$dbUser = $env:POSTGRES_USER

# Ensure backups directory
$backupsDir = Join-Path $ProjectRoot "backups"
if (-not (Test-Path $backupsDir)) {
    New-Item -ItemType Directory -Path $backupsDir | Out-Null
}

# Determine output path
if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $ext = switch ($Format) {
        "custom"    { "dump" }
        "plain"     { "sql" }
        "tar"       { "tar" }
        "directory" { "" }
        default     { "dump" }
    }
    $OutputPath = Join-Path $backupsDir "${dbName}_${timestamp}.${ext}"
}

Write-Host "Backing up database '$dbName'..." -ForegroundColor Cyan
Write-Host "  Output: $OutputPath" -ForegroundColor White

$container = "app-db"

# Check container is running
$state = docker inspect --format='{{.State.Running}}' $container 2>$null
if ($state -ne "true") {
    Write-Host "[FAIL] Database container '$container' is not running." -ForegroundColor Red
    Write-Host "  Start it first: .\deploy.bat" -ForegroundColor White
    exit 1
}

# Run pg_dump
$dumpArgs = @(
    "exec", "-t", $container,
    "pg_dump", "-U", $dbUser, "-d", $dbName,
    "-Fc",  # custom format always for reliability; we convert if needed
    "-f", "/tmp/backup.dump"
)

Write-Host "  Running pg_dump inside container..." -ForegroundColor Gray
& docker @dumpArgs 2>&1 | ForEach-Object { Write-Host "  $_" }

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] pg_dump failed." -ForegroundColor Red
    exit 1
}

# Copy dump out of container
Write-Host "  Extracting backup from container..." -ForegroundColor Gray
& docker cp "${container}:/tmp/backup.dump" $OutputPath 2>&1 | ForEach-Object { Write-Host "  $_" }

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Failed to extract backup from container." -ForegroundColor Red
    exit 1
}

# Clean up temp file in container
& docker exec $container rm -f /tmp/backup.dump 2>$null

# Report
$fileSize = (Get-Item $OutputPath).Length
$sizeMB = [math]::Round($fileSize / 1MB, 2)

Write-Host ""
Write-Host "[OK] Backup completed" -ForegroundColor Green
Write-Host "  File: $OutputPath" -ForegroundColor White
Write-Host "  Size: $sizeMB MB" -ForegroundColor White
Write-Host "  Database: $dbName (user: $dbUser)" -ForegroundColor White
