@echo off
setlocal

REM ============================================================
REM   sync_loom.bat
REM
REM   Loom-specific launcher. Mirrors the Loom-relevant subset of
REM   the digested AI conversation exports into the Loom corpus,
REM   preserving the source split under FromNick\Notes\AI\:
REM     FromNick\Notes\AI\Claude\Conversations\Exported\
REM     FromNick\Notes\AI\ChatGPT\Conversations\Exported\
REM
REM   The "Exported" subfolder distinguishes these auto-mirrored
REM   files from sibling folders (Copied\, Output\) that hold
REM   hand-curated AI conversation extracts.
REM
REM   This .bat holds the Loom-specific paths. The engine it calls
REM   (sync_subset.py) is generic and contains no Loom knowledge.
REM   The selection list (loom_ai_subset.txt) is Loom data and
REM   lives WITH THE CORPUS, not in the tooling folder. This is the
REM   same generic-engine / site-launcher / site-data separation
REM   the rest of the pipeline already uses.
REM
REM   To extend this to another export source later (e.g. Evernote
REM   once its shape is known), copy the pattern of one SECTION
REM   block below, pointing at that source's digested tree and a
REM   destination subfolder. The engine and the per-source nature
REM   of the run do not change.
REM
REM   Usage:
REM     sync_loom.bat              mirror; report stale, keep it
REM     sync_loom.bat --prune      mirror; remove de-selected dest
REM                                folders too
REM     sync_loom.bat --dry-run    show what would happen, no writes
REM     (flags can be combined, e.g.  sync_loom.bat --prune --dry-run)
REM ============================================================

set "ENGINE=%~dp0sync_subset.py"

REM --- Selection list: Loom DATA, stored with the Loom corpus ---
set "SELLIST=I:\RPG\_Design\Loom\_Tools\loom_ai_subset.txt"

REM --- Source digested trees (the immediate subfolder that holds
REM     the per-project/topic folders is the selectable root) ---
REM The AI exports put a timestamp in the path, so the dated folder
REM changes every export cycle. Rather than hardcode it (and have to
REM edit this file after every export), we auto-discover the NEWEST
REM dated folder under each 2-Digested root.
REM
REM Why by filesystem date, not by name: the export folder names are
REM not zero-padded (e.g. 2026-05-9-15-24-00, not 2026-05-09-...), so
REM a plain alphabetical/name sort is WRONG -- "2026-05-9" would sort
REM after "2026-05-29". `dir /o-d` orders by actual modified date,
REM newest first, which is correct regardless of the name format.

set "DIG_CLAUDE=I:\AI\Backups\Claude\Exported\2-Digested"
set "DIG_CHATGPT=I:\AI\Backups\ChatGPT\Exported\2-Digested"

set "SRC_CLAUDE="
for /f "delims=" %%D in ('dir "%DIG_CLAUDE%" /ad /b /o-d 2^>nul') do (
    if not defined SRC_CLAUDE set "SRC_CLAUDE=%DIG_CLAUDE%\%%D\conversations"
)

set "SRC_CHATGPT="
for /f "delims=" %%D in ('dir "%DIG_CHATGPT%" /ad /b /o-d 2^>nul') do (
    if not defined SRC_CHATGPT set "SRC_CHATGPT=%DIG_CHATGPT%\%%D\conversations"
)

if not defined SRC_CLAUDE (
    echo ERROR: no dated export folder found under:
    echo     %DIG_CLAUDE%
    echo Has the Claude export been digested yet?
    pause
    exit /b 2
)
if not defined SRC_CHATGPT (
    echo ERROR: no dated export folder found under:
    echo     %DIG_CHATGPT%
    echo Has the ChatGPT export been digested yet?
    pause
    exit /b 2
)
if not exist "%SRC_CLAUDE%" (
    echo ERROR: newest Claude dated folder has no 'conversations' subfolder:
    echo     %SRC_CLAUDE%
    pause
    exit /b 2
)
if not exist "%SRC_CHATGPT%" (
    echo ERROR: newest ChatGPT dated folder has no 'conversations' subfolder:
    echo     %SRC_CHATGPT%
    pause
    exit /b 2
)

REM --- Destinations: source split preserved under
REM     FromNick\Notes\AI\<source>\Conversations\Exported\ ---
set "DST_CLAUDE=I:\RPG\_Design\Loom\2-Digested\FromNick\Notes\AI\Claude\Conversations\Exported"
set "DST_CHATGPT=I:\RPG\_Design\Loom\2-Digested\FromNick\Notes\AI\ChatGPT\Conversations\Exported"

REM Pass through any flags (--prune, --dry-run, --verbose) to both runs.
set "FLAGS=%*"

REM ---------- Locate Python ----------
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist "%SELLIST%" (
    echo ERROR: selection list not found:
    echo     %SELLIST%
    echo This file is Loom data and should live with the corpus.
    pause
    exit /b 2
)

echo.
echo ============================================================
echo   Loom AI-export subset mirror
echo ============================================================
echo   List   : %SELLIST%
echo   Flags  : %FLAGS%
echo   Claude : %SRC_CLAUDE%
echo   ChatGPT: %SRC_CHATGPT%
echo ============================================================

REM ===== SECTION: Claude =====
echo.
echo --- Claude export -^> FromNick\Notes\AI\Claude\Conversations\Exported ---
%PY% "%ENGINE%" "%SRC_CLAUDE%" "%DST_CLAUDE%" --list "%SELLIST%" %FLAGS%
set "RC_CLAUDE=%errorlevel%"
if "%RC_CLAUDE%"=="2" goto :hard_error

REM ===== SECTION: ChatGPT =====
echo.
echo --- ChatGPT export -^> FromNick\Notes\AI\ChatGPT\Conversations\Exported ---
%PY% "%ENGINE%" "%SRC_CHATGPT%" "%DST_CHATGPT%" --list "%SELLIST%" %FLAGS%
set "RC_CHATGPT=%errorlevel%"
if "%RC_CHATGPT%"=="2" goto :hard_error

echo.
echo ============================================================
if "%RC_CLAUDE%"=="0" if "%RC_CHATGPT%"=="0" (
    echo   Done. Both sources mirrored cleanly.
) else (
    echo   Done, with items needing attention above
    echo   ^(missing selection entries or de-selected dest folders^).
    echo   This is informational, not a failure.
)
echo ============================================================
pause
exit /b 0

:hard_error
echo.
echo ============================================================
echo   A run hit a path/usage error ^(exit 2^). Nothing was
echo   mirrored for that source. Check the messages above.
echo ============================================================
pause
exit /b 2
