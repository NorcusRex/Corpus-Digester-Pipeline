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
| 4 | Carry the corpora report to AI Methods | Nick |
| 5 | ChatGPT export media — build the fix | Item 2 |
| 6 | Multi-word keywords — PM has ruled it in | Nobody; unscheduled |
| 7 | Index or digest the `RPG` library | Nobody; someday |
| — | Acceptance tiers 1–4 | Out of scope — the reporting skill's job |

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

## 4. Carry the corpora report to AI Methods

```
docs/handoffs/2026-09-25-1951__reference-and-production-corpora.md
```

On the branch, not on `main`. It reports the decision to federate — each
archived project stays its own corpus and a project agent reaches across
several — and the two corpus kinds that follow, Production with four tiers and
Reference with two.

**Three things for the Designer**, all on their side of the line:

1. `repository-structure.md`'s four-tier root check has to become the
   *Production*-corpus check, or `search-project-corpus` will reject every
   Reference corpus as an error. Which shared file carries the notion of corpus
   kind is theirs to decide.
2. The search requirement you accepted — per-corpus exhaustive search,
   corpus-labelled results, no global ranking — needs to land somewhere
   binding, because it is the kind of constraint that gets optimised away by
   someone reasonably trying to make the skill tidier.
3. One open question is genuinely theirs to answer: whether the Drive connector
   can search several roots well. That is the only dependency that could still
   argue against federation.

`search-google-drive` is named in the report as an intention, not a spec.

**Nothing here blocks the pipeline.** Federation is the cheaper option on this
side — each corpus is simply digested, with no cross-corpus mirroring at all.

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

## 6. Multi-word keywords

**Ruled in by Nick, unscheduled.** Real work, nobody blocked, no date.

The requirement existed in `repository-structure.md` v1.11 — "Most keywords are
multi-word" — and vanished when the conventions were split: v2.1 removed the
Frontmatter section and `pipeline-conventions.md` inherited only "a list of
quoted strings". The pipeline emits single words, so nothing is currently
violating a rule; the rule had simply stopped existing. The Designer accepted
the finding and left it out of 2.3 deliberately. When it is picked up, the
requirement belongs in `pipeline-conventions.md`, which the pipeline owns.

**Scope.** Generate n-gram candidates that do not cross punctuation, reject ones
bounded by stopwords, and score them alongside unigrams. TF-IDF handles n-grams
unchanged, and the lexicon already accepts multi-word entries.

**One step of the original sketch is wrong, corrected by the Designer.** It
proposed dropping single words that a chosen phrase covers. That discards
evidence: a word occurring fifty times, ten of them inside a phrase, has earned
its own entry on the other forty. Score phrases and single words independently
and keep both where both earn a place.

**What it is worth.** Better browsing. It would not have prevented the retrieval
failure that started this — that was conjunctive queries and searching in the
wrong vocabulary, both on the searcher's side.

## 7. Index or digest the `RPG` library

**Nick's, deferred to "some day".** No date, nobody blocked.

The library is very large, mostly PDFs, with no corpus structure and no index.
Two depths, and they are not the same job.

**Index in place.** `tier_sidecars.py` already writes a catalogue record beside
a file it must not modify — that is how `4-Canon` works. Pointed at the library
it would leave every PDF byte-identical and produce a findable catalogue. The
limitation is real: it extracts text only from formats it reads cheaply, so
PDFs would get keywords from filename and path alone. Findable by title, not by
content. Wiring in `pdf_to_markdown.py`'s extraction is what would change that.

**Actually mine it.** Nick's own framing, and his estimate of the cost: many of
the games are not OCR'd, so this means OCR across a large collection and
"tremendous work". Nothing is proposed.

The reason to keep the distinction visible is that the first is a day and the
second is a project, and they are easy to conflate when the phrase is "digest
the RPG folder".

---

# Out of scope for the pipeline

## Acceptance tiers 1–4 — Decision 1

**Not deferred work. These belong to the reporting skill, and the pipeline
cannot have them.** Nick's ruling, and it draws the line in the right place.

Tiers 1–4 turn on whether the subject endorsed or objected after referring to
something. The evidence for that is indirect: tone, hedging, what a "yes, but"
is actually conceding, a partial agreement that accepts one clause and rejects
another. An AI reading the passage can weigh it. Procedural code cannot, and a
marker list that pattern-matches "agreed" and "no" would be confidently wrong
on exactly the cases that matter.

So the split is by what each tool can honestly judge:

| | Assigns | How |
|---|---|---|
| **Pipeline** | nothing on this scale | It weights by whose turn a term appears in, not by acceptance |
| **Reporting skill** | tiers 1–4, and the rest | Semantic — an AI reading the exchange |

**The pipeline no longer uses the acceptance scale at all.** It was simplified
to a single question: does this term appear anywhere in the subject's turns?
Yes gets 128, no gets 1. See *Keyword weighting* under the closed items for
why, and for the failure that simplification removed.

Nick has been declaring agreement more explicitly, and has added styles of
partial agreement. Both are for the reporting skill to read. Neither is
something the pipeline attempts to interpret.

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

## Selection, and the three silent failures around it

**Closed.** Four changes, all from one thread: you cannot control what an AI
export contains, so selecting from it is the real work, and three of the ways
it went wrong were silent.

**`subset_inventory.py` is new.** `sync_subset.py` mirrors folders you name;
this reports what the names are. Per selectable folder: file count, Markdown
count, size, and the span of dates it covers. Given selection lists it also
says which lists claim each folder, **which folders nothing claims**, and which
list entries name a folder that is not there.

The unclaimed list is why it exists. A project nobody selected is not an error
anywhere in the pipeline — it simply never reaches a corpus, and the only
symptom is a search finding nothing and being unable to say why. The rest is
convenience.

**The project-name map now says where it looked.** `process_folder.py` printed
nothing at all when `project_names.tsv` was absent — the code comment read
`# Silent skip if TSV doesn't exist`. A mistyped `--rename-tsv` path looked
identical to a successful run. It now prints the path it tried, says plainly
when the file is not there, and points at `--rename-tsv` when the path came
from there.

**And it warns about the symptom, not just the cause.** After the rename pass,
any folder still carrying a raw ChatGPT id (`project_g-p-…`, `gpt_g-…`) is
reported by name. Claude's grouped folders also begin with `project_` but carry
a short UUID and a slug, so the `g-` discriminator separates "not yet named"
from "named differently" without false positives — verified against both
shapes.

**A project-name map beside the wrapper now wins.** The wrapper's own header
claimed configuration files live beside it; for the TSV that was false, since
the code only looked next to `process_folder.py` and the wrapper never passed
`--rename-tsv`. It now passes it when the file is really there, so a corpus can
override and the account-level copy stays the default.

**One selection list per source.** The wrapper called the sync twice with one
shared list. The two exports name their folders differently — Claude's are
`project_<short-uuid>__<slug>` from the manifest, ChatGPT's are whatever the
TSV renamed them to — so every run reported each source's entries as missing
from the other and exited 1. Now `SELLIST_CLAUDE` and `SELLIST_CHATGPT`, each
skipped when empty or absent.

**Two documentation faults found while doing this**, both stating the opposite
of what the code does. `docs/pipeline-guide.md` never said the export archive
is itself a corpus needing its own digest run before anything can select from
it; it now carries the two-corpus flow as a diagram. And
`claude_to_markdown.py`'s docstring said conversations are "flat under
conversations/, not grouped by project", which stopped being true when manifest
recovery was added.

## The shared-file versioning rule

**Closed at `project-manifest-format.md` 1.4**, after two round trips and one
defect in between.

**What was wrong.** The same glossary text was reaching the pipeline stamped
1.6, 2.3, 4.4 and 4.6 — a shared file was carrying whichever version its host
skill bundle happened to be at. A copy's version therefore said nothing about
its content, which is the one thing a version is for in this arrangement: a
file is the only channel between Designer and Developer, so a version mismatch
has to mean drift rather than a variant.

**What was built here.** `references/README.md` states the rule for this side —
a shared file carries its own version, independent of any skill that bundles
it, every copy shows the same version, and the version changes only when the
content does.

**What came back.** The Designer replaced the rule in
`project-manifest-format.md` rather than patching it: the document version and
`manifest_format_version` are stated as independent, either free to move
without the other, with the general principle that a version describes the
thing it is attached to and nothing else.

**And then broke it, once.** 1.3 stated two different versions for itself — 1.3
in the header, 1.2 in the *Versioning* section's own first line, in the section
that had just been rewritten. Found by reading the shipped file, sent back
rather than edited locally, and returned as 1.4 the same day. The fix removes
the duplicate rather than syncing it: the section now says its own version is in
the header. Verified on receipt that the diff is two hunks and nothing else in
the file moved.

**Worth keeping for the pattern**, not the content. The defect was a stale line
left behind by an edit, in the paragraph most about not leaving stale versions
behind; it survived the Designer's own review and was caught by a reader on the
other side of the channel with no stake in the wording. That is the check this
arrangement actually has, and it worked.

## Inconsistencies between the shared reference files

**All three resolved**, two by the Designer in the 2026-09-25 round and one
before it. Recorded because each was found by reading the shipped files against
each other, which is the only check this arrangement gets.

**The sidecar description disagreed with the pipeline.** Resolved before the
round: `corpus-glossary.md` v1.0 says the pipeline "copies through or sidecars
whatever it cannot convert", and `repository-structure.md` says files it cannot
convert "appear as a small Markdown sidecar recording the original's name, type
and source path". Both now match what the code does.

**The corpus was three places or four, depending which file you read.** The
glossary said four — conversation, past conversations, Evernote notes, Drive
repository — and declares itself the file that reconciles disagreements.
`repository-structure.md` v2.1 said three, in two separate places, omitting
Evernote. Resolved in 2.3: the preamble defers to the glossary rather than
restating a corpus definition, and *Project and corpus* names all four. Nothing
in the pipeline depended on the answer — it converts `1-Raw` into `2-Digested`
and never sees a conversation or a live source — but the searcher does.

**The multi-word keyword requirement vanished in the split.** Accepted and
ruled in as pipeline work; now item 6 rather than a reference-file problem.

**51% duplication in `repository-structure.md` v2.1.** Measured here,
independently confirmed upstream, and cut in 2.3 — *The four tiers* and
*Non-tier siblings*, both owned by the glossary, 121 lines down to 97. Checked
before installing that the glossary really does carry what was cut, so the cut
removed a duplicate rather than the only copy.

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

**9.6.** The stray `SKILL.md` is replaced by `project-manifest-format.md`, read
from the `update-project-manifest` skill's own reference folder. The copy that
arrived was stamped **v2.3** — the host skill bundle's version, not the shared
file's, which is the per-bundle stamping bug that set off the versioning work.
The same document is now at 1.3 in `references/`. No parser
change was needed, verified rather than assumed: the manifest is consumed by
`claude_to_markdown.py`, detected by content shape (`project_uuid` +
`conversations`) rather than by filename, and every field is read with `.get()`.
A manifest carrying `manifest_format_version`, every documented field, and
invented keys besides is still recognised correctly. The manifest is recorded
as a named pipeline input in the pipeline guide alongside `project_names.tsv`.

That oddity is what became the versioning rule the Designer rewrote, first for
1.3 and then for 1.4. It is closed; see *The shared-file versioning rule* below.

## Keyword weighting simplified to one question

**Decision 1, as amended by Nick.** The original built an eight-tier weighting
from the acceptance rubric: tier 0 for the subject's own unquoted words, 5 and
6 for terms the assistant introduced and the subject took up, 7 for terms that
never left the assistant. It now asks one thing — does this term appear
anywhere in the subject's turns — and answers 128 or 1.

Two reasons, both Nick's.

**Acceptance is not what keywords need.** Weighting by endorsement requires
reading tone and hedging, and working out what a "yes, but" is conceding. That
is the reporting skill's job. The pipeline should not approximate it.

**Quoting demonstrates stake, not distance.** The old scheme put blockquoted
text in a subject turn at weight 2, near the floor, reasoning that quoting an
assertion does not transfer it. That is right for attribution and wrong for
aboutness: choosing to reproduce a passage is engagement with its terminology,
whoever wrote it first. If the subject later changes terminology, the newer
usage outnumbers the old and comes to dominate on frequency alone.

The simplification also removed the only unreliable input the weighting had.
Blockquote markers depend on re-prefixing pasted text, which nobody does
consistently, and a quotation of Matt, of a past self, or of another chat is
indistinguishable from a quotation of this conversation's assistant. Measured
on a real case, an unmarked external quote put someone else's vocabulary at
full subject weight — 64x too high, in the worst direction. Under the current
rule the question never arises: identical weights with or without markers,
verified.

What survives is structural rather than semantic. In a converted export
`## Human` versus `## Assistant` is ground truth from the export data; in a
speaker-labelled document the labels are explicit. Whose turn a term appears in
is a fact about the file, not an interpretation of it.

## HTML relative image sources

**Closed.** `html_to_markdown.make_image_handler` now copies a relative `src=`
into `<basename>_media/` and rewrites the link, alongside the base64 `data:`
URLs it already handled. URL-escaped names resolve, a repeated asset copies
once, and a path escaping the HTML file's own folder is refused rather than
followed.

PDF extraction was verified correct and needed no change: embedded images per
page plus attachments, both written to `<basename>_media/` and linked.
