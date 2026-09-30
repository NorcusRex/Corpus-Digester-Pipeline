---
title: "Handoff — The Conventions Split"
date: 2026-09-25T13:59-07:00
source: "Claude conversation, AI Methods project"
model: Claude Opus 4.6
version: "1.0"
keywords: ["conventions", "pipeline-conventions", "repository-structure", "decoupling", "producers and consumers"]
---

# Handoff: The Conventions Split

2026-09-25 13:59 PDT · Source: Claude conversation, AI Methods project · Claude Opus 4.6
High compression, prose. Decisions and instructions only.

**Abstract.** Filename and frontmatter rules used to live in
`repository-structure.md`, which the pipeline was told to build against. They
have been moved out, because the reporting skills were decoupled from the corpus
and needed their own conventions. There are now three documents with three
owners: reports, pipeline, searcher. The pipeline's file is new, written as a
specification and **not verified against the code**. Reconciling it is the first
task.

**Keywords:** conventions · pipeline-conventions · repository-structure ·
decoupling · producers and consumers

## What changed and why

The six reporting skills carried a glossary describing a corpus data model most
of them never used, which made them unusable to anyone without a corpus. They
were decoupled: `write-report` now reads its own `report-conventions.md`,
settings rather than law, and writes a plain Markdown file if that file is
absent.

That pulled the filename, frontmatter and relative-path sections out of
`repository-structure.md` — where the pipeline was reading them. Hence this
handoff.

## The model

Two producers, one consumer. **The producers never read each other's output.**
The pipeline does not read reports; `write-report` does not read digested files.
Only the searcher reads both, which is why their conventions may differ without
anything breaking.

| Document | Owner | Governs | Lives in |
|---|---|---|---|
| `report-conventions.md` | `write-report` skill | what a report looks like | the skill |
| `pipeline-conventions.md` | the pipeline | what a digested file looks like | this repo |
| `repository-structure.md` | `search-project-corpus` | what a searcher finds | the skill, copied here |

Reports and digested files look alike — date-prefixed names, a
`title`/`date`/`source`/`keywords` block — because consistency was chosen, not
because either copies the other. Either may change without the other being
wrong.

## Instructions

**Owner: Assistant (pipeline conversation).**

1. **Reconcile `pipeline-conventions.md` against the code.** It was written
   from the digester handoff and from conversation by someone with no access to
   the repository. Statements marked **[verified]** were confirmed against code
   excerpts; everything else is specification and may be wrong. Where they
   disagree, the code is right. Correct the file, then remove its warning
   banner.

2. **Replace `repository-structure.md` in this repo** with v2.1. The copy here
   is v1.6 and still contains the filename and frontmatter sections, which have
   moved. The new version describes what a searcher finds rather than
   prescribing what a producer writes.

3. **Replace `glossary.md` with `corpus-glossary.md` v1.0.** The combined
   glossary was split; the reporting half is not the pipeline's concern. The old
   file's version number was also wrong — it was stamped with a host skill's
   version, a bug since fixed.

4. **Treat `pipeline-conventions.md` as the pipeline's own document from here.**
   It is not a shared file. Edit it freely as the code changes; nothing else
   reads it.

## Note on the completeness requirement

`pipeline-conventions.md` states that everything in `1-Raw` appears in
`2-Digested`, and records that this **does not currently hold** — files outside
`MEDIA_EXTS` and outside a detected export root are dropped. That finding came
from the code review and is the most consequential item in this handoff: the
searcher skips `1-Raw` entirely on the strength of a guarantee the pipeline does
not yet provide.

## Provenance

Report conventions v1.0, reporting glossary v1.0. High compression, prose.
Draft 1.

**Nick's own position.** That the reporting skills should be decoupled from the
corpus. That `report-conventions.md` should be editable settings, skipped
entirely when absent. That the pipeline needs its own conventions file, a new
handoff, and an updated `repository-structure.md`. That nothing in the pipeline
reads report files, and that the corpus files with frontmatter are read only by
`search-project-corpus` — which is the observation the three-owner model came
from.

**The reporter's, not ruled on** (user-acceptance tier 7 — Indeterminate). The
contents of `pipeline-conventions.md`, except where marked verified. The
descriptive reframing of `repository-structure.md`.

**Coverage.** The pipeline source was not read. `FILETREE.txt` listed the file
names; code excerpts reached this conversation only through the claude.ai/code
agent's review. Every unmarked statement in `pipeline-conventions.md` is
therefore unsupported by the code.

## Sources

1. Claude conversation, AI Methods project, 2026-09-13 to 2026-09-25. No URL
   available from within the session.
2. Code review notes from the `Corpus-Digester-Pipeline` claude.ai/code
   session, relayed into this conversation. Source of every **[verified]** mark.
3. `2026-09-24-1137__corpus-retrieval-post-mortem-and-tooling-handoff.md`
