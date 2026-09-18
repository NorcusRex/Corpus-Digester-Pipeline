================================================================
QUICK REFERENCE - RUNNING THE .BAT FILES
================================================================
Last updated: 2026-05-16 (rev 2 - added subset mirror)


NOTE ON SCRIPT NAMES
--------------------
The Loom-specific batch files were replaced by generic ones that take the
corpus root and remote as parameters:

    sync_loom.bat            ->  sync_gdrive_corpus.bat
    push_loom.bat            ->  push_gdrive_corpus.bat
    merge_loom_to_drive.bat  ->  merge_corpus_local_to_drive.bat
    pull_matt.bat            ->  pull_gdrive_folder.bat
    digest_all.bat           ->  corpus_wrapper.template.bat

No corpus name, local path, or Drive path appears in any of them. Each corpus
gets one copy of corpus_wrapper.template.bat in its _Tools folder, with its
paths filled in; that wrapper calls the generic scripts in order. Configuration
files such as the AI selection list and project_names.tsv are data, not code,
and live beside the wrapper.

Sections below that still name the old scripts describe the same behaviour
under the new names.

This is the short operational cheat-sheet. For the reasoning
behind any of it -- why rclone copy instead of Drive Desktop,
what "stale" means, the failure modes -- see the full readme.txt
sections: GOOGLE DRIVE TRANSFER, STALE FILE CLEANUP, DIGESTING
MULTIPLE LIBRARIES. When this file and readme.txt disagree,
readme.txt is authoritative.


----------------------------------------------------------------
THE BAT FILES, AND WHEN TO RUN EACH
----------------------------------------------------------------

process_folder.bat
    Digest ONE folder. Double-click, or drag a folder onto it,
    or:  process_folder.bat "C:\src" "C:\dst"

digest_all.bat
    Digest ALL libraries in sequence, then stale-check each.
    Double-click for the safe default (digest + REPORT stale,
    nothing deleted). Arguments:
        (none)            digest + report stale
        --skip-stale      digest only
        --delete-stale    digest + delete verified-stale (prompts)
        --delete-orphans  digest + delete stale AND orphans (no
                          prompt -- only after reviewing a report)

pull_matt.bat
    Drive -> local. Pulls the collaborator's shared Drive folder
    into the raw tree, converting native Google Docs to .docx on
    the way down. Run this BEFORE digest_all.bat when there's new
    collaborator content. Two-pass: a --dry-run preview to the
    console, then the real pass appended to a dated log next to
    the .bat (pull_matt_YYYY-MM-DD.log).

push_loom.bat
    Local -> Drive. Backs up local Loom changes to the Drive
    copy. Non-destructive (never deletes anything in Drive). Run
    AFTER a pipeline session, as often as you like. Two-pass: a
    --dry-run preview to the console, then the real pass
    appended to a dated log next to the .bat
    (push_loom_YYYY-MM-DD.log).

merge_loom_to_drive.bat
    Local -> Drive, ONE TIME ONLY. Use this the first time, when
    local and Drive have drifted apart. Three passes with prompts
    between each: Pass 1 (dry-run) and Pass 2 (--checksum
    dry-run) print to the console so you can read them live;
    Pass 3 (the real upload) appends its output to a dated log
    next to the .bat (loom_merge_YYYY-MM-DD.log). After the
    first successful merge, use push_loom.bat from then on.

sync_loom.bat
    Mirrors the Loom-relevant subset of the digested AI exports
    into the Loom corpus, under FromNick\Notes\AI\Claude\Conversations
    \Exported\ and FromNick\Notes\AI\ChatGPT\Conversations\Exported\.
    Run AFTER digest_all.bat, and any time you edit the selection
    list. Auto-finds the newest dated export folder. Idempotent;
    safe to re-run. Flags: --dry-run (preview), --prune (also
    remove folders you de-selected from the list).


----------------------------------------------------------------
TYPICAL ORDER OF OPERATIONS
----------------------------------------------------------------

First-ever Drive setup (once):
    1. (done) rclone.exe is at
       I:\rclone-v1.74.1-windows-amd64\rclone.exe
    2. (done) own client_id created; JSON in
       I:\Google-Cloud-for-rclone\
    3. rclone config  -- create a remote named exactly "drive"
       using that client_id/secret. Verify:
           "I:\rclone-v1.74.1-windows-amd64\rclone.exe" lsd drive:
       should list your top-level Drive folders incl. RPG and
       LOOM-Matt. (The Loom corpus lives at
       drive:RPG/_Design/Loom -- not at the top level.)
    4. Run merge_loom_to_drive.bat once. Walk the three passes.

Normal working session, from then on:
    1. pull_matt.bat            (if collaborator has new docs)
    2. digest_all.bat           (digest everything; read the
                                 stale report)
    3. sync_loom.bat            (project the Loom subset out of
                                 the digested AI exports)
    4. push_loom.bat            (back the result up to Drive)

Editing which projects are in the Loom corpus:
    - Edit the selection list (its location is in the install
      notes; it lives WITH THE CORPUS, not the tooling folder).
    - Re-run sync_loom.bat. Add --prune if you REMOVED entries
      and want their mirrored copies deleted too.
    - sync_loom.bat --dry-run first if you want to preview.

Stale cleanup, when a report shows orphans you want gone:
    - Re-run digest_all.bat --delete-stale  (prompts per library)
    - Or run clean_stale.py directly on one library:
        python clean_stale.py <raw_dir> <digested_dir>
        (report only; add --delete or --delete-orphans to act)


----------------------------------------------------------------
THE ONE SETTING YOU MAY NEED TO EDIT
----------------------------------------------------------------

Each rclone .bat has, near the top:

    set "RCLONEPATH=I:\rclone-v1.74.1-windows-amd64\rclone.exe"

This is the ONLY thing tying the scripts to where rclone lives.
rclone is NOT required on the system PATH. If you ever move or
upgrade the rclone folder (e.g. a new version with a different
folder name), edit this one line in:
    pull_matt.bat
    push_loom.bat
    merge_loom_to_drive.bat

Library paths (LOCAL_LOOM, DRIVE_LOOM, LOCAL_MATT) and the
collaborator folder ID (MATT_FOLDER_ID, an immutable Drive ID
rather than a folder name -- see pull_matt.bat's header comments
for why) are also set lines near the top of the relevant files
-- edit there if a library moves or the shared folder is
re-shared.


----------------------------------------------------------------
SAFETY NOTES (THE SHORT VERSION)
----------------------------------------------------------------

- push_loom.bat / pull_matt.bat / merge: all rclone COPY. They
  never delete anything on either side. A file removed from the
  source stays at the destination until you remove it by hand.
  This is deliberate -- it is what makes the Drive copy safe as
  a backup.

- The destructive operations are ONLY: clean_stale.py with
  --delete / --delete-orphans, and digest_all.bat with
  --delete-stale / --delete-orphans. None of these is a default;
  all of them either prompt or require an explicit flag.

- push_loom.bat's LOCAL_LOOM must point at the Loom LIBRARY, not
  at the tooling folder. Do not point it at I:\ root, or it will
  push the pipeline scripts and the client_secret JSON up to
  Drive along with the library.
