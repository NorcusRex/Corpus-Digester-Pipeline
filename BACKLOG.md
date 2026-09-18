# Backlog

Work agreed but not built, and questions waiting on an answer. Items are drawn
from the digester handoff (v6.8) and from findings while implementing it.

Owners follow the handoff's convention: **Assistant** for code and
verification, **Nick** for rulings, Drive operations, and anything needing the
real corpus.

---

## Waiting on the corpus

### docx unresolved drawings — Decision 7
**Resolved. No media was being lost; the figure was our own false positive.**

The premise was that a 43,639-word docx reporting `unresolved_drawings: 433`
with `images_extracted: 0` had lost 433 images. Verified against the real file
(`Danger vs Agency.docx`) and it had not. The document contains no images at
all:

| Probe | Count |
|---|---|
| `word/media/` | folder absent |
| `<w:drawing>` | 0 |
| `r:embed=` / `r:link=` | 0 / 0 |
| `<v:shape>` / `<v:imagedata>` | 0 / 0 |
| `<w:object>` / `<mc:AlternateContent>` | 0 / 0 |
| image relationships, `TargetMode="External"` | 0 / 0 |
| **`<w:pict>`** | **433** |
| **`<v:rect>`** | **433** |

Pasting a web page into Word turns every HTML `<hr>` into
`<w:pict><v:rect o:hr="t">`. The file is a pasted ChatGPT conversation, so the
433 were turn separators. `render_pict` called every picture element without
image data a failed image, and the counter was a substring search for
`(unresolved)` over the finished Markdown.

Both fixed. `render_pict` now distinguishes three cases — a resolvable image, an
image that will not resolve, and a picture element that is not an image at all
(a horizontal rule renders as `---`, other bare shapes render as nothing).
The field is renamed `unresolved_images`, counts actual emissions, and is
joined by `horizontal_rules`. Re-digestion replaces `unresolved_drawings` in
existing output.

Side effect worth knowing: those 433 dead markers were in the body, so keyword
extraction had been counting *embedded* and *unresolved* 433 times in that file.
Neither is a stopword. The same held for every pasted conversation, which is
most of the high-count list.

**Still open: Matt's drafts are a different origin.** `3.4 Skills - Description`
(99) and the Dragons file (83) are authored docx, not pasted conversations, and
may have genuinely embedded images. Probe `word/media` on one of them. If it is
populated, the straightforward extraction case is real for his files even though
it was not for the pasted ones.

### AI export media pointers — Decision 7
**Owner: Nick to run the inspection, Assistant to build.**

`chatgpt_to_markdown.extract_text` discards the multimodal content dict,
emitting `[<content_type> content omitted]` and dropping the `asset_pointer`
field that sits in it. The link between a conversation and its images exists in
the export and the converter throws it away. This is the path covering the
1,446 uncarried files.

Needed before building: the distinct `content_type` values and a sample of
`asset_pointer` strings from one real export, plus that export folder's
filenames, so the pointer-to-file mapping is known rather than guessed. The
export format has changed across ChatGPT versions.

The Claude side is better placed — `render_files` already reads `file_name` and
`file_uuid`.

---

## Agreed, not yet built

### Pipeline self-check — Decision 5
**Built** as `pipeline_selfcheck.py`. Kept here for the record of what it covers.

All six checks: unconverted files, index integrity,
frontmatter presence, filename conformance, duplicate content by normalized
token windows, and suggest-never-delete. `4-Canon` is exempt from the
frontmatter check.

The completeness check is well-defined now that every file in `1-Raw` lands in
exactly one of three states in `2-Digested`: converted, copied through, or
represented by a sidecar carrying `source_path`.

Duplicate detection must fingerprint several windows through each document, not
only the head — a pasted copy may begin at a different point than an export of
the same conversation. Where candidates differ, report the passages present in
one and not the other: **that is where hand-added commentary lives and it must
not be lost to deduplication.**

---

## Waiting on a ruling

### Frontmatter stamping for 3-Reporting — Decision 2
**Owner: Nick to rule.**

May be unnecessary. The `write-report` skill now writes frontmatter in the same
format, so reports arrive already stamped. The open question is whether enough
hand-written or pasted material reaches `3-Reporting` to justify a stamping
pass at all.

`4-Canon` is settled and needs no ruling: no stamping, ever. Released artifacts
are catalogued by companion sidecars (`tier_sidecars.py`) which leave the
artifact byte-identical.

### Reject extraction artifacts from keywords — Decision 8
**Owner: Nick to rule on scope.**

Keyword lists contain strings such as `erlyjewxq`, `jauuimuv-wmcjrfg`, `kxwoj`
and `lz-pirirgptx` — conversion artifacts, not words. The current filters do
not catch them: tokens need only start with a letter and reach four characters.

Structural filters (no vowels, implausible consonant runs, mixed alphanumeric
noise) are stdlib-only and catch all four examples. The handoff also suggests a
dictionary check, which needs a word list Python does not ship — a dependency
decision, and probably unnecessary.

### Parameterize the corpus wrappers — Decision 9
**Owner: Assistant for the scripts, Nick for placement.**

Rename and parameterize so the batch files serve any corpus:

| Current | Becomes |
|---|---|
| `sync_loom.bat` | `sync_gdrive_corpus.bat` |
| `push_loom.bat` | `push_gdrive_corpus.bat` |
| `merge_loom_to_drive.bat` | `merge_corpus_local_to_drive.bat` |
| `pull_matt.bat` | `pull_gdrive_folder.bat` |

Not in the handoff's table but equally Loom-specific: **`digest_all.bat`**,
which hardcodes all three library paths. It is the natural candidate to become
the per-corpus marshaling wrapper. Needs a ruling.

The Python engine already takes paths as arguments, so it is closer to
path-agnostic than the handoff assumes.

Also under this decision: replace the stray `SKILL.md` with
`project-manifest-format.md`. **Already verified** — the manifest is consumed by
`claude_to_markdown.py`, detected by content shape (`project_uuid` +
`conversations`) rather than by filename, and unknown keys are read with
`.get()` and ignored. Adding `manifest_format_version` needs no parser change.

---

## Deferred by design

### Acceptance tiers 1–4 — Decision 1
**Owner: Nick to rule if it is ever wanted.**

Tiers 1–4 turn on one semantic judgment: endorsement versus objection after a
reference. The handoff permits deferring it, and the implementation does defer
— terms fall to whichever structural tier applies (0, 5, 6 or 7) and no tier is
guessed.

Building it would mean either a marker-based approximation or a classifier over
a small set of passages. Neither is needed for the ranking to work.

---

## Findings not yet decisions

### The pipeline does not write `date`
**Owner: Nick to rule on the source of truth, Assistant to build.**

Found by `pipeline_selfcheck.py` on its first run against clean output: every
Markdown file the pipeline writes is missing `date`, one of the four fields
`repository-structure.md` says the pipeline writes and search relies on.

`add_metadata` backfills `modified` (the file's mtime, in UTC) and stamps
`indexed_at`, but never `date`. The two are not interchangeable: `modified` is
when the file was last touched on disk, and `date` is meant to carry the
document's own local timestamp with offset, matching its filename.

The fix is a small backfill; the ruling is what it should draw from, in order
of preference:

1. a date the converter already knows -- a conversation's `create_time`, a
   docx's document properties
2. the timestamp in the filename, where the file follows the convention
3. the file's mtime, converted to the corpus owner's local zone

Sidecars already write `date` correctly, which is why they do not appear in
the finding.

### HTML relative image sources
**Closed.**

`html_to_markdown.make_image_handler` now copies a relative `src=` into
`<basename>_media/` and rewrites the link, alongside the base64 `data:` URLs it
already handled. URL-escaped names resolve, a repeated asset copies once, and a
path escaping the HTML file's own folder is refused rather than followed.

PDF extraction was verified correct and needed no change: embedded images per
page plus attachments, both written to `<basename>_media/` and linked.

### Reference documents contradict the sidecar ruling
**Owner: Nick, in the source conversation.**

`repository-structure.md` v1.10 still says under *Completeness of 2-Digested*
that "the pipeline copies through every file it cannot convert". The glossary
v1.6 says the same. Under the sidecar ruling this is no longer accurate:
`2-Digested` is a complete **catalog** of `1-Raw`, not a complete copy. Media
and export auxiliaries are copied; everything else is represented by a sidecar.

The search skill reads these files, so the wording matters.
