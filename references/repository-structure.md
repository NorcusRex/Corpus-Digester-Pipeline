# Repository Structure

**Version 2.1**

The shared definition of the Drive repository's shape.

**Vocabulary.** *Corpus* means all of a project's material: the current
conversation, the project's past conversations, and the Drive repository.
*Repository* means the Drive folder tree alone — what this document describes. The search-project-corpus skill reads it; the
digestion pipeline is built to it. When the two disagree, this document is the
thing to reconcile them against.

## The four tiers

Every corpus has these four folders directly beneath its root, in this order:

```
1-Raw          Incoming material, any format, any path
2-Digested     Pipeline output. Classified, converted, indexed
3-Reporting    Authored reports and commentary
4-Canon        Released artifacts — what the project produces
```

These names are **architectural**. Resolve them by name. Do not enumerate to
discover them, and do not accept a root that lacks them.

**Nothing below the four tiers is architectural.** Every tier may have
subfolders to arbitrary depth, organised however the corpus owner finds useful
— by provenance, by maturity, by subject, or not at all. The schemes differ
between tiers, differ between corpora, and change over time. Enumerate them.
Never assume a scheme, and never resolve a subfolder by a name seen before.

## Non-tier siblings

The root may hold **utility** folders and files alongside the four tiers —
tooling, editor configuration, generated directory listings, audit output.
`_Tools`, `.obsidian`, `DIRTREE.txt` are examples.

These are not corpus content and are not searched. The distinction is by role,
not by naming pattern, though a leading underscore or dot marks most of them.

A root is verified by the presence of the four tiers, not by their being the
only children.

## Durability tiers

Not all structure is equally stable. Three classes, and the handling differs:

**Architectural.** The four tier names, and the root named in project
instructions. Assert and rely on these. Verify the root by checking that the
four tiers sit beneath it; a named root without them is an error worth
surfacing, not a folder to search anyway.

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
- **The Drive folder tree** is its corpus

This is why search priority runs conversation context, then past conversations,
then the Drive corpus — it is one body of material in three places, ordered by
how directly it is at hand.
