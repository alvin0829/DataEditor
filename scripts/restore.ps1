<#
.SYNOPSIS
    Replace the application database with a verified custom-format backup.
.DESCRIPTION
    Stops the API, restores the dump in one PostgreSQL transaction, and starts
    the API again. Existing application tables are replaced only after explicit
    confirmation. A failed restore is rolled back and returns a non-zero exit.
.PARAMETER InputPath
    Path to the .dump backup file. Required.
.PARAMETER Confirm
    Skip the interactive RESTORE confirmation (for controlled automation).
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$InputPath,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

function Invoke-DockerCommand {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker @Arguments 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
}

$resolvedInput = Resolve-Path -LiteralPath $InputPath -ErrorAction SilentlyContinue
if (-not $resolvedInput) {
    Write-Host "[FAIL] Backup file not found: $InputPath" -ForegroundColor Red
    exit 1
}

$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Host "[FAIL] .env not found. Run deploy.bat first." -ForegroundColor Red
    exit 1
}
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2], "Process")
    }
}

$dbName = $env:POSTGRES_DB
$dbUser = $env:POSTGRES_USER
$container = "app-db"
$state = docker inspect --format='{{.State.Running}}' $container 2>$null
if ($state -ne "true") {
    Write-Host "[FAIL] Database container '$container' is not running." -ForegroundColor Red
    exit 1
}

$fileSize = (Get-Item -LiteralPath $resolvedInput).Length
$sizeMB = [math]::Round($fileSize / 1MB, 2)
Write-Host "`n=== RESTORE CONFIRMATION ===" -ForegroundColor Yellow
Write-Host "  Database: $dbName"
Write-Host "  Backup:   $resolvedInput"
Write-Host "  Size:     $sizeMB MB"
Write-Host "  Action:   Replace existing application tables and data"

if (-not $Confirm) {
    $response = Read-Host "Type 'RESTORE' to continue"
    if ($response -ne "RESTORE") {
        Write-Host "[CANCELLED] Restore aborted." -ForegroundColor Yellow
        exit 0
    }
}

$apiWasRunning = (docker inspect --format='{{.State.Running}}' app-api 2>$null) -eq "true"
$restoreSucceeded = $false
try {
    if ($apiWasRunning) {
        Write-Host "  [1/4] Stopping API to prevent writes during restore..." -ForegroundColor Gray
        if ((Invoke-DockerCommand -Arguments @("compose", "stop", "api")) -ne 0) {
            throw "Could not stop API container"
        }
    }

    Write-Host "  [2/4] Copying backup into database container..." -ForegroundColor Gray
    if ((Invoke-DockerCommand -Arguments @("cp", [string]$resolvedInput, "${container}:/tmp/restore.dump")) -ne 0) {
        throw "Could not copy backup into database container"
    }

    Write-Host "  [3/4] Restoring in a single transaction..." -ForegroundColor Gray
    $restoreArgs = @(
        "exec", $container,
        "pg_restore", "-U", $dbUser, "-d", $dbName,
        "--clean", "--if-exists", "--no-owner", "--no-privileges",
        "--single-transaction", "--exit-on-error", "/tmp/restore.dump"
    )
    if ((Invoke-DockerCommand -Arguments $restoreArgs) -ne 0) {
        throw "pg_restore failed; PostgreSQL rolled back the restore transaction"
    }
    $restoreSucceeded = $true
} catch {
    Write-Host "[FAIL] Restore failed: $_" -ForegroundColor Red
} finally {
    Write-Host "  [4/4] Cleaning up and restarting API..." -ForegroundColor Gray
    $null = Invoke-DockerCommand -Arguments @("exec", $container, "rm", "-f", "/tmp/restore.dump")
    if ($apiWasRunning) {
        $null = Invoke-DockerCommand -Arguments @("compose", "up", "-d", "api")
    }
}

if (-not $restoreSucceeded) { exit 1 }
Write-Host "[OK] Restore completed successfully" -ForegroundColor Green
Write-Host "  Database: $dbName"
Write-Host "  Verify:   .\scripts\status.ps1"
