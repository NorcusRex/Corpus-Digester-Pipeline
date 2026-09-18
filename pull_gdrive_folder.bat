@echo off
setlocal
REM ============================================================
REM   pull_gdrive_folder.bat
REM
REM   Pull a shared Drive folder to a local directory, exporting
REM   Google Docs as .docx on the way.
REM
REM   Note it is *folder*, not *corpus*: pulling from a shared
REM   Drive folder is not specific to any one collaborator or to
REM   a corpus at all. The destination often sits inside 1-Raw,
REM   but nothing here requires that.
REM
REM   Usage:
REM     pull_gdrive_folder.bat <DRIVE_FOLDER_ID> <LOCAL_DEST> [LOG_DIR]
REM
REM   Example:
REM     pull_gdrive_folder.bat 1mAK0NwcWB7rVgtPdpLO8Abl2kgDZH3Wd ^
REM         "I:\RPG\_Design\Loom-Nick\1-Raw\FromMatt\Drafts"
REM
REM   The folder id is the last path segment of the Drive URL
REM   when the folder is open in a browser.
REM ============================================================

set "FOLDER_ID=%~1"
set "LOCAL_DEST=%~2"
set "LOG_DIR=%~3"

if "%FOLDER_ID%"=="" goto :usage
if "%LOCAL_DEST%"=="" goto :usage
if "%LOG_DIR%"=="" set "LOG_DIR=%~dp0"

call "%~dp0_rclone_common.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

if not exist "%LOCAL_DEST%" mkdir "%LOCAL_DEST%"

for %%I in ("%LOCAL_DEST%") do set "DEST_NAME=%%~nxI"
set "LOGFILE=%LOG_DIR%pull_%DEST_NAME%_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

echo.
echo ============================================================
echo   Pulling a shared Drive folder (Google Docs -^> .docx)
echo ============================================================
echo   Drive : (shared folder, id %FOLDER_ID%)
echo   Local : %LOCAL_DEST%
echo   Log   : %LOGFILE%
echo ============================================================
echo.
echo --- Pass 1: preview to console (--dry-run, no file changes) ---
echo.
"%RCLONEPATH%" copy "drive:" "%LOCAL_DEST%" ^
    --drive-root-folder-id %FOLDER_ID% ^
    --drive-export-formats docx ^
    --ignore-errors ^
    --max-depth 6 ^
    --retries 1 ^
    --dry-run ^
    --stats-one-line --stats 5s

echo.
echo --- Pass 2: real run (logged) ---
echo   Log: %LOGFILE%
echo.
"%RCLONEPATH%" copy "drive:" "%LOCAL_DEST%" ^
    --drive-root-folder-id %FOLDER_ID% ^
    --drive-export-formats docx ^
    --ignore-errors ^
    --max-depth 6 ^
    --retries 1 ^
    --log-file="%LOGFILE%" ^
    --log-level INFO ^
    --stats-one-line --stats 5s

echo.
echo ============================================================
echo   Pull complete. Log: %LOGFILE%
echo ============================================================
pause
exit /b 0

:usage
echo Usage: pull_gdrive_folder.bat ^<DRIVE_FOLDER_ID^> ^<LOCAL_DEST^> [LOG_DIR]
echo.
echo   DRIVE_FOLDER_ID  Last segment of the folder's Drive URL
echo   LOCAL_DEST       Local directory to pull into (created if absent)
echo   LOG_DIR          Where to write the log. Default: beside this script
pause
exit /b 2
