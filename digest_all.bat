@echo off
setlocal

REM ============================================================
REM   Digest all libraries
REM
REM   Convenience wrapper: runs the pipeline against each of
REM   your archive libraries in sequence, then optionally runs
REM   clean_stale.py to identify or remove stale digested files.
REM
REM   Usage:
REM     digest_all.bat                     digest + report stale (default)
REM     digest_all.bat --delete-stale      digest + delete stale (confirms each library)
REM     digest_all.bat --delete-orphans    digest + delete stale AND orphans (no prompt)
REM     digest_all.bat --skip-stale        digest only, no stale check
REM
REM   Edit the paths below to match your setup. Comment out
REM   any library you don't want included by prefixing with REM.
REM ============================================================

set "PIPELINE=%~dp0process_folder.py"
set "STALE=%~dp0clean_stale.py"

REM ---------- Parse stale-check mode from first argument ----------
REM STALE_ARGS is appended to clean_stale.py invocations.
REM Empty STALE_MODE means skip the stale check entirely.
set "STALE_MODE=report"
set "STALE_ARGS="
if /i "%~1"=="--skip-stale" set "STALE_MODE="
if /i "%~1"=="--delete-stale" (
    set "STALE_MODE=delete"
    set "STALE_ARGS=--delete"
)
if /i "%~1"=="--delete-orphans" (
    set "STALE_MODE=delete-orphans"
    set "STALE_ARGS=--delete-orphans --yes"
)

REM ---------- Locate Python ----------
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    set "PY=python"
)

echo.
echo ============================================================
echo   Digesting all archive libraries
echo   Stale-check mode: %STALE_MODE%
echo ============================================================
echo.

REM ============================================================
REM   Library 1: ChatGPT Backup
REM ============================================================
echo --- ChatGPT Backup: digest ---
%PY% "%PIPELINE%" "I:\AI\Backups\ChatGPT\Exported\1-Raw" "I:\AI\Backups\ChatGPT\Exported\2-Digested"
if errorlevel 1 goto :error

if not "%STALE_MODE%"=="" (
    echo.
    echo --- ChatGPT Backup: stale check ---
    %PY% "%STALE%" "I:\AI\Backups\ChatGPT\Exported\1-Raw" "I:\AI\Backups\ChatGPT\Exported\2-Digested" %STALE_ARGS%
)

REM ============================================================
REM   Library 2: Claude Backup
REM ============================================================
echo.
echo --- Claude Backup: digest ---
%PY% "%PIPELINE%" "I:\AI\Backups\Claude\Exported\1-Raw" "I:\AI\Backups\Claude\Exported\2-Digested"
if errorlevel 1 goto :error

if not "%STALE_MODE%"=="" (
    echo.
    echo --- Claude Backup: stale check ---
    %PY% "%STALE%" "I:\AI\Backups\Claude\Exported\1-Raw" "I:\AI\Backups\Claude\Exported\2-Digested" %STALE_ARGS%
)

REM ============================================================
REM   Library 3: Loom
REM ============================================================
echo.
echo --- Loom: digest ---
%PY% "%PIPELINE%" "I:\RPG\_Design\Loom\1-Raw" "I:\RPG\_Design\Loom\2-Digested"
if errorlevel 1 goto :error

if not "%STALE_MODE%"=="" (
    echo.
    echo --- Loom: stale check ---
    %PY% "%STALE%" "I:\RPG\_Design\Loom\1-Raw" "I:\RPG\_Design\Loom\2-Digested" %STALE_ARGS%
)

echo.
echo ============================================================
echo   All libraries digested successfully.
echo ============================================================
pause
exit /b 0

:error
echo.
echo ============================================================
echo   A library failed to digest. Check the messages above.
echo ============================================================
pause
exit /b 1
