# Pipeline Conventions

**Version 1.1**

What the digestion pipeline writes: filenames, frontmatter, sidecars, and what
it skips. Owned by this repository, and by nothing else — edit it freely as the
code changes.

Reconciled against the source on 2026-09-25. Where v1.0 was written as
specification from outside the repository, this version states what the code
does. Corrections from that pass are marked **[was wrong in v1.0]** so a reader
of the earlier file can see what moved.

## Scope

This governs `2-Digested`, and the authored-tier catalog the pipeline writes
into `4-Canon`. Reports written by the `write-report` skill follow
`report-conventions.md` and are not produced here; the two producers never read
each other's output.

## Filenames

**A converted file keeps its source's name.** `notes.docx` becomes `notes.md`
beside a `notes_media/` folder if it has images. **[was wrong in v1.0]**, which
described a date-prefixed convention for everything.

Two exceptions:

```
2026-02-22__failure-with-promise-in-loom.md     conversation from an AI export
export-2026-09.zip.md                           sidecar for an unconvertible file
```

**Conversations extracted from an AI export** are named
`YYYY-MM-DD__lowercase-hyphenated-slug.md`, from the conversation's create time
and title. There is no time component and no version suffix: a digested file is
derived from one source and regenerated rather than revised, so there is
nothing for a version to track.

**Sidecars** keep the original's full name, extension included, plus `.md`.
`notes.zip` and `notes.docx` therefore cannot collide on one sidecar.

Where two sources would produce the same output name in one run, the second
gets a `-2`, `-3` suffix. Re-runs overwrite rather than accumulate.

## Frontmatter

Every Markdown file in `2-Digested` carries these. The first four are what
search relies on; the rest are the pipeline's own record.

| Field | Meaning |
|---|---|
| `title` | Human title, matched by Drive's `title` search operator |
| `date` | Date of the source material, not of digestion |
| `keywords` | Extracted terms, a list of quoted strings, comma-space separated |
| `source` | Where the material came from — `docx`, `Claude export (conversation)`, `unconverted file (sidecar)` |
| `date_source` | Which of three sources `date` came from |
| `source_file` | **Filename only** of the original, e.g. `Danger vs Agency.docx` |
| `source_path` | Path of the original relative to the corpus root, forward slashes |
| `source_sha256`, `source_bytes` | The source's content identity |
| `conversation_id` | For AI exports |
| `provenance_structure` | `turn-structured`, `speaker-labelled`, `single-voice`, `unknown` |
| `keywords_weighted` | Whether provenance weighting applied |
| `word_count`, `modified`, `indexed_at` | Computed on every run |

**`source_file` and `source_path` are different fields.** **[was wrong in
v1.0]**, which said `source_file` holds a corpus-relative path. It holds a bare
filename; `source_path` holds the path. Converted files carry `source_file`;
sidecars carry both.

Converted `.docx` also carries `images_extracted`, and `unresolved_images` or
`horizontal_rules` where either is non-zero.

### date

Resolved from three sources, first hit wins, and `date_source` records which:

1. a date the converter already knows — a conversation's `create_time`, a
   docx's document properties
2. the timestamp in the filename, where the name follows the convention
3. the file's modification time

Emitted as local time with offset, `2026-09-15T17:47-07:00`. PDF dates are
parsed with their own offset honoured rather than assumed local. A file that
already carries `date` is left alone.

### Orphan detection

`clean_stale.py` reads `source_file`, `conversation_id`, `source_sha256` and
`source_bytes`. **[expanded since v1.0]**: it no longer matches on filename
alone.

An absent source is reported as `absent-file` or `absent-conv` — deliberately
not "stale", because from the digested side a source deleted upstream and one
cleared on purpose to reclaim disk look identical. Before reporting anything
absent it searches the raw tree by content hash; the same bytes under a new
name is a **rename**, reported with both names and never deletable. Size is
matched first, so only genuine size-matches are hashed.

`source_retired: true` in frontmatter marks a deliberate removal and stops the
file being reported at all.

## Sidecars

**`<name>.nlm.md`** — the same content with frontmatter stripped, for tools that
choke on YAML.

**`<name>_media/`** — a folder of the file's images and audio, linked inline
from the Markdown by relative path. Implemented in the docx, pdf and html
converters. HTML also copies relative `src=` targets in from a saved page's
companion folder. **Not yet implemented for AI export media** — see the
backlog.

**`<original-name.ext>.md`** — a stub standing for a file that could not be
converted, recording the original's name, type, size and `source_path`. It
makes the original findable without duplicating it. Media and AI-export
auxiliary files are copied through instead, because a digested conversation
referencing its own images needs them beside it.

**`<artifact-name.ext>.md` in `4-Canon`** — a catalog record beside a released
artifact, written by `tier_sidecars.py`. **The artifact itself is never
modified**: no frontmatter is stamped into it and no index block is inserted
into its prose. A Markdown artifact that already carries frontmatter describes
itself and is left alone.

## Speaker headings

Converted AI exports mark turns as headings:

- Claude exports: `## Human` / `## Assistant`
- ChatGPT exports: `## User` / `## Assistant` / `## System` / `## Tool`

Both dialects are recognised. Matching only `## Human` would classify every
ChatGPT-derived file as `unknown`, which is the bulk of the corpus.

## Provenance structure

Classified before any weighting, by **positive detection only** — a file is
conversational because a pattern matched, never because another pattern failed.
Turns are never inferred from voice, topic shift or style.

| Value | Detected by |
|---|---|
| `turn-structured` | Turn headings for both sides |
| `speaker-labelled` | Two or more inline `**Name:**` labels, each recurring |
| `single-voice` | No conversational markers, and a `source` that is not an AI |
| `unknown` | Everything else |

Speaker labels are an open set — names, not a vocabulary. `unknown` is not an
error: the file keeps unweighted extraction and is reported.

## Keyword extraction

TF-IDF across the corpus, with the term-frequency count weighted by **whose
turns the term appears in**. Two buckets, not a tier ladder — keywords answer
what a document is about, and acceptance does not bear on that.

One question decides the weight: does the term appear anywhere in the subject's
turns? Yes weighs 128, no weighs 1. Because TF is sublinear, that is a
`+log(128)` bonus rather than a 128× one.

**Quoting counts as using.** Reproducing a passage is engagement with its
terminology, whoever wrote it first. This also means the weighting does not
depend on blockquote markers, which nobody adds consistently, and a quotation
of another person or another chat cannot be mistaken for the assistant's.

Weighting applies only to `turn-structured` and `speaker-labelled` files.
Everything else keeps unweighted extraction and is marked
`keywords_weighted: false`; `unknown` files are additionally reported.

Keywords are currently **single words**. The multi-word requirement that lived
in `repository-structure.md` v1.11 did not survive the conventions split — see
the backlog.

### Rejecting extraction artifacts

Two tiers. **Hard** tests cover shapes no English word takes: no vowel
(counting `w`, so Welsh survives), letters mixed with digits, `q` not followed
by `u`, a letter three times running, a seven-consonant run. **Soft** tests are
implausible letter sequences — an impossible letter pair, a six-consonant run —
rejected only when nothing vetoes them.

A veto is the term appearing in a lexicon, appearing capitalised mid-sentence,
or recurring across three or more documents. `--report-artifacts` writes every
rejection with the test that caused it.

Vowel ratio was tried and abandoned: `kxwoj` and `clock` sit at the same ratio,
so it cannot separate them.

## Skip list

Not corpus content; excluded from digestion, indexing, extraction and the
self-check. **One list, shared between the digester and the self-check** —
`add_metadata.is_utility_path`. **[fixed since v1.0]**, which correctly
observed that the two disagreed.

- Office lock files, `~$*`
- Dot-files and dot-directories at any depth, including `.obsidian/`
- Build artifacts, `__pycache__/`, `*.pyc`, `*.pyo`
- Generated listings, `DIRTREE.txt`, `FILETREE.txt`, `tree.txt`
- Audit output, anything under `_audit/`
- Tooling folders, `_Tools/`, `node_modules/`
- OS clutter, `.DS_Store`, `Thumbs.db`, `desktop.ini`

The pipeline runs `1-Raw` → `2-Digested` directly and never sees the corpus
root, so root-level utility folders are out of reach anyway. `--corpus-root`
supplies the root for `source_path`, defaulting to the input tier's parent.

## The index

**The index format is specified in `references/repository-structure.md`, not
here.** The searcher parses `_index.json` — it reads the index before anything
else — so the format is an interface between two parties, and it lives in the
shared document both of them hold. Restating it here would give one fact two
homes and let them drift.

What belongs here is what the pipeline decides about its own output:

- Written to `2-Digested` on every non-dry run, after the metadata pass
- Lists **Markdown files only**, including sidecars, which are Markdown
- Media carried through is not indexed; it is reached through the file that
  references it
- `.nlm.md` files are excluded — they are derivative
- `_manifest.json`, written by older versions, is still read under that name

## Completeness

**Everything in `1-Raw` appears in `2-Digested`**, converted, copied or
sidecarred. Nothing is silently dropped.

**[fixed since v1.0]**, which recorded this as not holding. It now does: files
outside `MEDIA_EXTS` and outside a detected export root get a sidecar instead
of incrementing `stats["unsupported"]`, so `.doc`, `.pptx`, `.epub`, `.eml`,
`.csv`, `.zip` and stray JSON are accounted for.

`2-Digested` is therefore a complete **catalog** of `1-Raw` rather than a
complete copy. A searcher reads three tiers and treats `1-Raw` as the escape
hatch for the bytes themselves.

The self-check tests this rather than assuming it, matching each raw file
against a conversion, a copy at the mirrored path, a sidecar, or — last resort
— content identity.

## Named pipeline inputs

Data the pipeline reads but does not produce. All are configuration, not code,
and belong beside a corpus's marshaling wrapper in its `_Tools/`.

| Input | Consumed by |
|---|---|
| `<PROJECT_UUID>_manifest.json` | `claude_to_markdown.py`, detected by content shape |
| `project_names.tsv` | `rename_chatgpt_projects.py` |
| `<corpus>_ai_subset.txt` | `sync_subset.py` |
| Lexicon directories | Keyword artifact vetoes |

## Authored tiers

`3-Reporting` and `4-Canon` hold writing the pipeline did not produce. Both
need to be findable, and they are handled differently because only one of them
can be touched.

**`3-Reporting` is stamped in place, where a field is missing.** A report from
the `write-report` skill arrives with a complete header. Anything hand-written,
pasted, or older than that skill does not, and search cannot see a file with no
`title`, `date`, `keywords` or `source`. `stamp_tier.py` fills in what is
absent and leaves what is present, so a hand-written title or a deliberately
set date survives. A file that is already complete is left byte-identical.

Two differences from the metadata pass over `2-Digested`, both deliberate. No
generated index block is inserted — that is right for a converted conversation
and wrong for authored prose. And keywords are computed over `3-Reporting`
alone, because TF-IDF is relative to the body it is measured over and a
report's distinctive terms should be distinctive among reports.

`source` is set to `authored` where nothing supplied one. In `2-Digested` a
converter names the origin; an authored file has no converter, and `authored`
is the most the pipeline can honestly say.

**`4-Canon` is catalogued, never stamped.** Most released artifacts are not
Markdown and could not carry frontmatter anyway, and modifying something that
has been released is not a thing the pipeline does. `tier_sidecars.py` writes a
companion record carrying the same four fields, and the artifact stays
byte-identical.

A Markdown artifact in `4-Canon` counts as self-describing, and is left without
a sidecar, only when its frontmatter is **complete**. Presence is not enough: an
older artifact carrying a bare `title:` looks finished and is still invisible to
search. Those now get a sidecar like any other artifact.

## What the pipeline never does

**It never deletes.** `clean_stale.py` reports; `pipeline_selfcheck.py` has no
deletion path at all. Removing anything takes an explicit flag, and above a
tenth of the tree a second one.

**It never modifies `4-Canon`.** Released artifacts are catalogued by companion
files and stay byte-identical.

**It never guesses attribution.** A turn is attributed because a heading or a
label says so, never because prose sounds like someone.
