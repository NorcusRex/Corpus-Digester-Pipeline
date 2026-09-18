@echo off
setlocal

REM ============================================================
REM   pull_matt.bat
REM
REM   Pulls Matt's files from drive:LOOM-Matt into the local
REM   pipeline staging folder, converting native Google Docs
REM   to .docx during the copy.
REM
REM   The --drive-export-formats docx flag is the important
REM   part: when rclone encounters a native Google Doc (which
REM   on its own is just a cloud pointer with no real file
REM   content), it asks Google to export it as a .docx and
REM   saves THAT. Real files Matt may have placed in the folder
REM   (PDF, xlsx, an already-exported .docx) are copied as-is.
REM
REM   This reproduces, as a single scriptable command, what a
REM   manual "Download folder" from the Drive web UI does.
REM
REM   Non-destructive: this is rclone COPY, not SYNC. Files
REM   deleted from Drive remain in the local folder until you
REM   remove them by hand. That is intentional -- it protects
REM   against the accidental-deletion failure mode.
REM
REM   Run before digest_all.bat to refresh Matt's content.
REM ============================================================

REM --- IMPORTANT: why this uses a folder ID, not a name ---
REM The LOOM-Matt folder is SHARED WITH YOU by another account
REM (owner: listonotsil@gmail.com). It is NOT in your My Drive --
REM it lives in "Shared with me". rclone's drive: remote only
REM searches your own My Drive tree by default, so "drive:LOOM-Matt"
REM fails with "directory not found" even though you can see the
REM folder fine in the Drive web UI.
REM
REM Addressing the folder by its immutable ID via
REM --drive-root-folder-id sidesteps the My-Drive-vs-Shared-with-me
REM distinction entirely: an ID resolves regardless of who owns the
REM folder or where it lives, and it also survives the folder being
REM renamed. If the folder is ever re-shared and gets a new ID, get
REM the new ID from the Drive URL (the long string after /folders/)
REM and update MATT_FOLDER_ID below.
set "MATT_FOLDER_ID=1mAK0NwcWB7rVgtPdpLO8Abl2kgDZH3Wd"
set "LOCAL_MATT=I:\RPG\_Design\Loom\1-Raw\FromMatt\Drafts"

REM Log file for this run. Date-stamped (YYYY-MM-DD); same-day re-runs
REM overwrite the same file. Written by rclone itself via --log-file, so
REM it appears the moment rclone starts and persists even if rclone
REM errors mid-run. NOTE: if a sanity check below fails (no rclone, no
REM remote, no local path) the script exits BEFORE invoking rclone, and
REM no log file is created -- those failures are loud on console and
REM there is nothing to log anyway.
set "LOGFILE=%~dp0pull_matt_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

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
    echo ERROR: rclone has no remote named "drive". Run: rclone config
    pause
    exit /b 1
)

REM Make sure local destination exists.
if not exist "%LOCAL_MATT%" mkdir "%LOCAL_MATT%"

echo.
echo ============================================================
echo   Pulling Matt from Drive (Google Docs -^> .docx)
echo ============================================================
echo   Drive : (shared folder, id %MATT_FOLDER_ID%)
echo   Local : %LOCAL_MATT%
echo   Log   : %LOGFILE%
echo ============================================================
echo.

REM --drive-root-folder-id : make the remote's root BE the shared
REM   LOOM-Matt folder, addressed by ID. The source path is then
REM   just "drive:" (that root). This ALONE is the correct and
REM   sufficient way to reach a shared folder by ID -- it resolves
REM   regardless of owner or My-Drive-vs-Shared-with-me.
REM
REM   Do NOT add --drive-shared-with-me here. It does not reinforce
REM   the root-folder-id; it OVERRIDES the scoping by switching the
REM   remote's whole view to your entire "Shared with me" collection
REM   (every folder anyone has ever shared with you, going back
REM   years). With it, this script pulled dozens of unrelated
REM   strangers' folders and a self-nesting tree. Without it, the
REM   root-folder-id cleanly scopes to just LOOM-Matt's contents.
REM --drive-export-formats docx : native Google Docs are exported
REM   as .docx. Real files pass through untouched.
REM --ignore-errors : continue past per-file errors rather than
REM   aborting and exiting non-zero. Matt's LOOM-Matt folder
REM   contains "Drafts" shortcuts that point at targets rclone
REM   cannot read; without this flag, those dangling-shortcut
REM   errors abort the run even though the rest of the pull
REM   succeeded. With this flag, the errors still appear in the
REM   log (correctly -- they ARE a real problem upstream), but
REM   they no longer abort.
REM
REM --max-depth 6 : hard limit on recursion depth. CRITICAL.
REM   At least one Drafts shortcut points back at its own
REM   ancestor, creating a cycle: rclone follows the shortcut,
REM   finds the same folder it just came from, recurses again,
REM   and so on forever. Earlier runs showed paths nested 12+
REM   levels deep:
REM     Guide 1/Drafts/Guide 1/Drafts/Guide 1/Drafts/...
REM   Without a depth limit, rclone never terminates -- it just
REM   keeps deepening the tree, hitting the Windows path-length
REM   limit eventually. --max-depth 6 covers Matt's real tree
REM   (LOOM-Matt -> Guide N -> topic -> subtopic -> file is 4
REM   levels) with two levels of headroom, and stops the cycle
REM   from running away.
REM
REM   The durable fix is upstream: ask Matt to remove the
REM   self-referential shortcut(s). Until then, --max-depth
REM   keeps the pull bounded.
REM
REM No --include filter here: we WANT everything, because the
REM whole point is to capture native Docs (which have no .docx
REM extension on the Drive side until rclone exports them). If
REM Matt drops in a file type the pipeline cannot handle, it
REM will simply sit unconverted in 2-Digested's skip list --
REM visible, not silently lost.
echo --- Pass 1: preview to console (--dry-run, no file changes) ---
echo.
"%RCLONEPATH%" copy "drive:" "%LOCAL_MATT%" ^
    --drive-root-folder-id %MATT_FOLDER_ID% ^
    --drive-export-formats docx ^
    --ignore-errors ^
    --max-depth 6 ^
    --retries 1 ^
    --dry-run ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo --- Pass 2: real run (output captured by rclone to log file) ---
echo   Log: %LOGFILE%
echo   (Pass 2 is silent on console -- see the log for per-file
echo    detail. Pass 1 above showed what to expect.)
echo.
"%RCLONEPATH%" copy "drive:" "%LOCAL_MATT%" ^
    --drive-root-folder-id %MATT_FOLDER_ID% ^
    --drive-export-formats docx ^
    --ignore-errors ^
    --max-depth 6 ^
    --retries 1 ^
    --log-file="%LOGFILE%" ^
    --log-level INFO ^
    --stats-one-line --stats 5s
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   Pull complete.
echo.
echo   Native Google Docs were exported as .docx.
echo   Any real files were copied as-is.
echo.
echo   Pass 1 (console above): what rclone planned to do.
echo   Pass 2 (silent): the real run, logged to:
echo     %LOGFILE%
echo.
echo   Next step: run digest_all.bat to process new files.
echo ============================================================
pause
exit /b 0

:error
echo.
echo rclone reported an error. Check messages above
echo and the log file: %LOGFILE%
pause
exit /b 1
