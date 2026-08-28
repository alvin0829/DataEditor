<#
.SYNOPSIS
    Main deployment orchestrator for the API + PostgreSQL stack.
.DESCRIPTION
    Validates prerequisites, generates .env if needed, builds/starts services,
    waits for readiness, and runs a smoke test.
.PARAMETER SkipSmokeTest
    Skip the smoke test after deployment.
.PARAMETER ForceRebuild
    Force rebuild of the API image even if cached.
#>
param(
    [switch]$SkipSmokeTest,
    [switch]$ForceRebuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

# ─── Helpers ────────────────────────────────────────────────────────────
function Write-Step  { param([string]$Msg) Write-Host "`n>>> $Msg" -ForegroundColor Cyan }
function Write-OK    { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN] $Msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$Msg) Write-Host "[FAIL] $Msg" -ForegroundColor Red }
function Invoke-DockerCommand {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker @Arguments 2>&1 | ForEach-Object { Write-Host "  $_" }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
}

# ─── 1. Validate prerequisites ─────────────────────────────────────────
Write-Step "Checking prerequisites"

# Docker CLI
try {
    $dockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "docker version failed" }
    Write-OK "Docker CLI found ($dockerVersion)"
} catch {
    Write-Fail "Docker CLI not found or not in PATH."
    Write-Host "  Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor White
    exit 1
}

# Docker Compose (v2 plugin)
try {
    $composeVersion = docker compose version --short 2>&1
    if ($LASTEXITCODE -ne 0) { throw "compose version failed" }
    Write-OK "Docker Compose v$composeVersion found"
} catch {
    Write-Fail "Docker Compose plugin not found."
    Write-Host "  Install or update Docker Desktop to get the Compose plugin." -ForegroundColor White
    exit 1
}

# Docker daemon. Best-effort start makes deployment genuinely one-button on
# ordinary Windows PCs with Docker Desktop already installed.
$daemonReady = $false
try {
    $null = docker info 2>&1
    $daemonReady = ($LASTEXITCODE -eq 0)
} catch {}

if (-not $daemonReady) {
    Write-Warn "Docker daemon is not running; attempting to start Docker Desktop/Engine"
    $dockerService = Get-Service -Name docker -ErrorAction SilentlyContinue
    if ($dockerService -and $dockerService.Status -ne "Running") {
        try { Start-Service -Name docker -ErrorAction Stop } catch {}
    }

    $desktopCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe")
    )
    $desktopPath = $desktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ((-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) -and $desktopPath) {
        Start-Process -FilePath $desktopPath -WindowStyle Minimized
    }

    for ($attempt = 1; $attempt -le 24; $attempt++) {
        Start-Sleep -Seconds 5
        try {
            $null = docker info 2>&1
            if ($LASTEXITCODE -eq 0) { $daemonReady = $true; break }
        } catch {}
        Write-Host "  Waiting for Docker... $($attempt * 5)s" -ForegroundColor Gray
    }
}

if (-not $daemonReady) {
    Write-Fail "Docker daemon could not be started within 120 seconds."
    Write-Host "  Start Docker Desktop manually and run deploy.bat again." -ForegroundColor White
    exit 1
}
Write-OK "Docker daemon is running"

# ─── 2. Generate .env if missing ───────────────────────────────────────
Write-Step "Checking environment configuration"

$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[INFO] No .env found. Generating with secure credentials..." -ForegroundColor Yellow
    & "$ScriptDir\generate-env.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to generate .env"
        exit 1
    }
} else {
    Write-OK ".env already exists"
}

# ─── 3. Validate compose config ────────────────────────────────────────
Write-Step "Validating docker-compose.yml"

try {
    $null = docker compose config 2>&1
    if ($LASTEXITCODE -ne 0) { throw "config validation failed" }
    Write-OK "docker-compose.yml is valid"
} catch {
    Write-Fail "docker-compose.yml validation failed."
    docker compose config 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor White }
    exit 1
}

# ─── 4. Build API image (optional force) ───────────────────────────────
Write-Step "Building API image"

$buildArgs = @("compose", "build", "api")
if ($ForceRebuild) { $buildArgs += "--no-cache" }

$buildExit = Invoke-DockerCommand -Arguments $buildArgs
if ($buildExit -ne 0) {
    Write-Fail "Docker build failed"
    exit 1
}
Write-OK "API image built"

# ─── 5. Start services (idempotent) ────────────────────────────────────
Write-Step "Starting services (db + api)"

$upExit = Invoke-DockerCommand -Arguments @("compose", "up", "-d")
if ($upExit -ne 0) {
    Write-Fail "Failed to start services"
    exit 1
}
Write-OK "Services started"

# ─── 6. Wait for readiness ─────────────────────────────────────────────
Write-Step "Waiting for services to become healthy"

$maxWait = 120  # seconds
$interval = 5
$elapsed = 0
$healthy = $false

while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds $interval
    $elapsed += $interval

    # Check container health status
    $dbHealth = docker inspect --format='{{.State.Health.Status}}' app-db 2>$null
    $apiHealth = docker inspect --format='{{.State.Health.Status}}' app-api 2>$null

    if ($dbHealth -eq "healthy" -and $apiHealth -eq "healthy") {
        $healthy = $true
        break
    }

    $dbStatus = if ($dbHealth) { $dbHealth } else { "starting" }
    $apiStatus = if ($apiHealth) { $apiHealth } else { "starting" }
    Write-Host "  [$elapsed/${maxWait}s] db=$dbStatus api=$apiStatus" -ForegroundColor Gray
}

if (-not $healthy) {
    Write-Warn "Services did not become healthy within ${maxWait}s"
    Write-Host "  Check logs: docker compose logs --tail=50" -ForegroundColor White

    # Show recent logs for debugging
    Write-Host "`n--- Recent API logs ---" -ForegroundColor Yellow
    $null = Invoke-DockerCommand -Arguments @("compose", "logs", "--tail=20", "api")
    Write-Host "--- End logs ---`n" -ForegroundColor Yellow

    exit 1
}
Write-OK "All services healthy"

# ─── 7. Show service status ────────────────────────────────────────────
Write-Step "Service status"
$null = Invoke-DockerCommand -Arguments @("compose", "ps")

# ─── 8. Smoke test ─────────────────────────────────────────────────────
if ($SkipSmokeTest) {
    Write-Host "`n[SKIP] Smoke test skipped by flag." -ForegroundColor Yellow
} else {
    Write-Step "Running smoke test"

    $apiPort = (Select-String -Path $EnvFile -Pattern "^API_PORT=(\d+)" -AllMatches).Matches[0].Groups[1].Value
    if (-not $apiPort) { $apiPort = "8080" }

    $baseUrl = "http://localhost:$apiPort"
    $testId = "SMK-$(Get-Date -Format 'yyyyMMddHHmmss')-$(Get-Random -Maximum 9999)"

    try {
        # 8a. Health check
        Write-Host "  [1/4] Health check..." -ForegroundColor Gray
        $health = Invoke-RestMethod -Uri "$baseUrl/health" -Method GET -TimeoutSec 10
        if ($health.status -ne "ok") {
            throw "Health check returned status: $($health.status)"
        }
        Write-OK "Health check passed"

        # 8b. Create a unique test request
        Write-Host "  [2/4] Creating test request ($testId)..." -ForegroundColor Gray
        $createBody = @{
            request_number = $testId
            department = "Deployment Test"
            status = "created"
            data = @{ source = "smoke-test"; timestamp = (Get-Date -Format "o") }
        } | ConvertTo-Json -Depth 5

        $createResult = Invoke-RestMethod -Uri "$baseUrl/api/requests" -Method POST `
            -Body $createBody -ContentType "application/json" -TimeoutSec 10

        if (-not $createResult) {
            throw "Create request returned empty response"
        }
        Write-OK "Test request created"

        # 8c. Retrieve the created request
        Write-Host "  [3/4] Retrieving test request..." -ForegroundColor Gray
        $getResult = Invoke-RestMethod -Uri "$baseUrl/api/requests/$($createResult.id)" -Method GET -TimeoutSec 10
        if ($getResult.request_number -ne $testId) {
            throw "Retrieved request mismatch: expected $testId, got $($getResult.request_number)"
        }
        Write-OK "Test request retrieved correctly"

        # 8d. List requests and verify presence
        Write-Host "  [4/4] Listing requests..." -ForegroundColor Gray
        $listResult = Invoke-RestMethod -Uri "$baseUrl/api/requests" -Method GET -TimeoutSec 10
        $found = $false
        if ($listResult -is [array]) {
            $found = $listResult | Where-Object { $_.request_number -eq $testId }
        } elseif ($listResult.request_number -eq $testId) {
            $found = $true
        } elseif ($listResult.items) {
            $found = $listResult.items | Where-Object { $_.request_number -eq $testId }
        }

        if (-not $found) {
            throw "Test request not found in list"
        }
        Write-OK "Test request found in list"

    } catch {
        Write-Fail "Smoke test FAILED: $_"
        Write-Host "  Check API logs: docker compose logs api --tail=30" -ForegroundColor White
        exit 1
    }
}

# ─── 9. Done ───────────────────────────────────────────────────────────
$apiPort = (Select-String -Path $EnvFile -Pattern "^API_PORT=(\d+)" -AllMatches).Matches[0].Groups[1].Value
if (-not $apiPort) { $apiPort = "8080" }

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "  API:       http://localhost:$apiPort" -ForegroundColor White
Write-Host "  API Docs:  http://localhost:$apiPort/docs" -ForegroundColor White
Write-Host "  LAN:       http://<this-server-ip>:$apiPort" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    Check status:  .\scripts\status.ps1" -ForegroundColor White
Write-Host "    View logs:     .\scripts\logs.ps1" -ForegroundColor White
Write-Host "    Stop:          .\scripts\stop.ps1" -ForegroundColor White
Write-Host "    Backup:        .\scripts\backup.ps1" -ForegroundColor White
Write-Host "    Redeploy:      .\deploy.bat --rebuild" -ForegroundColor White
Write-Host ""
