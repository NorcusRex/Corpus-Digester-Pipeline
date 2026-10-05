---
title: Handoff — Manifest format 1.5 and update-project-manifest 3.4
date: 2026-10-05T12:07-07:00
source: "claude.ai/code, Corpus-Digester-Pipeline repository (Developer)"
keywords: [handoff, project manifest, manifest format, update-project-manifest, closeout-chat, create_file, revision, manifest gate]
---

# Handoff — Manifest format 1.5 and `update-project-manifest` 3.4

*2026-10-05 12:07 PDT · From: Developer (this repository) · To: Designer, via PM*

## What this asks for

Two changes to files the Designer owns, and one to a skill's behaviour, all
ruled by PM in the session that produced this handoff:

| File | Now | Proposed |
|---|---|---|
| `project-manifest-format.md` | 1.4 (format 1.0) | **1.5 (format 1.1)** |
| `update-project-manifest` skill | 3.3 | **3.4** |
| `closeout-chat` skill | — | a reminder, not a manifest |

The pipeline side is already built against the proposal below, so the
proposal can be checked against working code. It reads format 1.0 and 1.1. If
the Designer changes any detail, the pipeline follows the Designer.

## Why

**The manual step goes.** Today a manifest is downloaded from its chat and
dropped into the unzipped export's `projects/` folder, one file per project,
before every digest. PM ruled that this is the tedious part, and it is
avoidable: a file written with `create_file` keeps its full text in the
export's `conversations.json`, as the input to that tool call. The pipeline now
reads manifests from there. The download-and-file step disappears, and
"generate the manifests, then export" — PM's order — becomes the correct one.

**Every revision is kept.** Each regeneration is another dated tool call in
the export, so the history comes free. That reverses the reason the current
format fixes the filename (one current manifest, replaced on download), and so
the filename rule changes with it.

## Format 1.1 (document 1.5)

### Filename

```
YYYY-MM-DD-HHMM__<PROJECT_UUID>_manifest_r<N>_v<format>.json
```

```
2026-10-05-0930__019cfa39-2239-73f8-b318-26995911b88a_manifest_r3_v1.1.json
```

- The datetime follows the corpus convention (`YYYY-MM-DD-HHMM__`, local
  time) and must equal `generated_at` to the minute.
- `r<N>` is the revision, an integer. PM wants it in the name: integers are
  compared at a glance; the datetime says when.
- `v<format>` is `manifest_format_version`.

The section that says the filename "must not be changed" to the corpus
convention is replaced. It was right for a file looked up by fixed name; the
pipeline has never matched manifests by name (it detects them by content), and
the file is no longer looked up at all.

### Structure

One new field, `revision`, after `generated_at`:

```json
{
  "manifest_format_version": "1.1",
  "project_uuid": "019cfa39-2239-73f8-b318-26995911b88a",
  "project_name": "RPG - The Loom",
  "generated_at": "2026-10-05T09:30-07:00",
  "revision": 3,
  "conversation_count": 28,
  "conversations": [ ... unchanged ... ]
}
```

**`revision`** — starts at 1 for a project's first manifest and increases by
one each time it is regenerated. Never reused, never decreases.

Everything else is unchanged: ordering, encoding, field meanings.

## Skill 3.4

1. **One dedicated chat per project**, named `Update manifest for <project
   name>`. Every regeneration happens there. That is what lets the skill
   number revisions reliably: the previous manifest, with its revision, is in
   that chat's own history. First manifest in the chat: revision 1. Otherwise
   the previous revision plus one.
2. **Write with `create_file`, directly to
   `/mnt/user-data/outputs/<filename>`, then present it.** Never from a
   script, never written to `/home/claude` and copied — PM found the skill
   doing exactly that, which leaves only the copy command in the export, not
   the JSON. Never edit it afterwards: a wrong manifest is regenerated, as the
   next revision.
3. **The fixed-filename section goes** ("Write the same filename every time").
4. **An empty project still gets a manifest** with an empty list and a count
   of zero. This is now required, not merely allowed: see the gate below.
5. Enumeration and verification are unchanged.

## `closeout-chat`

PM ruled against generating manifests at closeout: a manifest written in the
chat being closed cannot see the previous revision number. Closeout instead
**reminds** the user to update the project's manifest in its dedicated chat.

## A general rule PM stated, for the Designer to place

> No output file is created or presented unless it is written to `outputs`
> with `create_file` as its final creation step.

It applies to every skill, not only this one. The pipeline reports each
presented file that breaks it (copied into `outputs`, or built by a script) on
every run. Where the rule should live — each skill, or a shared convention —
is the Designer's call.

## What the pipeline now enforces

Before anything is written, every Claude export's manifests are checked. Any
failure stops the run with the corpus untouched (`--lenient-manifests`
downgrades this to a report, for exports made before this change).

- Every project in the export has a manifest — even an empty one.
- The manifest's UUID is a project in the export, and its `project_name`
  matches the export's name for that project.
- The newest manifest per project is the one used. It must be valid JSON in an
  accepted format, its count must match its entries, and it must list no
  conversation twice. For 1.1, the filename must agree with the contents (time,
  UUID, revision, format), the file must have been presented and not edited
  afterwards, and its revision must be higher than the previous one's.
- No conversation is claimed by two projects.
- Staleness: every conversation a manifest lists is in the export, and none
  has a message newer than the manifest. (A fixed age limit was rejected: a
  manifest for a project left alone for a month is old and still correct.)
- No conversation ends up in no project.
- The chat that wrote a manifest is placed in that manifest's project, listed
  or not.

A manifest generated in the wrong project, under the right UUID and name, is
not directly detectable — but it is caught: the project it really ran in
either has its own manifest, which claims the same conversations, or has none.

## Questions for the Designer

1. Should the skill list its own chat in the manifest? The pipeline places it
   either way; listing it is harmless.
2. Is `Update manifest for <project name>` the name to standardise, or should
   the skill name the chat itself?
3. Where should the general `create_file` rule live?
