<#
.SYNOPSIS
    Stop all services without removing data.
.DESCRIPTION
    Gracefully stops db and api containers. Named volume is preserved.
.PARAMETER RemoveContainers
    Also remove stopped containers (data volume is still preserved).
#>
param(
    [switch]$RemoveContainers
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Host "Stopping services..." -ForegroundColor Cyan

if ($RemoveContainers) {
    docker compose down 2>&1 | ForEach-Object { Write-Host "  $_" }
    Write-Host "[OK] Services stopped and containers removed (data volume preserved)" -ForegroundColor Green
} else {
    docker compose stop 2>&1 | ForEach-Object { Write-Host "  $_" }
    Write-Host "[OK] Services stopped (containers preserved for quick restart)" -ForegroundColor Green
}
