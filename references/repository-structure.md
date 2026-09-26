# Repository Structure

**Version 2.4**

The shared definition of the Drive repository's shape.

**Vocabulary** is defined in `corpus-glossary.md`, which is authoritative where
this file and it disagree. *Repository* — the Drive folder tree — is what this
document describes.


## Scope

Vocabulary — the tier names, what each holds, which root-level folders are
utility rather than content — is in `corpus-glossary.md`.

This document covers what a searcher needs beyond the vocabulary: durability,
the index format, the completeness guarantee, and the ownership model.

## Durability tiers

Not all structure is equally stable. Three classes, and the handling differs:

**Architectural.** The tier names, and the root named in project instructions.
Assert and rely on these.

**Verify a root by checking that `1-Raw` and `2-Digested` sit beneath it.** A
root carrying those two is a corpus. One carrying `3-Reporting` and `4-Canon` as
well is a **Production** corpus; one carrying only the first two is a
**Reference** corpus, which is valid rather than an error. A named root with
neither of the first two is not a corpus, and searching inside it anyway is the
failure this check exists to prevent.

**Evolving.** Everything below the four tiers. Follows a pattern, but the
pattern changes. **Enumerate at resolution time. Never resolve by name, never
hardcode a count, never assume a naming scheme.**

Names below the tiers have already diverged between mirrors in practice — the
same corpus has carried both singular and plural forms of the same subfolder on
local and remote simultaneously. A skill that resolves them by name breaks
silently when a folder is renamed; one that enumerates does not.

**Non-durable.** Drive file and folder IDs. A clean re-push creates new objects
with new IDs. Resolve per session, never store across sessions. A stored ID
returning nothing means *re-resolve*, never *corpus broken*.

## Which tiers carry an index

**`2-Digested` has an index**, written by the pipeline: `_index.json`
(current) or `_manifest.json` (legacy — the old name does not mean the index is
missing). Top-level `generated_at`, `output_root`, `file_count`, `stats`,
`files[]`. Each entry carries `path`, `size_bytes`, and `frontmatter` including
`title` and `keywords`. The index carries **no file IDs** by design; it is
written before the push.

**`3-Reporting` and `4-Canon` have no index, by design.** They are authored
tiers, not pipeline-generated. The absence of an index there is expected — not
a defect, not a tool limitation, and never a reason to report the tier as
unsearchable.

## What a searcher can rely on

**`2-Digested` covers everything in `1-Raw`.** Files the pipeline can convert
appear as Markdown; files it cannot appear as a small Markdown sidecar
recording the original's name, type and source path. Media accompanying a
converted file is carried through beside it.

Search therefore reads three tiers rather than four, treating `1-Raw` as an
escape hatch for originals rather than a routine target.

This is a property the pipeline provides, specified in its own
`pipeline-conventions.md`. This document describes what a searcher meets; it
does not govern what the pipeline writes. If completeness stops holding, search
misses whatever was dropped and has no way to notice — which is why the
pipeline's self-check tests it rather than assuming it.

## Who writes what

Three documents, three owners, no overlap:

| Document | Owner | Governs |
|---|---|---|
| `report-conventions.md` | the `write-report` skill | what a report looks like |
| `pipeline-conventions.md` | the digestion pipeline | what a digested file looks like |
| this file | `search-project-corpus` | what a searcher finds |

The two producers never read each other's output. The one consumer reads both,
which is why their conventions may differ without anything breaking — the
searcher has to handle both shapes regardless.

## Project and corpus

A project and its corpus correspond:

- **Project context files** are the project's governing documents
- **Project conversations** are its raw material
- **Evernote** holds what has not yet been exported
- **The Drive folder tree** is the repository

Search priority runs conversation context, then past conversations, then
Evernote, then the repository — one body of material in four places, ordered by
how directly it is at hand.
