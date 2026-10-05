# Runbook: Claude export to pushed corpus

The whole procedure, start to finish, for bringing a new Claude export into the
corpora. Follow it in order; each step says what you should see. The reasoning
behind any step is in [`pipeline-guide.md`](pipeline-guide.md), and the
wrapper's flags are in [`quickstart.md`](quickstart.md).

Two kinds of corpus are involved:

- **The export archive**, `I:\AI\Backups\Claude\Exported`. Raw exports go into
  its `1-Raw`; it digests them and groups conversations into project folders.
  Nobody searches it directly.
- **Topic corpora**, such as Loom. Each mirrors the project folders it wants
  out of the archive (its selection list), digests them, and is pushed to
  Drive.

---

## 1. Before exporting, in claude.ai

**Every chat must be in a project.** The digest stops if any conversation
belongs to none. Move stray chats into projects first.

**Update each project's manifest.** In each project, open its dedicated chat,
`Update manifest for <project name>`, and run:

```
/update-project-manifest <project UUID> <project name>
```

The UUID is in the project's URL. You should see a file card named like
`2026-10-05-0930__<uuid>_manifest_r3_v1.1.json`. No card means the skill did
not follow its rules; run it again. A project without such a chat gets one now
— every project needs a manifest, even an empty one.

Only projects with new or changed chats since their last manifest need this,
but if in doubt, run it: the digest stops if a manifest is out of date.

**Then export straight away.** A chat touched after its project's manifest
makes that manifest out of date, and the digest will stop.

## 2. Export and unzip

Request the data export from claude.ai's settings, download it, and unzip it
into the archive's raw tier as its own folder:

```
I:\AI\Backups\Claude\Exported\1-Raw\<export folder>\
    conversations.json  users.json  memories.json  projects\
```

**Nothing else to do here.** Manifests are no longer downloaded or copied into
`projects\`; the pipeline reads them from the export itself.

## 3. Update the pipeline

```
cd I:\AI\Backups\_Tools\Corpus-Digester-Pipeline
git pull
```

## 4. Digest the archive

Run the archive's wrapper (a copy of `corpus_wrapper.template.bat` with
`ARCHIVE_ONLY=1`), or directly:

```
python I:\AI\Backups\_Tools\Corpus-Digester-Pipeline\process_folder.py ^
    I:\AI\Backups\Claude\Exported\1-Raw I:\AI\Backups\Claude\Exported\2-Digested ^
    --archive-only
```

**If it stops** with a banner reading `STOPPED: the project manifests for this
export are not right`, nothing has been written. The banner lists every
problem. Fix them in claude.ai (usually: regenerate a manifest, or move a chat
into a project), export again, replace the export folder, and rerun. Do not
reach for `--lenient-manifests`: it exists only for exports made before
manifests were written this way.

**Open decision — older exports in `1-Raw`.** The check runs on every Claude
export in `1-Raw`, and exports made before this change (such as
`2026-05-9-15-24-00`, whose manifests were dropped in by hand) do not pass it.
Until PM decides how those are handled, a run over a `1-Raw` holding them will
stop.

## 5. Read the run summary

Look for these lines near the end:

| Line | Means | Action |
|---|---|---|
| `claude exports : … conversations, … projects, … knowledge docs` | What was converted | None |
| `claude outputs : N recovered, M not recoverable` | Files Claude wrote, rebuilt into each conversation's `_outputs` folder; `M` were binary | None; the binaries are listed in each folder's `_recovered-outputs.json` |
| `[create_file rule] "<chat>" -- <file>: …` | A presented file was not written into outputs by `create_file` | Tell the skill or chat responsible; the file is recovered anyway |
| `errors : 0` | — | Anything above 0: read the warnings above it |

Then the stale-check and self-check reports. Both only report; nothing is
deleted.

## 6. Mirror, digest and push each topic corpus

For each topic corpus that takes Claude conversations:

```
<corpus>\_Tools\<wrapper>.bat --all
```

That mirrors its selected project folders from the archive, digests, checks,
and pushes to Drive. To preview first, use `--dry-run`.

---

## When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `has no manifest` | Project never had one, or the skill wrote it the old way | Run the skill in that project's manifest chat; export again |
| `is in no project` | A chat outside every project | Move it into a project; update that project's manifest; export again |
| `is out of date` | A chat was used after its project's manifest | Regenerate the manifest; export again |
| `claimed by both` | A manifest was generated in the wrong project | Regenerate both projects' manifests, each in its own chat |
| `calls project … but the export calls it …` | Wrong name given to the skill, or the project was renamed | Regenerate with the current name |
| `filename …` / `never presented` / `edited after` | The skill did not follow its rules | Regenerate; it becomes the next revision |
