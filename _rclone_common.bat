@echo off
REM ============================================================
REM   _rclone_common.bat
REM
REM   Shared preamble for the generic rclone wrappers. Not run
REM   directly -- the wrappers CALL it.
REM
REM   Resolves rclone and checks the "drive:" remote exists, so
REM   the same two checks are not copied into four files.
REM
REM   rclone.exe is found in this order:
REM     1. the RCLONE_EXE environment variable
REM     2. rclone.exe on PATH
REM     3. a default install location
REM
REM   No corpus name, local path, or Drive path appears here or
REM   in any generic script. Those arrive as parameters.
REM ============================================================

if defined RCLONE_EXE (
    if exist "%RCLONE_EXE%" (
        set "RCLONEPATH=%RCLONE_EXE%"
        goto :have_rclone
    )
    echo ERROR: RCLONE_EXE is set but does not exist:
    echo     %RCLONE_EXE%
    exit /b 1
)

where rclone.exe >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%P in ('where rclone.exe') do (
        if not defined RCLONEPATH set "RCLONEPATH=%%P"
    )
    goto :have_rclone
)

set "RCLONEPATH=I:\rclone-v1.74.1-windows-amd64\rclone.exe"
if exist "%RCLONEPATH%" goto :have_rclone

echo ERROR: rclone.exe not found.
echo.
echo Set the RCLONE_EXE environment variable to its full path, or
echo put rclone.exe on your PATH. For example:
echo     set RCLONE_EXE=I:\rclone-v1.74.1-windows-amd64\rclone.exe
exit /b 1

:have_rclone
"%RCLONEPATH%" listremotes | findstr /B /C:"drive:" >nul
if errorlevel 1 (
    echo ERROR: rclone has no remote named "drive". Run: rclone config
    echo and set up a Google Drive remote named "drive".
    exit /b 1
)
exit /b 0
