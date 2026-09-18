@echo off
setlocal
REM ============================================================
REM   corpus_wrapper.template.bat
REM
REM   THE ONE PER-CORPUS ARTIFACT.
REM
REM   Copy this file into a corpus's _Tools folder, edit the
REM   CONFIGURATION block below, and run it. Everything it calls
REM   is generic: no corpus name, local path, or Drive path
REM   appears in any script under the pipeline folder.
REM
REM   One engine in the AI Methods corpus; a thin wrapper plus
REM   configuration in each corpus that uses it.
REM
REM   Usage:
REM     <this file>                  digest, check, self-check
REM     <this file> --push           also push to Drive
REM     <this file> --sync           also mirror selected AI conversations
REM     <this file> --all            everything
REM     <this file> --dry-run        show what would happen, change nothing
REM
REM   Configuration files (the selection list, project_names.tsv)
REM   are data, not code. They live beside this wrapper.
REM ============================================================

REM ---------- CONFIGURATION: edit these ----------------------

REM Where the pipeline engine lives (the folder holding
REM process_folder.py and the generic .bat wrappers).
set "PIPELINE=I:\AI\Methods\Corpus-Digester-Pipeline"

REM This corpus's root: the folder holding the four tiers.
set "CORPUS_ROOT=I:\RPG\_Design\Loom-Nick"

REM This corpus's Drive mirror, as an rclone remote path.
set "DRIVE_PATH=drive:RPG/_Design/Loom-Nick"

REM The subject: whose assertions sit at tier 0 in provenance
REM weighting. Usually the corpus owner. Leave empty to let a
REM document with exactly one non-AI speaker resolve itself.
set "SUBJECT=Nick"

REM Optional: a word list used to veto keyword rejections.
REM Leave empty to rely on corpus frequency and capitalisation.
set "DICTIONARY="

REM Optional: mirroring selected AI conversations into this
REM corpus. Leave SELLIST empty to skip the --sync step.
set "SELLIST=%~dp0loom_ai_subset.txt"
set "SRC_CLAUDE=I:\AI\Backups\Claude\Exported\2-Digested"
set "SRC_CHATGPT=I:\AI\Backups\ChatGPT\Exported\2-Digested"
set "DST_CLAUDE=%CORPUS_ROOT%\1-Raw\FromNick\Notes\AI\Claude\Conversations\Exported"
set "DST_CHATGPT=%CORPUS_ROOT%\1-Raw\FromNick\Notes\AI\ChatGPT\Conversations\Exported"

REM ---------- END CONFIGURATION ------------------------------

set "DO_PUSH="
set "DO_SYNC="
set "DRYRUN="
if /i "%~1"=="--push"    set "DO_PUSH=1"
if /i "%~1"=="--sync"    set "DO_SYNC=1"
if /i "%~1"=="--dry-run" set "DRYRUN=--dry-run"
if /i "%~1"=="--all" (
    set "DO_PUSH=1"
    set "DO_SYNC=1"
)

where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist "%PIPELINE%\process_folder.py" (
    echo ERROR: pipeline not found at:
    echo     %PIPELINE%
    echo Edit the PIPELINE line near the top of this file.
    pause
    exit /b 2
)
if not exist "%CORPUS_ROOT%\1-Raw" (
    echo ERROR: %CORPUS_ROOT% does not look like a corpus root.
    echo Expected a 1-Raw folder beneath it.
    pause
    exit /b 2
)

set "OPTS="
if not "%SUBJECT%"==""    set "OPTS=%OPTS% --subject "%SUBJECT%""
if not "%DICTIONARY%"=="" set "OPTS=%OPTS% --dictionary "%DICTIONARY%""

for %%I in ("%CORPUS_ROOT%") do set "CORPUS_NAME=%%~nxI"

echo.
echo ============================================================
echo   Corpus: %CORPUS_NAME%
echo   Root  : %CORPUS_ROOT%
echo ============================================================

REM ---------- Step 1: mirror selected AI conversations --------
if defined DO_SYNC if not "%SELLIST%"=="" (
    echo.
    echo --- Mirroring selected Claude conversations ---
    call "%PIPELINE%\sync_gdrive_corpus.bat" "%SELLIST%" "%SRC_CLAUDE%" "%DST_CLAUDE%" %DRYRUN%
    echo.
    echo --- Mirroring selected ChatGPT conversations ---
    call "%PIPELINE%\sync_gdrive_corpus.bat" "%SELLIST%" "%SRC_CHATGPT%" "%DST_CHATGPT%" %DRYRUN%
)

REM ---------- Step 2: digest ----------------------------------
echo.
echo --- Digesting 1-Raw into 2-Digested ---
%PY% "%PIPELINE%\process_folder.py" "%CORPUS_ROOT%\1-Raw" "%CORPUS_ROOT%\2-Digested" ^
    --corpus-root "%CORPUS_ROOT%" %OPTS% %DRYRUN%
if errorlevel 1 goto :error

REM ---------- Step 3: catalogue the authored tiers ------------
REM 4-Canon artifacts are never modified. Each gets a companion
REM Markdown record so it can be found.
if exist "%CORPUS_ROOT%\4-Canon" (
    echo.
    echo --- Cataloguing 4-Canon ---
    %PY% "%PIPELINE%\tier_sidecars.py" "%CORPUS_ROOT%\4-Canon" ^
        --corpus-root "%CORPUS_ROOT%" %DRYRUN%
)

REM ---------- Step 4: stale check (report only) ---------------
echo.
echo --- Checking for digested files whose source is gone ---
%PY% "%PIPELINE%\clean_stale.py" "%CORPUS_ROOT%\1-Raw" "%CORPUS_ROOT%\2-Digested"

REM ---------- Step 5: self-check ------------------------------
echo.
echo --- Pipeline self-check ---
%PY% "%PIPELINE%\pipeline_selfcheck.py" "%CORPUS_ROOT%" ^
    --report "%CORPUS_ROOT%\_selfcheck_%CORPUS_NAME%.md"

REM ---------- Step 6: push ------------------------------------
if defined DO_PUSH (
    echo.
    echo --- Pushing to Drive ---
    call "%PIPELINE%\push_gdrive_corpus.bat" "%CORPUS_ROOT%" "%DRIVE_PATH%" "%~dp0"
)

echo.
echo ============================================================
echo   %CORPUS_NAME%: done.
echo.
echo   The stale check and self-check above REPORT only. Nothing
echo   is ever deleted automatically. Deletion is yours.
echo ============================================================
pause
exit /b 0

:error
echo.
echo ============================================================
echo   The digest step failed. Check the messages above.
echo ============================================================
pause
exit /b 1
