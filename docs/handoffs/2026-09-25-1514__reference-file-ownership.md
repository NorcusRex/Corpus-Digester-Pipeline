---
title: "Handoff — Reference File Ownership and the repository-structure Cut List"
date: 2026-09-25T15:14-07:00
source: "Claude Code session, Corpus-Digester-Pipeline repository"
model: Claude Opus 5
keywords: ["shared reference files", "canonical source", "repository-structure", "duplication", "requirements versus mechanisms"]
---

# Handoff: Reference File Ownership and the `repository-structure` Cut List

2026-09-25 · Source: Claude Code session, Corpus-Digester-Pipeline repository · Claude Opus 5
Middling compression, prose with tables. For the AI Methods conversation.

**Abstract.** The conventions split is applied in the pipeline repository and
the bundle's findings are reconciled against the code. Two things need doing on
the design side. `repository-structure.md` v2.1 restates content that
`corpus-glossary.md` v1.0 owns — 51% of it by line count, measured — and in one
place contradicts it. A cut list is proposed. Separately, the canonical source
of the two shared files is confirmed as the claude.ai side, with the pipeline
repository holding read-only copies.

## Canonical source, confirmed

`corpus-glossary.md` and `repository-structure.md` are design artifacts. The
AI Methods project and the skill bundles are canonical; the pipeline repository
holds read-only copies and never edits them. If the pipeline needs one changed
it is raised there and comes back as a new version.

`pipeline-conventions.md` is the exception and is now repository-owned, edited
freely as the code changes, read by nothing else.

This is recorded in the repository at `references/README.md`, with a table of
each file's version and the date received, so a version mismatch is visible
rather than silent.

## Who owns which fact

A fact both sides need lives in a shared file. A fact one side needs lives in
that side's own file. Nobody copies.

| Fact | Document | Authority |
|---|---|---|
| Vocabulary — corpus, tier, sidecar | `corpus-glossary.md` | Chat/Design |
| `_index.json` format | `repository-structure.md` | Chat/Design |
| "`2-Digested` covers everything in `1-Raw`" | `repository-structure.md` | Chat/Design |
| Durability tiers, Drive ID handling | `repository-structure.md` | Chat/Design |
| Filenames, frontmatter fields, skip list, keyword weighting | `pipeline-conventions.md` | Code |
| Sidecar contents, media handling, orphan detection | `pipeline-conventions.md` | Code |

**Requirements are Chat/Design's. Mechanisms are Code's.** The test for which a
statement is: *if the pipeline changed how it did this, would the searcher have
to change?* If not, it is a mechanism and belongs with the code.

This is exactly where the copy-through wording went wrong. v1.10 and v1.11
stated a mechanism, so when the mechanism changed the document became false —
for days — while the requirement it was reaching for, that nothing is silently
dropped, never stopped holding.

## The index format stays in `repository-structure.md`

Worth stating explicitly, because the first instinct was the opposite. The
search skill reads `_index.json` before anything else, so the format is an
interface between two parties rather than a pipeline internal. It belongs in
the document both of them hold.

The correction went the other way instead: `pipeline-conventions.md` has been
edited to reference the format rather than restate it, and now records only
what the pipeline decides about its own output — when the index is written,
that it lists Markdown only, that `.nlm.md` is excluded.

## Cut list for `repository-structure.md` v2.1

Measured by section, 58 of 114 lines restate content held elsewhere. Three
sections should go; the rest should stay.

**Cut — `corpus-glossary.md` v1.0 already owns these:**

| Section | Lines | Note |
|---|---|---|
| The four tiers | 19 | Glossary's `Tier` entry covers it |
| Non-tier siblings | 11 | Glossary's `Utility siblings` covers it |
| The corpus definition in the preamble | ~4 | **And contradicts the glossary — see below** |

**Keep:**

| Section | Why |
|---|---|
| Durability tiers | Searcher-only; nothing else states it |
| Which tiers carry an index | The interface both parties parse |
| What a searcher can rely on | The consumer's side of the contract, legitimately distinct from the producer's statement of it |
| Who writes what | The ownership model itself |
| Project and corpus | Search priority; searcher-only |

That is roughly 34 lines out of 114, and removes every statement that has two
homes.

## A live contradiction

`corpus-glossary.md` v1.0 says the corpus is **four** places — the current
conversation, past conversations, **Evernote notes**, and the Drive repository —
and declares itself the file that reconciles disagreements.

`repository-structure.md` v2.1 says **three**, in its *Vocabulary* paragraph
and again in *Project and corpus*, omitting Evernote. Both shipped in the same
bundle.

Cutting the preamble's corpus definition resolves it in one move, since the
glossary is authoritative on vocabulary anyway.

## The three layers, and why they are worth protecting

`repository-structure.md` states a requirement → `pipeline-conventions.md` says
how it is met → `pipeline_selfcheck.py` verifies it on every run.

Each layer has one owner, and the bottom one mechanically enforces the top one.
v2.1 already says as much: "which is why the pipeline's self-check tests it
rather than assuming it." That loop is the thing that keeps a requirement from
quietly becoming false, and it is nearly complete — the cut list is mostly about
stopping the top layer from duplicating the middle one.

## The versioning rule needs one more fix

`project-manifest-format.md` v1.1 arrived and is installed. Its change is
framing only — the document stopped naming the digestion pipeline as *the*
consumer and now presents it as one worked example. Structure, fields, ordering
and encoding are byte-identical to v1.0, and the pipeline needed no change.

That revision quietly breaks the document's own rule, which is worth fixing
before it causes a third round of confusion.

The document is now **v1.1**. The format it describes is still **1.0**, and the
example still reads `"manifest_format_version": "1.0"`. That is the right
outcome: the wire format did not change, so bumping the field would have
signalled a change that did not happen. But the *Versioning* section says:

> The version in this document and the value of `manifest_format_version` move
> together: this document at v1.0 describes `"manifest_format_version": "1.0"`.

A v1.1 document describing format 1.0 is exactly what that rule says cannot
exist.

**The rule is what is wrong, and this revision is the proof.** Documents get
revised for reasons that have nothing to do with the wire format — decoupling
the manifest from its one named consumer improved the document and had no
business touching the format. Coupling the two numbers means either the format
version inflates for editorial changes, or the rule is broken every time the
prose is improved. Both have now happened: the earlier confusion was a host
skill's version stamped on the header, and this one is an editorial revision
with nowhere to go.

**Suggested fix.** Drop the "move together" sentence and state the mapping
explicitly instead:

> This document is version 1.1 and describes `manifest_format_version` **1.0**.
> The two are independent: the document version changes whenever this file
> changes, and the format version changes only when the JSON a consumer must
> parse changes.

That lets either move without lying about the other, and a reader can always
tell which number is which. It is also the same principle the shared-file rule
already establishes — a version describes the thing it is attached to, and
nothing else.

The distinction is recorded in the pipeline repository's `references/README.md`
so a reader there is not misled by the stale rule inside the file itself.

## One smaller item

**The multi-word keyword requirement disappeared in the split.**
`repository-structure.md` v1.11 said "Most keywords are multi-word". v2.1
removes the whole Frontmatter section, and `pipeline-conventions.md` inherited
only "a list of quoted strings", so the requirement now exists nowhere.

The pipeline emits single words, so this closes the gap by accident rather than
by decision. If multi-word keywords are wanted, the requirement belongs in
`pipeline-conventions.md` and the work is real: n-gram candidates that do not
cross punctuation, rejecting ones bounded by stopwords, scored alongside
unigrams, then dropping single words a chosen phrase covers. TF-IDF handles
n-grams unchanged and the lexicon already accepts multi-word entries.

## Provenance

**Nick's own position.** That the canonical source of both shared files is the
claude.ai side, both being design artifacts. That the `Owner` column should
distinguish Chat/Design from Code authority. That the three-layer loop is worth
protecting and should be recorded in the handoff notes.

**The reporter's, established by measurement.** The 51% duplication figure and
the section-by-section breakdown, from comparing v2.1 against `corpus-glossary`
v1.0 and `pipeline-conventions` v1.1. The corpus three-versus-four
contradiction. That the search skill reads `_index.json` first, which is what
settled the index format's ownership.

**The reporter's, not ruled on** (user-acceptance tier 7 — Indeterminate). The
cut list itself. The requirements-versus-mechanisms test as the way to decide
future placements.

## Sources

### S1 — Bundle: pipeline-handoff-bundle
- Type: zip supplied to the pipeline session
- Locator: supplied in conversation 2026-09-25; no URL
- Note: source of `repository-structure.md` v2.1, `corpus-glossary.md` v1.0 and the conventions-split handoff

### S2 — Repository: Corpus-Digester-Pipeline
- Type: git repository
- Locator: https://github.com/NorcusRex/Corpus-Digester-Pipeline
- Version: branch `claude/vigilant-davinci-amht34`
- Accessed: 2026-09-25

### S3 — Skill bundle: search-project-corpus
- Type: .skill archive supplied to the pipeline session
- Locator: supplied in conversation 2026-09-25; no URL
- Note: `SKILL.md` line 115, "read `_index.json`", is the evidence for index-format ownership
