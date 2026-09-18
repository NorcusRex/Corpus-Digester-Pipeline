@echo off
setlocal
REM ============================================================
REM   push_gdrive_corpus.bat
REM
REM   Ongoing use: push a corpus's local tree to its Drive mirror.
REM   Local is authoritative; the mirror follows.
REM
REM   Usage:
REM     push_gdrive_corpus.bat <LOCAL_ROOT> <DRIVE_PATH> [LOG_DIR]
REM
REM   Example:
REM     push_gdrive_corpus.bat "I:\RPG\_Design\Loom-Nick" ^
REM                            "drive:RPG/_Design/Loom-Nick"
REM
REM   For a FIRST reconciliation against a Drive folder that
REM   already holds content, use merge_corpus_local_to_drive.bat
REM   instead: it makes several dry-run passes first.
REM
REM   rclone is located by _rclone_common.bat. Set RCLONE_EXE if
REM   it is not on your PATH.
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
set "LOGFILE=%LOG_DIR%push_%CORPUS_NAME%_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

echo.
echo ============================================================
echo   Pushing local corpus to Drive
echo ============================================================
echo   Corpus: %CORPUS_NAME%
echo   Local : %LOCAL_ROOT%
echo   Drive : %DRIVE_PATH%
echo   Log   : %LOGFILE%
echo ============================================================
echo.
echo --- Pass 1: preview to console (--dry-run, no uploads) ---
echo.
"%RCLONEPATH%" copy "%LOCAL_ROOT%" "%DRIVE_PATH%" --update %EXCLUDES% ^
    --dry-run ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo --- Pass 2: real run (output captured by rclone to log file) ---
echo   Log: %LOGFILE%
echo   (Pass 2 is silent on console -- see the log for per-file
echo    detail. Pass 1 above showed what to expect.)
echo.
"%RCLONEPATH%" copy "%LOCAL_ROOT%" "%DRIVE_PATH%" --update %EXCLUDES% ^
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

:usage
echo Usage: push_gdrive_corpus.bat ^<LOCAL_ROOT^> ^<DRIVE_PATH^> [LOG_DIR]
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
