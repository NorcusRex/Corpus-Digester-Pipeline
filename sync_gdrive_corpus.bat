@echo off
setlocal
REM ============================================================
REM   sync_gdrive_corpus.bat
REM
REM   Mirror a selected subset of digested AI conversations into
REM   a corpus. The selection list names which conversations
REM   belong to this corpus; everything else is left behind.
REM
REM   Each source is a digested export tree holding dated folders.
REM   The NEWEST dated folder is used, and its "conversations"
REM   subfolder is the actual source.
REM
REM   Usage:
REM     sync_gdrive_corpus.bat <SELECTION_LIST> <SRC_ROOT> <DEST> [FLAGS]
REM
REM   Example:
REM     sync_gdrive_corpus.bat ^
REM        "I:\RPG\_Design\Loom-Nick\_Tools\loom_ai_subset.txt" ^
REM        "I:\AI\Backups\Claude\Exported\2-Digested" ^
REM        "I:\RPG\_Design\Loom-Nick\1-Raw\FromNick\Notes\AI\Claude\Conversations\Exported"
REM
REM   Call it once per source. A corpus pulling from both Claude
REM   and ChatGPT calls it twice, which is what the per-corpus
REM   marshaling wrapper does.
REM
REM   FLAGS are passed through to sync_subset.py. Useful ones:
REM     --dry-run   show what would change, write nothing
REM     --prune     remove destination folders no longer selected
REM     --verbose   per-item detail
REM ============================================================

set "ENGINE=%~dp0sync_subset.py"
set "SELLIST=%~1"
set "SRC_ROOT=%~2"
set "DEST=%~3"

if "%SELLIST%"=="" goto :usage
if "%SRC_ROOT%"=="" goto :usage
if "%DEST%"=="" goto :usage

REM Everything after the third argument is passed to the engine.
set "FLAGS="
shift
shift
shift
:collect
if "%~1"=="" goto :collected
set "FLAGS=%FLAGS% %~1"
shift
goto :collect
:collected

where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist "%ENGINE%" (
    echo ERROR: sync_subset.py not found beside this script:
    echo     %ENGINE%
    pause
    exit /b 2
)
if not exist "%SELLIST%" (
    echo ERROR: selection list not found:
    echo     %SELLIST%
    echo.
    echo This file is per-corpus configuration. It lives beside the
    echo corpus's marshaling wrapper, in its _Tools folder.
    pause
    exit /b 2
)
if not exist "%SRC_ROOT%" (
    echo ERROR: source root not found:
    echo     %SRC_ROOT%
    pause
    exit /b 2
)

REM Newest dated folder under the source root.
set "SRC="
for /f "delims=" %%D in ('dir "%SRC_ROOT%" /ad /b /o-d 2^>nul') do (
    if not defined SRC set "SRC=%SRC_ROOT%\%%D\conversations"
)
if not defined SRC (
    echo ERROR: no dated export folder found under:
    echo     %SRC_ROOT%
    echo Has that export been digested yet?
    pause
    exit /b 2
)
if not exist "%SRC%" (
    echo ERROR: newest dated folder has no 'conversations' subfolder:
    echo     %SRC%
    pause
    exit /b 2
)

echo.
echo ============================================================
echo   Mirroring selected conversations
echo ============================================================
echo   List  : %SELLIST%
echo   Source: %SRC%
echo   Dest  : %DEST%
if not "%FLAGS%"=="" echo   Flags :%FLAGS%
echo ============================================================
echo.

%PY% "%ENGINE%" "%SRC%" "%DEST%" --list "%SELLIST%"%FLAGS%
set "RC=%errorlevel%"

if "%RC%"=="2" (
    echo.
    echo ============================================================
    echo   A path or usage error ^(exit 2^). Nothing was mirrored.
    echo ============================================================
    exit /b 2
)
if "%RC%"=="0" (
    echo.
    echo   Done. Source mirrored cleanly.
) else (
    echo.
    echo   Done, with items needing attention above
    echo   ^(missing selection entries or de-selected dest folders^).
    echo   This is informational, not a failure.
)
exit /b %RC%

:usage
echo Usage: sync_gdrive_corpus.bat ^<SELECTION_LIST^> ^<SRC_ROOT^> ^<DEST^> [FLAGS]
echo.
echo   SELECTION_LIST  Per-corpus list of conversations to mirror
echo   SRC_ROOT        Digested export tree holding dated folders
echo   DEST            Where to mirror the selected conversations
echo   FLAGS           Passed to sync_subset.py (--dry-run, --prune, --verbose)
exit /b 2
