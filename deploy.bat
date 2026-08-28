@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: One-Button Deployment Wrapper
:: Builds and starts the API + PostgreSQL using Docker Compose
:: ============================================================

title API Deployment

:: Parse command-line arguments in any order. --no-pause is used by automation;
:: double-click deployment still pauses so users can read the result.
set "ARGS="
set "NO_PAUSE=0"
:parse_args
if "%~1"=="" goto run_deploy
if /I "%~1"=="--rebuild" set "ARGS=!ARGS! -ForceRebuild"
if /I "%~1"=="--no-smoke" set "ARGS=!ARGS! -SkipSmokeTest"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto parse_args

:run_deploy

:: Run deployment
echo ============================================================
echo   API Deployment - Starting...
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy.ps1" %ARGS%
set "EXIT_CODE=!ERRORLEVEL!"

echo.
if !EXIT_CODE! equ 0 (
    echo ============================================================
    echo   Deployment completed successfully.
    echo ============================================================
) else (
    echo ============================================================
    echo   Deployment FAILED with exit code !EXIT_CODE!
    echo   Review the output above for details.
    echo ============================================================
)

echo.
if !NO_PAUSE! equ 0 (
    echo Press any key to exit...
    pause >nul
)
exit /b !EXIT_CODE!
