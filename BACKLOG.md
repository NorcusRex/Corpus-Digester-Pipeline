# Backlog

Open work and open questions, from the digester handoff (v6.8) and from
findings while implementing it.

**Organised by who is blocked**, not by category, so the live items are at the
top and the finished ones are out of the way. Closed entries are kept rather
than deleted — several of them correct a claim in the handoff, and that
reasoning is worth being able to find.

## At a glance

| # | Item | Blocked on |
|---|---|---|
| 1 | Keyword soft tier — run the audit, then rule | Nick |
| 2 | ChatGPT export media — run the inspection | Nick |
| 3 | `3-Reporting` stamping — rule whether it is needed | Nick |
| 4 | Reference documents contradict the code | Nick |
| 5 | ChatGPT export media — build the fix | Item 2 |
| — | Acceptance tiers 1–4 | Deferred by design |

---

# Waiting on Nick

## 1. Does the keyword filter's soft tier survive contact with the corpus?

**The one to do first.** It is the only open item where the current code could
be quietly doing damage — throwing away real words — and the audit that settles
it takes one run.

Decision 8 is built. Rejection runs in two tiers, and only the second is in
question.

**Hard tests** cover shapes no English word takes: no vowel (counting `w`, so
Welsh survives), letters mixed with digits, `q` not followed by `u`, a letter
three times running, a seven-consonant run. Safe with no other evidence, and
not in doubt.

**Soft tests** are implausible letter sequences — an impossible letter pair, a
six-consonant run — rejected only when nothing vetoes them. A veto is the term
appearing in a lexicon, appearing capitalised mid-sentence, or recurring across
three or more documents.

The soft tier needs judging for two reasons. It is the tier that can throw away
a real word. And it is the tier doing the work: of the four artifacts the
handoff names, the hard tests catch two and the soft tests catch the other two.

**How to settle it.** Run a digest with `--report-artifacts rejected.md`, or the
wrapper's `--audit`. Read the *Soft rejections* table. Anything real in it is a
false positive, and the answer is either a lexicon entry or dropping the tier.

**Why synthetic testing is not enough.** Two false-positive bugs were found and
fixed during implementation, both invisible to the fixtures that were passing at
the time. The first used vowel ratio and threw away `clock`, `clocks` and
`handling` — `kxwoj` and `clock` have identical vowel ratios, so counting vowels
cannot separate them. The second read sentence-initial capitals as evidence of a
proper noun, which protected whatever happened to open a sentence and put `the`
in the harvested name list. A third of the same kind is likelier than not.

**On the dictionary.** It is currently unexercised. With no lexicon, no corpus
statistics and no body text, the present tests catch all eight test artifacts
and lose none of twenty-four real words, so nothing in testing has yet needed a
veto. Its value is protection for real words the test set does not contain,
which is exactly what the audit will reveal. An earlier claim that the
dictionary was "earning its place" was made about the vowel-ratio version and
was not revisited after that version was replaced; it was also circular, since
the dictionary passed to that test was built from the test's own answer key.

## 2. ChatGPT export media — run the inspection

Run `inspect_chatgpt_assets.py` against one real ChatGPT export and paste the
output. It is read-only and prints no conversation text — only content types,
the keys each carries, sample pointer identifiers, and whether those match
files on disk.

```
python inspect_chatgpt_assets.py "<export folder>" --report assets.txt
```

Needed because the export format has changed across ChatGPT versions, and the
pointer-to-file mapping should be known rather than guessed. Unblocks item 5.

## 3. `3-Reporting` stamping — Decision 2

May be unnecessary. The `write-report` skill now writes frontmatter in the same
format, so reports arrive already stamped. The open question is whether enough
hand-written or pasted material reaches `3-Reporting` to justify a stamping
pass at all. That is a question about your filing habits, not about the code.

`4-Canon` is settled and needs no ruling: no stamping, ever. Released artifacts
are catalogued by companion sidecars (`tier_sidecars.py`) which leave the
artifact byte-identical.

## 4. Reference documents contradict the code

To take back to the source conversation. A message covering all of this was
drafted and sent separately.

**The sidecar ruling.** `repository-structure.md` v1.10 still says under
*Completeness of 2-Digested* that "the pipeline copies through every file it
cannot convert". The glossary says the same. Under the sidecar ruling this is
no longer accurate: `2-Digested` is a complete **catalog** of `1-Raw`, not a
complete copy. Media and export auxiliaries are copied; everything else is
represented by a sidecar. The search skill reads these files, so the wording
matters.

**A version-numbering question**, for whoever maintains the reference files.
`project-manifest-format.md` is headed **Version 2.3** but its example manifest
carries `"manifest_format_version": "1.0"`, while its *Versioning* section says
the two numbers move together. Three claims that cannot all hold.

The likely explanation is that the header number is a **bundle** version,
stamped across every reference file at once, rather than a version of that
document. The evidence is strong: the same glossary text now carries **1.6** in
the copy given to this session, **2.3** in the `update-project-manifest` skill
bundle, and **4.4** in the `write-report` skill bundle, the files being
otherwise identical line for line.

If that reading is right, the manifest format really is at 1.0, the example is
correct, and the sentence claiming the two versions track each other is the
error. Nothing for this pipeline either way — it ignores the field — but anyone
writing a validator would not know which number to expect.

---

# Waiting on me

## 5. ChatGPT export media — build the fix

**Blocked on item 2.**

`chatgpt_to_markdown.extract_text` discards the multimodal content dict,
emitting `[<content_type> content omitted]` and dropping the `asset_pointer`
field that sits in it. The link between a conversation and its images exists in
the export and the converter throws it away. This is the path covering the
1,446 uncarried files.

The Claude side is better placed — `render_files` already reads `file_name` and
`file_uuid`.

---

# Deferred by design

## Acceptance tiers 1–4 — Decision 1

Tiers 1–4 turn on one semantic judgment: endorsement versus objection after a
reference. The handoff permits deferring it, and the implementation does defer
— terms fall to whichever structural tier applies (0, 5, 6 or 7) and no tier is
guessed.

Building it would mean either a marker-based approximation or a classifier over
a small set of passages. Neither is needed for the ranking to work.

---

# Operational notes

Awareness rather than work.

## Source identity only populates on re-digestion

`source_sha256` and `source_bytes` are written at digestion time, so existing
digested output does not carry them. Until a re-run, a renamed source still
reports as absent rather than as a rename — correctly, since there is nothing
to match on. No action needed beyond knowing why the first run after this
change reports differently from the one before it.

Found the hard way: `Creatures (Abortions)：  Undead.docx` was reported as
having no source in `1-Raw`, when the raw file had simply been renamed to
`Creatures (Aberrations)：  Undead.docx`. Under the old delete behaviour a
spelling fix would have destroyed good output.

---

# Closed, with the evidence

Kept because the reasoning is worth finding again, not because anything is
pending.

## docx unresolved drawings — Decision 7

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

**Closed across the whole corpus.** Every affected document was swept, matching
each digested file's marker count against its source's `word/media` entries,
its `document.xml.rels` image relationships, and its recorded
`images_extracted`.

Of roughly 185 affected documents, only 20 carry any media at all, 50 files
between them. In every one, `images_extracted` equals the number of image
relationships in the document body: **the converter has never failed to extract
an image the body references.** There is no extraction bug, and the highest
marker counts (433, 197, 115, 99, 83) sit on documents with no media
whatsoever.

Eight image files across six documents exist in the package without being
referenced from `document.xml`. Spot-checking the largest
(`Core Mechanic and Probability System.docx`, 9 in the package, 8 referenced):
the eight referenced are ~180 KB matplotlib charts, extracted and linked
correctly, and the ninth is a **70-byte PNG** — a 1x1 pixel, the kind of
spacer that arrives with pasted HTML. The file also carries `header1`/`header2`
relationship parts, so header decoration is the other candidate for that class.

No frontmatter counter was added for them. A field reporting eight
pixel-spacers and header graphics as unreferenced would imply a loss that did
not occur, which is worse than silence.

## Pipeline self-check — Decision 5

**Built** as `pipeline_selfcheck.py`. All six checks: unconverted files, index
integrity, frontmatter presence, filename conformance, duplicate content by
normalized token windows, and suggest-never-delete. `4-Canon` is exempt from
the frontmatter check.

The completeness check is well-defined because every file in `1-Raw` lands in
exactly one of three states in `2-Digested`: converted, copied through, or
represented by a sidecar carrying `source_path`.

Duplicate detection fingerprints several windows through each document, not
only the head — a pasted copy may begin at a different point than an export of
the same conversation. Where candidates differ, the passages present in one and
not the other are reported: **that is where hand-added commentary lives and it
must not be lost to deduplication.**

## The pipeline does not write `date`

**Built.** Found by `pipeline_selfcheck.py` on its first run against clean
output: every Markdown file the pipeline wrote was missing `date`, one of the
four fields `repository-structure.md` says the pipeline writes and search
relies on. `add_metadata` backfilled `modified` (mtime, UTC) and stamped
`indexed_at`, but never `date`, which is meant to carry the document's own
local timestamp with offset, matching its filename.

Resolved from three sources in order, with the one used recorded in
`date_source`:

1. a date the converter already knows — a conversation's `create_time`, a
   docx's document properties
2. the timestamp in the filename, where the file follows the convention
3. the file's mtime, converted to the corpus owner's local zone

PDF dates are parsed with their timezone offset honoured rather than dropped,
which would otherwise land a PDF written elsewhere hours out. A file that
already carries `date` is left alone.

## Parameterize the corpus wrappers — Decision 9

**Built**, including 9.6. The Loom-specific batch files were replaced by
generic ones taking the corpus root and remote as parameters:

| Was | Became |
|---|---|
| `sync_loom.bat` | `sync_gdrive_corpus.bat` |
| `push_loom.bat` | `push_gdrive_corpus.bat` |
| `merge_loom_to_drive.bat` | `merge_corpus_local_to_drive.bat` |
| `pull_matt.bat` | `pull_gdrive_folder.bat` |
| `digest_all.bat` | `corpus_wrapper.template.bat` |

`digest_all.bat` was not in the handoff's table but hardcoded all three library
paths, and became the per-corpus marshaling wrapper. No corpus name, local path
or Drive path appears in any generic script; rclone is found through
`RCLONE_EXE`, the `PATH`, or a default, by one shared preamble rather than four
copies of the same check.

**9.6.** The stray `SKILL.md` is replaced by `project-manifest-format.md` v2.3,
read from the `update-project-manifest` skill's own reference folder. No parser
change was needed, verified rather than assumed: the manifest is consumed by
`claude_to_markdown.py`, detected by content shape (`project_uuid` +
`conversations`) rather than by filename, and every field is read with `.get()`.
A manifest carrying `manifest_format_version`, every documented field, and
invented keys besides is still recognised correctly. The manifest is recorded
as a named pipeline input in the pipeline guide alongside `project_names.tsv`.

The version-numbering oddity found while doing this is under item 4, since it
goes back to the same place.

## HTML relative image sources

**Closed.** `html_to_markdown.make_image_handler` now copies a relative `src=`
into `<basename>_media/` and rewrites the link, alongside the base64 `data:`
URLs it already handled. URL-escaped names resolve, a repeated asset copies
once, and a path escaping the HTML file's own folder is refused rather than
followed.

PDF extraction was verified correct and needed no change: embedded images per
page plus attachments, both written to `<basename>_media/` and linked.
