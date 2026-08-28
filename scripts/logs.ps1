<#
.SYNOPSIS
    Tail logs from services.
.DESCRIPTION
    Shows recent logs from api and db services.
.PARAMETER Service
    Specific service to tail (api, db). Default: all.
.PARAMETER Lines
    Number of recent lines to show. Default: 50.
.PARAMETER Follow
    Continuously follow log output.
#>
param(
    [ValidateSet("api", "db", "all")]
    [string]$Service = "all",
    [int]$Lines = 50,
    [switch]$Follow
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

$args = @("compose", "logs", "--tail=$Lines")
if ($Follow) { $args += "-f" }
if ($Service -ne "all") { $args += $Service }

Write-Host "Showing logs (last $Lines lines)..." -ForegroundColor Cyan
& docker @args 2>&1 | ForEach-Object { Write-Host $_ }
