@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM   merge_loom_to_drive.bat
REM
REM   ONE-TIME-USE: reconciles local Loom with Drive Loom using
REM   a three-pass procedure:
REM
REM     Pass 1: dry-run with default size+modtime comparison
REM     Pass 2: dry-run with --checksum (catches content differences
REM             that size+modtime missed)
REM     Pass 3: real run, with --update so newer Drive files win,
REM             logged to merge log file
REM
REM   This is destructive in pass 3 (uploads files to Drive). The
REM   non-destructive guarantee still holds: nothing in Drive is
REM   ever deleted by this script. But files in Drive that exist
REM   locally with the same name will be overwritten if the local
REM   copy is newer (--update flag).
REM
REM   After the initial merge is complete, use push_loom.bat for
REM   ongoing pushes (same pass-3 logic, no prompts).
REM ============================================================

set "LOCAL_LOOM=I:\RPG\_Design\Loom"
REM Drive path mirrors the local nested structure under My Drive:
REM     My Drive\RPG\_Design\Loom
REM (NOT the top-level My Drive\Loom -- that was a misconfiguration
REM created on the first merge run before this was caught. If a
REM stale top-level Loom\ still exists on Drive, delete it manually.)
set "DRIVE_LOOM=drive:RPG/_Design/Loom"
set "LOGFILE=%~dp0loom_merge_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"
set "EXCLUDES=--exclude Thumbs.db --exclude desktop.ini --exclude .DS_Store"

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
    echo ERROR: rclone has no remote named "drive".
    echo Run: rclone config
    echo and set up a Google Drive remote named "drive".
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
echo   Loom merge: local -^> Drive
echo ============================================================
echo   Local : %LOCAL_LOOM%
echo   Drive : %DRIVE_LOOM%
echo   Log   : %LOGFILE%
echo ============================================================
echo.

REM ---------- Pass 1: default dry-run ----------
echo --- Pass 1: dry-run, default comparison (size + modtime) ---
echo.
echo This pass shows what rclone would upload using the default
echo size+modtime check. Read the output and look for surprises.
echo.
pause
echo.
"%RCLONEPATH%" copy "%LOCAL_LOOM%" "%DRIVE_LOOM%" --update --dry-run %EXCLUDES% ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Pass 1 complete. Review the file list above.
echo ============================================================
echo.
set /p CONTINUE="Continue to Pass 2 (--checksum dry-run)? [y/N]: "
if /i not "%CONTINUE%"=="y" goto :aborted

REM ---------- Pass 2: dry-run with --checksum ----------
echo.
echo --- Pass 2: dry-run, --checksum (hash comparison) ---
echo.
echo This pass uses content hashing instead of size+modtime. If
echo the list of "would upload" files is significantly larger
echo than Pass 1, that means some files match in size+modtime
echo but differ in content. Those are the surprises worth knowing
echo about before the real run.
echo.
pause
echo.
"%RCLONEPATH%" copy "%LOCAL_LOOM%" "%DRIVE_LOOM%" --update --dry-run --checksum %EXCLUDES% ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Pass 2 complete.
echo ============================================================
echo.
set /p CONTINUE="Continue to Pass 3 (REAL UPLOAD)? [y/N]: "
if /i not "%CONTINUE%"=="y" goto :aborted

REM ---------- Pass 3: real run, logged ----------
echo.
echo --- Pass 3: REAL UPLOAD, with logging ---
echo.
echo Uploading. Files newer in Drive than local will be skipped
echo (--update). Nothing in Drive will be deleted. Logging to:
echo   %LOGFILE%
echo.
echo Pass 3 is silent on console -- see the log for per-file
echo detail. Passes 1 and 2 above showed what to expect.
echo.
"%RCLONEPATH%" copy "%LOCAL_LOOM%" "%DRIVE_LOOM%" --update %EXCLUDES% ^
    --log-file="%LOGFILE%" ^
    --log-level INFO ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Merge complete.
echo ============================================================
echo   Drive Loom now contains everything local Loom had, plus
echo   anything Drive already had that local did not.
echo.
echo   Log written to: %LOGFILE%
echo.
echo   Use push_loom.bat for future ongoing pushes.
echo ============================================================
pause
exit /b 0

:aborted
echo.
echo Merge aborted by user. Nothing was uploaded.
echo Partial log (if any) at: %LOGFILE%
pause
exit /b 0

:error
echo.
echo ============================================================
echo   rclone reported an error. Check messages above
echo   and the log file: %LOGFILE%
echo ============================================================
pause
exit /b 1
