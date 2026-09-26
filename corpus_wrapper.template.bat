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
REM     <this file> --audit          also write a rejected-keyword report
REM
REM   Configuration files (the selection lists, project_names.tsv)
REM   are data, not code. They live beside this wrapper, and a
REM   copy found here overrides the pipeline's own.
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

REM Optional: this corpus's own glossaries -- invented terms, place names,
REM character names. Anything listed there is protected from the keyword
REM artifact filter. The pipeline's own lexicon folder is used automatically
REM in addition to this one.
set "GLOSSARIES=%~dp0glossaries"

REM Optional: a single standalone word list, if you have one.
set "DICTIONARY="

REM Write a rejected-keyword report on every run. The keyword
REM filter discards strings it judges to be conversion debris,
REM and the looser half of that filter can in principle discard
REM a real word. The report costs nothing -- it records what the
REM metadata pass already decided -- and it is the only way to
REM find a false positive. On by default for that reason; set
REM empty to turn it off.
set "AUDIT=1"

REM Set to 1 to recover text from scanned PDFs. Needs ocrmypdf
REM on PATH or in OCRMYPDF_EXE; without it the step is skipped
REM with a message. Nothing in 1-Raw is modified -- the text is
REM cached under _ocr-cache at the corpus root, keyed on content
REM hash, so a re-digest costs nothing. Leave empty for a corpus
REM with no scanned material.
set "OCR="

REM Set to 1 to skip extracting images from PDFs. For scanned
REM books every page image IS the page, so extraction writes the
REM whole document out again as loose files for no search value.
REM Set it for a library of scans; leave empty otherwise.
set "NO_PDF_IMAGES="

REM Set to 1 if this corpus is an EXPORT ARCHIVE -- a tree that
REM exists only so other corpora can select project folders out
REM of it, and that is never uploaded or searched itself.
REM
REM It then converts, groups and names, and stops. Keywords, the
REM NotebookLM sidecars and _index.json are all skipped, because
REM the corpus that receives the selection re-digests what it
REM takes and computes its own. Keywords especially: TF-IDF is
REM corpus-relative, so the archive's are the wrong numbers AND
REM the most expensive pass in the run.
REM
REM Leave empty for a normal corpus.
set "ARCHIVE_ONLY="

REM Optional: mirroring selected AI conversations into this
REM corpus from a central digested export archive.
REM
REM ONE LIST PER SOURCE. The two exports name their project
REM folders differently -- Claude's are
REM `project_<short-uuid>__<slug>`, ChatGPT's are whatever
REM project_names.tsv renamed them to -- so a shared list would
REM report each source's entries as missing from the other.
REM Leave a list empty to skip that source.
REM
REM Run subset_inventory.py against a source to see what is
REM there to select and what nothing selects yet.
set "SELLIST_CLAUDE=%~dp0subset_claude.txt"
set "SELLIST_CHATGPT=%~dp0subset_chatgpt.txt"
set "SRC_CLAUDE=I:\AI\Backups\Claude\Exported\2-Digested\conversations"
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
set "DO_AUDIT="
if /i "%~1"=="--audit" set "DO_AUDIT=1"
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
if not "%GLOSSARIES%"=="" if exist "%GLOSSARIES%" set "OPTS=%OPTS% --lexicon "%GLOSSARIES%""
if defined AUDIT   set "DO_AUDIT=1"
if defined DO_AUDIT set "OPTS=%OPTS% --report-artifacts "%CORPUS_ROOT%\_rejected-keywords.md""
if defined ARCHIVE_ONLY set "OPTS=%OPTS% --archive-only"
if defined OCR set "OPTS=%OPTS% --ocr"
if defined NO_PDF_IMAGES set "OPTS=%OPTS% --no-pdf-images"

REM A project-name map beside this wrapper overrides the pipeline's
REM own copy. Without one, process_folder.py falls back to
REM project_names.tsv next to itself -- which is usually what you
REM want, since ChatGPT project ids are account-level rather than
REM per-corpus. Pass the override only when the file is really there,
REM so a missing per-corpus copy falls through instead of pointing
REM the pipeline at a path that does not exist.
if exist "%~dp0project_names.tsv" set "OPTS=%OPTS% --rename-tsv "%~dp0project_names.tsv""

for %%I in ("%CORPUS_ROOT%") do set "CORPUS_NAME=%%~nxI"

echo.
echo ============================================================
echo   Corpus: %CORPUS_NAME%
echo   Root  : %CORPUS_ROOT%
echo ============================================================

REM ---------- Step 1: mirror selected AI conversations --------
if defined DO_SYNC (
    if not "%SELLIST_CLAUDE%"=="" if exist "%SELLIST_CLAUDE%" (
        echo.
        echo --- Mirroring selected Claude conversations ---
        call "%PIPELINE%\sync_gdrive_corpus.bat" "%SELLIST_CLAUDE%" "%SRC_CLAUDE%" "%DST_CLAUDE%" %DRYRUN%
    )
    if not "%SELLIST_CHATGPT%"=="" if exist "%SELLIST_CHATGPT%" (
        echo.
        echo --- Mirroring selected ChatGPT conversations ---
        call "%PIPELINE%\sync_gdrive_corpus.bat" "%SELLIST_CHATGPT%" "%SRC_CHATGPT%" "%DST_CHATGPT%" %DRYRUN%
    )
)

REM ---------- Step 2: digest ----------------------------------
echo.
echo --- Digesting 1-Raw into 2-Digested ---
%PY% "%PIPELINE%\process_folder.py" "%CORPUS_ROOT%\1-Raw" "%CORPUS_ROOT%\2-Digested" ^
    --corpus-root "%CORPUS_ROOT%" %OPTS% %DRYRUN%
if errorlevel 1 goto :error

REM ---------- Step 3a: stamp 3-Reporting ----------------------
REM Reports from the write-report skill arrive already stamped.
REM Hand-written or pasted files do not, and without a title,
REM date, keywords and source line, search cannot see them.
REM Only files missing a field are touched.
if not defined ARCHIVE_ONLY if exist "%CORPUS_ROOT%\3-Reporting" (
    echo.
    echo --- Stamping 3-Reporting ---
    %PY% "%PIPELINE%\stamp_tier.py" "%CORPUS_ROOT%\3-Reporting" ^
        --corpus-root "%CORPUS_ROOT%" %DRYRUN%
)

REM ---------- Step 3b: catalogue the authored tiers ------------
REM 4-Canon artifacts are never modified. Each gets a companion
REM Markdown record so it can be found. An export archive has no
REM authored tiers, so this is skipped there.
if not defined ARCHIVE_ONLY if exist "%CORPUS_ROOT%\4-Canon" (
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
REM Skipped for an export archive: the checks that matter there
REM (frontmatter, the index) are for output this run deliberately
REM did not produce, so they would report the intended state as a
REM fault. Completeness still holds and is checked where the
REM material lands.
if not defined ARCHIVE_ONLY (
echo.
echo --- Pipeline self-check ---
%PY% "%PIPELINE%\pipeline_selfcheck.py" "%CORPUS_ROOT%" ^
    --report "%CORPUS_ROOT%\_selfcheck_%CORPUS_NAME%.md"
)

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
if defined DO_AUDIT (
    echo.
    echo   Rejected keywords: %CORPUS_ROOT%\_rejected-keywords.md
    echo   Read it. Anything in there that is a real word is a false
    echo   positive, and belongs in your glossaries folder.
)
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
