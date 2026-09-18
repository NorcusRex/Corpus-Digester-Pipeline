@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM   Archive digestion pipeline launcher
REM
REM   Usage:
REM     1. Edit INPUT_DIR and OUTPUT_DIR below to your folders
REM     2. Save the file
REM     3. Double-click to run, OR drag a folder onto the .bat,
REM        OR call: process_folder.bat "C:\src" "C:\dst"
REM ============================================================

REM ===== EDIT THESE TWO PATHS =====
set "INPUT_DIR=C:\Users\YourName\Documents\Archive\source"
set "OUTPUT_DIR=C:\Users\YourName\Documents\Archive\digested"
REM ================================

REM Optional command-line override (drag a folder here, or pass two paths).
if not "%~1"=="" set "INPUT_DIR=%~1"
if not "%~2"=="" set "OUTPUT_DIR=%~2"

REM Run from the .bat's own directory so the .py files are findable.
cd /d "%~dp0"

echo.
echo ============================================================
echo   Archive digestion pipeline
echo ============================================================
echo   Source : "%INPUT_DIR%"
echo   Output : "%OUTPUT_DIR%"
echo ============================================================
echo.

REM ---------- Locate Python ----------
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python is not installed or not on PATH.
        echo Install Python 3 from https://www.python.org/downloads/
        echo and re-run this script.
        goto :error
    )
    set "PY=python"
)

REM ---------- Check / install pypdf for PDF support ----------
REM The [image] extra pulls in Pillow, which pypdf needs to extract embedded
REM images from many PDFs. Without it, image-bearing PDFs fail to convert.
%PY% -c "import pypdf, PIL" 2>nul
if errorlevel 1 (
    echo Installing pypdf with image support...
    %PY% -m pip install --quiet "pypdf[image]"
    if errorlevel 1 (
        echo.
        echo WARNING: could not install pypdf[image] automatically.
        echo PDFs with embedded images may fail. To install manually, run:
        echo     %PY% -m pip install "pypdf[image]"
        echo.
    )
)

REM ---------- Verify input directory exists ----------
if not exist "%INPUT_DIR%" (
    echo ERROR: input directory does not exist:
    echo     "%INPUT_DIR%"
    echo.
    echo Edit the INPUT_DIR line at the top of this .bat file
    echo or pass a folder path as the first argument.
    goto :error
)

REM ---------- Run the orchestrator ----------
%PY% "%~dp0process_folder.py" "%INPUT_DIR%" "%OUTPUT_DIR%" %3 %4 %5 %6 %7 %8 %9
set "RESULT=%errorlevel%"

echo.
if "%RESULT%"=="0" (
    echo Done. Output is at:
    echo     "%OUTPUT_DIR%"
) else (
    echo Finished with errors. Check the messages above.
)
echo.
pause
exit /b %RESULT%

:error
echo.
pause
exit /b 1
