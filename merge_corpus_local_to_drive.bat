@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM   merge_corpus_local_to_drive.bat
REM
REM   FIRST reconciliation of a local corpus against a Drive
REM   folder that already holds content. Makes two dry-run passes
REM   before anything is uploaded, so you see what a size+modtime
REM   comparison would do and what a checksum comparison would do
REM   before committing to either.
REM
REM   For routine ongoing pushes use push_gdrive_corpus.bat, which
REM   is a single preview pass and a real run.
REM
REM   Usage:
REM     merge_corpus_local_to_drive.bat <LOCAL_ROOT> <DRIVE_PATH> [LOG_DIR]
REM
REM   Example:
REM     merge_corpus_local_to_drive.bat "I:\RPG\_Design\Loom-Nick" ^
REM                                     "drive:RPG/_Design/Loom-Nick"
REM
REM   Nothing on Drive is deleted. This only adds and updates.
REM ============================================================

set "LOCAL_ROOT=%~1"
set "DRIVE_PATH=%~2"
set "LOG_DIR=%~3"

if "%LOCAL_ROOT%"=="" goto :usage
if "%DRIVE_PATH%"=="" goto :usage
if "%LOG_DIR%"=="" set "LOG_DIR=%~dp0"

call "%~dp0_rclone_common.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

if not exist "%LOCAL_ROOT%" (
    echo ERROR: local source does not exist: %LOCAL_ROOT%
    pause
    exit /b 1
)

for %%I in ("%LOCAL_ROOT%") do set "CORPUS_NAME=%%~nxI"
set "EXCLUDES=--exclude Thumbs.db --exclude desktop.ini --exclude .DS_Store"
set "LOGFILE=%LOG_DIR%merge_%CORPUS_NAME%_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

echo.
echo ============================================================
echo   Corpus merge: local -^> Drive
echo ============================================================
echo   Corpus: %CORPUS_NAME%
echo   Local : %LOCAL_ROOT%
echo   Drive : %DRIVE_PATH%
echo   Log   : %LOGFILE%
echo ============================================================
echo.
echo --- Pass 1: dry-run, default comparison (size + modtime) ---
echo.
echo This pass shows what rclone would upload using the default
echo size-and-modification-time comparison. A file whose timestamp
echo drifted will appear here even if its contents match.
echo.
"%RCLONEPATH%" copy "%LOCAL_ROOT%" "%DRIVE_PATH%" --update %EXCLUDES% ^
    --dry-run ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo --- Pass 2: dry-run, checksum comparison ---
echo.
echo This pass compares contents rather than timestamps. Anything
echo listed here genuinely differs. If Pass 2 is much shorter than
echo Pass 1, the difference was timestamps, not content.
echo.
"%RCLONEPATH%" copy "%LOCAL_ROOT%" "%DRIVE_PATH%" --checksum %EXCLUDES% ^
    --dry-run ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Both previews are complete. Nothing has been uploaded.
echo ============================================================
echo.
echo   Review the two passes above. Pass 2 is the honest list of
echo   what actually differs.
echo.
set /p CONFIRM="Proceed with the real upload? [y/N]: "
if /i not "%CONFIRM%"=="y" (
    echo.
    echo Aborted. Nothing was uploaded.
    pause
    exit /b 0
)

echo.
echo --- Pass 3: real run, checksum comparison (logged) ---
echo   Log: %LOGFILE%
echo.
"%RCLONEPATH%" copy "%LOCAL_ROOT%" "%DRIVE_PATH%" --checksum %EXCLUDES% ^
    --log-file="%LOGFILE%" ^
    --log-level INFO ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Merge complete.
echo.
echo   Drive now holds everything local had, plus whatever was
echo   already there. Nothing was deleted.
echo.
echo   Use push_gdrive_corpus.bat for ongoing pushes from here.
echo ============================================================
pause
exit /b 0

:usage
echo Usage: merge_corpus_local_to_drive.bat ^<LOCAL_ROOT^> ^<DRIVE_PATH^> [LOG_DIR]
echo.
echo   LOCAL_ROOT  Corpus root on disk, holding the four tiers
echo   DRIVE_PATH  rclone remote path, e.g. drive:RPG/_Design/Loom-Nick
echo   LOG_DIR     Where to write the log. Default: beside this script
pause
exit /b 2

:error
echo.
echo rclone reported an error. Check messages above
echo and the log file: %LOGFILE%
pause
exit /b 1
