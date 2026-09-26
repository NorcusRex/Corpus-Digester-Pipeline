# Corpus Digester Pipeline

Local Python that converts a corpus's raw material into a searchable digested
tier: it reads `1-Raw`, writes `2-Digested`, stamps frontmatter, extracts
keywords, and maintains an index. It runs offline, has no agent in it, and
depends on nothing outside the standard library except `pypdf`, which is
optional.

One engine serves every corpus. Paths, selection lists and glossaries are
per-corpus configuration, supplied by a thin wrapper.

## The four tiers

Every corpus has these four folders directly beneath its root:

| Tier | Holds | Written by |
|---|---|---|
| `1-Raw` | Incoming material, any format, any path | You |
| `2-Digested` | Converted, classified, indexed output | This pipeline |
| `3-Reporting` | Authored reports and commentary | You |
| `4-Canon` | Released artifacts | You |

Only these four names are fixed. Everything below them is enumerated at
runtime, never resolved by a name seen before.

`2-Digested` accounts for **every** file in `1-Raw`. Each raw file reaches it
one of three ways: converted to Markdown, copied through unchanged (media and
AI-export auxiliary files), or represented by a Markdown **sidecar** naming the
original and its path. Nothing is dropped silently, which is what lets search
read three tiers and treat `1-Raw` as an escape hatch for originals.

## Quick start

```
python process_folder.py <corpus>/1-Raw <corpus>/2-Digested --corpus-root <corpus>
```

In practice you run a per-corpus wrapper instead, which supplies the paths and
calls everything in order. Copy `corpus_wrapper.template.bat` into a corpus's
`_Tools/`, edit the configuration block at the top, and run it.

## What converts

| Source | Output |
|---|---|
| `.docx` | `<stem>.md` + `<stem>_media/` for images |
| `.xlsx` | `<stem>.md` |
| `.pdf` | `<stem>.md` + `<stem>_media/` for images and attachments |
| `.html` | `<stem>.md` + `<stem>_media/` for inline and relative images |
| `.rtf` | `<stem>.md` |
| ChatGPT export | one `.md` per conversation, grouped by project |
| Claude export | one `.md` per conversation, grouped by project |
| `.md` | copied as-is |
| `.txt` | wrapped with frontmatter |
| anything else | `<name.ext>.md` sidecar recording the original |

## The scripts

**Engine** — takes paths, knows no corpus:

| Script | Does |
|---|---|
| `process_folder.py` | Walks `1-Raw`, converts everything, writes the index |
| `add_metadata.py` | Frontmatter, keywords, provenance classification |
| `clean_stale.py` | Reports digested files whose source cannot be found |
| `pipeline_selfcheck.py` | Six checks over the pipeline's own output |
| `tier_sidecars.py` | Catalogues an authored tier without modifying it |
| `stamp_tier.py` | Fills in missing frontmatter on an authored tier's Markdown |
| `sync_subset.py` | Mirrors a selected subset of digested conversations |
| `subset_inventory.py` | Reports what a digested archive offers for selection, and what nothing selects |
| `split_export.py` | Splits an AI export into per-project exports before any conversion |
| `chatgpt_assets.py` | Resolves a ChatGPT export's asset pointers to the files beside it |
| `inspect_chatgpt_assets.py` | Reports how an export references its media |
| `*_to_markdown.py` | The converters |

**Wrappers** — generic, parameterized:

| Script | Does |
|---|---|
| `corpus_wrapper.template.bat` | **Copy this per corpus.** Runs everything in order |
| `push_gdrive_corpus.bat` | Push a corpus to its Drive mirror |
| `merge_corpus_local_to_drive.bat` | First reconciliation, with dry-run passes |
| `pull_gdrive_folder.bat` | Pull a shared Drive folder, exporting Docs as `.docx` |
| `sync_gdrive_corpus.bat` | Mirror selected AI conversations into a corpus |

## Two things it will not do

**It never deletes.** `clean_stale.py` reports; `pipeline_selfcheck.py` has no
deletion path at all. Removing anything takes an explicit flag and, above a
threshold, a second one. An absent source is not evidence that output is stale
— a source may have been renamed, or cleared on purpose to reclaim disk — so
absence is reported, never acted on.

**It never modifies `4-Canon`.** Released artifacts are catalogued by companion
sidecars that leave the artifact byte-identical. No frontmatter is stamped into
them and no generated index block is inserted into their prose.

## Keywords

Keywords are ranked by TF-IDF across the corpus. For documents that can be
classified as conversations, each term's count is first weighted by **whose
turns it appears in**: a term the corpus owner used anywhere in their own turns
carries far more weight than one only the assistant ever used. So what a
document is *about* reflects what the owner engaged with rather than raw word
frequency.

Quoting counts as engagement. Choosing to reproduce a passage is an act of
engagement with its terminology, whoever first wrote it, so quoted text weighs
the same as any other text in the owner's turns. That also means the weighting
does not depend on blockquote markers, which nobody adds consistently.

Conversion debris is filtered out. Before trusting that filter on a new corpus,
run a digest with `--report-artifacts rejected.md` and read what it dropped —
anything real in there is a false positive. See [`lexicon/`](lexicon/README.md)
for supplying word lists and project glossaries that protect real terms.

## Documentation

| File | Covers |
|---|---|
| [`pipeline-conventions.md`](pipeline-conventions.md) | **What this pipeline writes.** Filenames, frontmatter, sidecars, skip list, completeness |
| [`docs/quickstart.md`](docs/quickstart.md) | Running the batch files |
| [`docs/pipeline-guide.md`](docs/pipeline-guide.md) | Full reference, including named pipeline inputs |
| [`docs/brief-part-1-pipeline-and-libraries.md`](docs/brief-part-1-pipeline-and-libraries.md) | Design history: the pipeline and libraries |
| [`docs/brief-part-2-conversation-research-project.md`](docs/brief-part-2-conversation-research-project.md) | Design history: conversation research |
| [`references/README.md`](references/README.md) | Canonical source of the shared files, and who owns which fact |
| [`references/corpus-glossary.md`](references/corpus-glossary.md) | Shared vocabulary: corpus, repository, tier, sidecar, index |
| [`references/repository-structure.md`](references/repository-structure.md) | What a searcher finds — the contract this pipeline must satisfy |
| [`references/project-manifest-format.md`](references/project-manifest-format.md) | Format contract for the project manifest |
| [`docs/conventions-split-handoff.md`](docs/conventions-split-handoff.md) | Why conventions live in three documents with three owners |
| [`docs/handoffs/`](docs/handoffs/) | Notes written for the AI Methods conversation |
| [`lexicon/README.md`](lexicon/README.md) | Word lists and glossaries |
| [`BACKLOG.md`](BACKLOG.md) | Agreed but unbuilt, and what waits on a ruling |

## Requirements

Python 3.10 or later. `pypdf` for PDF conversion; without it PDFs are reported
as skipped and everything else still runs. No other dependencies.
