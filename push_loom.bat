@echo off
setlocal

REM ============================================================
REM   push_loom.bat
REM
REM   Ongoing-use: pushes local Loom changes to Drive Loom.
REM   Non-destructive: never deletes Drive files. Uses --update
REM   so newer Drive files are not overwritten.
REM
REM   Run after a pipeline session to back up local changes to
REM   Drive. Safe to run repeatedly; identical files are no-ops.
REM
REM   For the FIRST run after setting up rclone, use
REM   merge_loom_to_drive.bat instead (which does dry-run passes
REM   first and prompts between steps).
REM ============================================================

set "LOCAL_LOOM=I:\RPG\_Design\Loom"
REM Drive path mirrors the local nested structure under My Drive:
REM     My Drive\RPG\_Design\Loom
REM (NOT the top-level My Drive\Loom -- that was a misconfiguration
REM created on the first merge run before this was caught. If a
REM stale top-level Loom\ still exists on Drive, delete it manually.)
set "DRIVE_LOOM=drive:RPG/_Design/Loom"
set "EXCLUDES=--exclude Thumbs.db --exclude desktop.ini --exclude .DS_Store"

REM Log file for this run. Date-stamped (YYYY-MM-DD); same-day re-runs
REM append to the same file. Written by rclone itself via --log-file, so
REM it appears the moment rclone starts and persists even if rclone
REM errors mid-run. NOTE: if a sanity check below fails (no rclone, no
REM remote, no local path) the script exits BEFORE invoking rclone, and
REM no log file is created -- those failures are loud on console and
REM there is nothing to log anyway.
set "LOGFILE=%~dp0push_loom_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

REM Full path to rclone.exe. Edit this if you move the rclone
REM folder. The scripts do NOT require rclone on the system PATH.
set "RCLONEPATH=I:\rclone-v1.74.1-windows-amd64\rclone.exe"

REM Sanity check: rclone present at RCLONEPATH?
if not exist "%RCLONEPATH%" (
    echo ERROR: rclone.exe not found at:
    echo     %RCLONEPATH%
    echo Edit the RCLONEPATH line near the top of this .bat file
    echo to point at your rclone.exe.
    pause
    exit /b 1
)

REM Sanity check: drive: remote configured?
"%RCLONEPATH%" listremotes | findstr /B /C:"drive:" >nul
if errorlevel 1 (
    echo ERROR: rclone has no remote named "drive". Run: rclone config
    pause
    exit /b 1
)

REM Sanity check: local source exists?
if not exist "%LOCAL_LOOM%" (
    echo ERROR: local source does not exist: %LOCAL_LOOM%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Pushing local Loom to Drive
echo ============================================================
echo   Local : %LOCAL_LOOM%
echo   Drive : %DRIVE_LOOM%
echo   Log   : %LOGFILE%
echo ============================================================
echo.

echo --- Pass 1: preview to console (--dry-run, no uploads) ---
echo.
"%RCLONEPATH%" copy "%LOCAL_LOOM%" "%DRIVE_LOOM%" --update %EXCLUDES% ^
    --dry-run ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo --- Pass 2: real run (output captured by rclone to log file) ---
echo   Log: %LOGFILE%
echo   (Pass 2 is silent on console -- see the log for per-file
echo    detail. Pass 1 above showed what to expect.)
echo.
"%RCLONEPATH%" copy "%LOCAL_LOOM%" "%DRIVE_LOOM%" --update %EXCLUDES% ^
    --log-file="%LOGFILE%" ^
    --log-level INFO ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Push complete.
echo.
echo   Pass 1 (console above): what rclone planned to do.
echo   Pass 2 (silent): the real run, logged to:
echo     %LOGFILE%
echo ============================================================
pause
exit /b 0

:error
echo.
echo rclone reported an error. Check messages above
echo and the log file: %LOGFILE%
pause
exit /b 1
