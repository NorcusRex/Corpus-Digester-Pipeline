# Pipeline Conventions

**Version 1.3**

What the digestion pipeline writes: filenames, frontmatter, sidecars, and what
it skips. Owned by this repository, and by nothing else — edit it freely as the
code changes.

Reconciled against the source on 2026-09-25, and again on 2026-09-26 when the
authored-tier passes and OCR were added. Where v1.0 was written as
specification from outside the repository, this version states what the code
does. Corrections from that first pass are marked **[was wrong in v1.0]** so a
reader of the earlier file can see what moved.

v1.2 adds *Authored tiers* and *Scanned PDFs*, both describing behaviour that
did not exist when v1.1 was written. The version moved with the content, which
is the rule this repository applies to the shared files and should not exempt
its own.

v1.3 adds *Claude exports* — the merged tree, the ledger and the manifest
gate — and the sidecars that came with them: project knowledge, recovered
outputs and filed manifests. It restates *What the pipeline never does*, whose
"never deletes" had become too broad to be true. v1.2 fell behind the code for
four merges before this; that lapse is the reason for the paragraph above.

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

**An earlier version of a Claude conversation** — kept because it holds
messages the newest version lacks — is the newest's name plus
`__as-of-YYYY-MM-DD` (the date of the export it came from; `-HHMM` is added
when two exports share a day). See *Claude exports*.

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

**`<project>_docs/`** — beside a Claude project's metadata file, one Markdown
file per project-knowledge document, its text verbatim from the export
(`projects/<uuid>.json`, `docs[].content`).

**`<project>_manifests/`** — beside a Claude project's metadata file, every
valid revision of its manifest written in a conversation, verbatim, under the
manifest's own dated filename.

**`<conversation>_outputs/`** — beside a Claude conversation, the files Claude
wrote in it, rebuilt from its tool calls (`claude_outputs.py`), byte-identical,
with `_recovered-outputs.json` recording where each came from, whether it was
presented, and what could not be recovered. **That manifest marks the folder:**
the metadata pass, NotebookLM sidecars, the index, `clean_stale.py` and the
self-check all leave such a folder alone, so a recovered file is never stamped
or rewritten. The conversation carries the same text and links to each file.

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

Separately, a **recovered-outputs folder** (one holding
`_recovered-outputs.json`) is digested content but is never processed further:
`add_metadata.in_recovered_outputs`, with a local copy in `clean_stale.py`,
which runs standalone. Detected by the manifest, not the folder name, so a raw
folder that happens to end in `_outputs` is digested normally.

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
— content identity. A Claude export does not mirror: every Claude export is
accounted for by the one merged tree, `claude-merged/`.

## Named pipeline inputs

Data the pipeline reads but does not produce. All are configuration, not code,
and belong beside a corpus's marshaling wrapper in its `_Tools/`.

| Input | Consumed by |
|---|---|
| Claude project manifests | `claude_manifests.py`: written by `create_file` in a conversation (format 1.1, `YYYY-MM-DD-HHMM__<uuid>_manifest_r<N>_v1.1.json`), or a file in an export's `projects/` (1.0 or 1.1); detected by content shape |
| `_claude-exports.json` | `claude_archive.py` and the digest. Written by the pipeline, but a record of decisions, so it lives at the corpus root and survives `--clean` |
| `project_names.tsv` | `rename_chatgpt_projects.py` |
| `<corpus>_ai_subset.txt` | `sync_subset.py` |
| Lexicon directories | Keyword artifact vetoes |

## Claude exports

Exports are incremental: a chat is exported, digested, and may then be
deleted from Claude. **No export supersedes another.** Every Claude export
under the raw tier is part of the record, and all of them are digested into
one tree, `2-Digested/claude-merged/`, keyed by conversation UUID
(`claude_archive.py`).

- A conversation in several exports is written once, from its **newest**
  version — newest by the export's own date, the latest activity it contains,
  not its folder name or time — with that export's project placement.
- An **older version is kept** beside it (see *Filenames*) when it holds a
  message the newest lacks. Nothing an export contained is dropped, and
  nothing is removed because a later export lacks it.
- Project metadata takes the newest version; every project-knowledge
  document ever seen is kept. Memories keep the newest text and any older
  text that differs, suffixed with its export's date.
- When a conversation is written to a new path — moved to another project,
  renamed in Claude — the previous file for that same conversation is
  removed, with its `.nlm.md` and its recovered-outputs folder. A
  conversation no longer in any export is never removed this way.

**The ledger**, `_claude-exports.json` at the corpus root, lists every export
taken in: folder, a sha256 of its `conversations.json`, its date,
conversation count, and how it was accepted (`manifests checked`, or
`without manifest check` for an export from before the gate, accepted once
with `claude_archive.py accept <export>`).

**The manifest gate** (`claude_manifests.py`) runs on an export not in the
ledger, or in it with a different fingerprint — a replaced export. It runs
before anything is written, `--clean` included, and any failure stops the run
with the corpus untouched. An export is recorded only after a successful
digest. Checked once, on arrival, never again: history cannot be fixed, so
re-checking it would let one old slip block every later run.

The gate requires: a manifest for every project, even an empty one; a UUID
and name matching the export's; no conversation claimed twice or left in no
project; no manifest listing a chat the export lacks or older than a message
in one of its chats; and for format 1.1, a filename agreeing with the
contents, presented, not edited after writing, with a revision above the
last. The chat that wrote a manifest is placed in its project.

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

## Scanned PDFs

A scanned PDF is a picture of a page: `pypdf` extracts nothing, so without help
the document reaches `2-Digested` with no body, no keywords, and no way for
search to find it. `likely_scanned: true` in the frontmatter says so.

`--ocr` recovers the text. Three properties are deliberate.

**The searchable PDF is kept; `1-Raw` is still not modified.** OCR yields two
useful things — the text, which search needs, and a searchable copy of the
book, which a person opens. Both are cached. The text goes into the Markdown;
the searchable copy lands in `2-Digested` as `<name>.ocr.pdf`, recorded in the
frontmatter as `ocr_pdf`, and travels to Drive with the rest of the tier.

That is what makes overwriting the original unnecessary. Running `ocrmypdf`
over the raw tree in place is safe where `1-Raw` holds copies and wrong as a
default: the tier is defined as incoming material, the pipeline is copied to
corpora whose conventions differ, and a default that rewrites its own inputs
is one bad run from losing them. `--no-ocr-pdf` drops the copy where space
matters more than convenience.

**The cache is keyed on content hash, in `_ocr-cache` at the corpus root.** OCR
is the slowest thing the pipeline can do, seconds per page against milliseconds
for everything else, and digestion is meant to be re-runnable. Hashing the
content rather than the path means a renamed, moved or re-copied book is still
a hit; editing the PDF is what invalidates it, which is the only thing that
should. The cache sits at the corpus root rather than under `2-Digested` so it
survives a `--clean` rebuild.

**OCR text is used only where the page yields none.** A page with a real text
layer keeps it. OCR of an already-digital page is a worse reading of the same
thing, so it is never allowed to overwrite one. `text_source` records `ocr` or
`mixed`, and `ocr_pages` counts how many pages needed it.

Failures are named in `_ocr-problems.md` at the corpus root and counted in the
run summary. A book that produces no text is recorded but **not** cached, so a
better scan of it is tried again rather than being permanently remembered as
empty.

`ocrmypdf` is external and optional, found through `OCRMYPDF_EXE` or `PATH`.
Absent, OCR is skipped with a message and the rest of the run proceeds.

**`--no-pdf-images` exists for this case.** The PDF converter extracts every
embedded image from every page. For a scanned book each page image *is* the
page, so extraction duplicates the whole document as loose files for no search
value at all.

## What the pipeline never does

**It never deletes anything whose source may be gone.** `clean_stale.py`
reports; `pipeline_selfcheck.py` has no deletion path at all. Removing output
for an absent source takes an explicit flag, and above a tenth of the tree a
second one.

What it does remove is its own previous rendering of something it has just
rendered again: a re-run overwrites its files, `--clean` empties `2-Digested`
on request, a recovered-outputs folder is rebuilt from its conversation, and a
Claude conversation written to a new path loses its old file. In each case the
content is still in `1-Raw` and has just been written again. **[restated in
v1.3]**: v1.2's unqualified "never deletes" was already untrue of `--clean`.

**It never modifies `4-Canon`.** Released artifacts are catalogued by companion
files and stay byte-identical.

**It never guesses attribution.** A turn is attributed because a heading or a
label says so, never because prose sounds like someone.
