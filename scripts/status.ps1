<#
.SYNOPSIS
    Show service status and health.
.DESCRIPTION
    Displays container status, health, ports, and disk usage.
#>
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Host "`n=== Service Status ===" -ForegroundColor Cyan
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1 | ForEach-Object { Write-Host "  $_" }

Write-Host "`n=== Container Health ===" -ForegroundColor Cyan
foreach ($svc in @("app-db", "app-api")) {
    $health = docker inspect --format='{{.State.Health.Status}} (last: {{with .State.Health.Log}}{{(index . 0).Output}}{{end}})' $svc 2>$null
    if ($health) {
        Write-Host "  ${svc}: $health" -ForegroundColor White
    } else {
        Write-Host "  ${svc}: not running" -ForegroundColor Yellow
    }
}

Write-Host "`n=== Volume Usage ===" -ForegroundColor Cyan
$volSize = docker system df -v 2>$null | Select-String "app-pgdata"
if ($volSize) { Write-Host "  $volSize" } else { Write-Host "  Volume data unavailable" }
