# Quickstart

The short operational cheat-sheet. For the reasoning behind any of it — why
`rclone copy` instead of Drive Desktop, what "stale" means, the failure modes —
see [`pipeline-guide.md`](pipeline-guide.md). Where this file and the guide
disagree, the guide is authoritative.

## The one file you edit

`corpus_wrapper.template.bat` is the only per-corpus artifact. Copy it into a
corpus's `_Tools/` folder, edit the configuration block at the top, and run it.
Everything it calls is generic — no corpus name, local path or Drive path
appears in any other script.

The block sets: where the pipeline lives, this corpus's root, its Drive path,
the subject name for keyword weighting, and optionally a glossaries folder.

## Running it

| Command | Does |
|---|---|
| `<wrapper>.bat` | Digest, catalogue `4-Canon`, stale-check, self-check |
| `<wrapper>.bat --sync` | Also mirror selected AI conversations in first |
| `<wrapper>.bat --push` | Also push the result to Drive |
| `<wrapper>.bat --all` | Everything |
| `<wrapper>.bat --audit` | Also write a rejected-keyword report |
| `<wrapper>.bat --dry-run` | Show what would happen; change nothing |

The default deletes nothing. The stale check and self-check report only.

## The generic scripts, and when each runs

- **`sync_gdrive_corpus.bat`** — mirrors a selected subset of digested AI
  conversations into a corpus. Called once per source, so a corpus pulling from
  both Claude and ChatGPT calls it twice. Auto-finds the newest dated export
  folder by filesystem date, not by name — export folder names are not
  zero-padded, so a name sort would pick the wrong one. Idempotent.
  Takes `--dry-run` and `--prune`.

- **`pull_gdrive_folder.bat`** — Drive → local. Pulls a shared Drive folder into
  the raw tree, converting native Google Docs to `.docx` on the way down. Run
  before digesting when a collaborator has new content. Takes the folder id and
  the local destination.

- **`push_gdrive_corpus.bat`** — local → Drive. Backs a corpus up to its Drive
  copy. Non-destructive; never deletes anything in Drive. Run as often as you
  like; identical files cost nothing. Two passes: a `--dry-run` preview to the
  console, then the real pass logged.

- **`merge_corpus_local_to_drive.bat`** — local → Drive, **first time only**,
  when local and Drive have drifted apart. Three passes with a prompt before the
  upload: a default dry run, a `--checksum` dry run, then the real one. If pass 2
  is much shorter than pass 1, the difference was timestamps rather than
  content. Use `push_gdrive_corpus.bat` from then on.

## Typical order

1. `pull_gdrive_folder.bat` — if a collaborator has new docs
2. `<wrapper>.bat --sync` — mirror the AI subset, then digest
3. Read the stale report and the self-check
4. `<wrapper>.bat --push` — back the result up

Or `<wrapper>.bat --all` to do all of it in one run.

## Finding rclone

There is no path to edit. `_rclone_common.bat` looks in three places, in order:

1. the `RCLONE_EXE` environment variable
2. `rclone.exe` on your `PATH`
3. `I:\rclone-v1.74.1-windows-amd64\rclone.exe`

If it is somewhere else, set the variable once:

```
setx RCLONE_EXE "D:\tools\rclone\rclone.exe"
```

All four rclone wrappers use the same lookup, so that is the only place it is
configured.

## After editing the selection list

Re-run the wrapper with `--sync`. Add `--prune` to `sync_gdrive_corpus.bat` if
you **removed** entries and want their mirrored copies deleted too. Preview with
`--dry-run` first if you are unsure.

## Safety notes

**Nothing is deleted automatically.** `clean_stale.py` and
`pipeline_selfcheck.py` report; removing anything takes an explicit flag.

**An absent source is not stale output.** A source may have been renamed, or
cleared on purpose to reclaim disk. `--delete` alone removes nothing; that takes
`--delete-source-absent`, and above 10% of the tree it also takes `--force`.
Mark a deliberately retired source with `source_retired: true` in the digested
file's frontmatter and it stops being reported.

**`4-Canon` is never modified.** Released artifacts get companion catalog files
and are left byte-identical.

**rclone copy is non-destructive.** It adds and updates; it never deletes on the
destination. A file removed from Drive stays in your local tree until you remove
it by hand, and vice versa.

## Old script names

The Loom-specific wrappers were replaced by generic ones:

```
sync_loom.bat            ->  sync_gdrive_corpus.bat
push_loom.bat            ->  push_gdrive_corpus.bat
merge_loom_to_drive.bat  ->  merge_corpus_local_to_drive.bat
pull_matt.bat            ->  pull_gdrive_folder.bat
digest_all.bat           ->  corpus_wrapper.template.bat
```

`digest_all.bat` digested several libraries in one run; its replacement handles
one corpus and is copied per corpus instead.
