# Reference files

Copies of documents this repository **reads but does not own**.

## Three roles

| Role | Who | Authority |
|---|---|---|
| **PM** | Nick | Rules on scope and priority; carries files between the other two |
| **Designer** | the AI Methods conversation | Owns the shared reference files — requirements, vocabulary, contracts |
| **Developer** | this repository | Owns the code and `pipeline-conventions.md` — mechanisms |

Designer and Developer do not talk to each other. Every change crosses through
PM as a file. That is why versions matter here: a file is the only channel, so a
stale copy is an unnoticed disagreement.

## The rule

**Never edit anything in this folder.** These are shared reference files. Their
canonical source is the AI Methods project and the skill bundles on the
claude.ai side, where they are design artifacts. A copy that has been edited
locally is worse than no copy, because it looks authoritative and is not.

If the pipeline needs one of these changed, raise it there. The change comes
back as a new version, and the copy here is replaced wholesale.

A shared file carries its own version, independent of any skill that bundles
it. Every copy must show the same version, and the version changes only when
the content does. So a version mismatch between this folder and the canonical
source is drift, not a variant.

## What is here

| File | Version | Received | Canonical owner | Why the pipeline holds it |
|---|---|---|---|---|
| `corpus-glossary.md` | 1.0 | 2026-09-25 | AI Methods / `search-project-corpus` | Vocabulary the pipeline uses: corpus, repository, tier, sidecar, index, manifest |
| `repository-structure.md` | 2.3 | 2026-09-25 | AI Methods / `search-project-corpus` | The contract the pipeline owes the searcher, and the `_index.json` format both parse |
| `project-manifest-format.md` | 1.3 | 2026-09-25 | AI Methods / `update-project-manifest` | Format of a real pipeline input, consumed by `claude_to_markdown.py` |

All three are current as of the dates above.

### What the last round settled

The three requests in `docs/handoffs/2026-09-25-1514__reference-file-ownership.md`
came back answered on 2026-09-25. The Designer's cover note is kept verbatim at
`docs/handoffs/2026-09-25__designer-response.md`.

- **`repository-structure.md` 2.3** applies the cut list. The vocabulary
  sections are gone and a short *Scope* section points at `corpus-glossary.md`
  instead; 121 lines down to 97. Verified before installing that the glossary
  does carry what was cut — the four tiers and the utility siblings are both
  defined there — so the cut removed duplication rather than the only copy.
- **The corpus is four places.** Both places `repository-structure.md` said
  three now defer to the glossary or name all four, Evernote included.
- **`project-manifest-format.md` 1.3** replaces the versioning rule rather than
  patching it. The document version and `manifest_format_version` are now
  stated as independent. The wire format is unchanged at `1.0`, so no pipeline
  change follows.
- **`corpus-glossary.md` stays at 1.0.** Unchanged and needing no action.

**One defect came with it.** `project-manifest-format.md` 1.3 gives two
different versions for itself: the header says 1.3, its *Versioning* section
says "This document is version 1.2". The body line is the stale one on the
Designer's own account of the sequence. Installed as received rather than
corrected, per the rule above, and raised for the next round — see `BACKLOG.md`
item 4.

**Still true, and worth knowing when reading `project-manifest-format.md`:** the
document's version and the format's version are not the same number. The
document is at 1.3; the format it describes is at 1.0.

## What is not here

**`pipeline-conventions.md`** lives at the repository root, not in this folder,
because this repository owns it. Nothing else reads it and it is edited freely
as the code changes. It is the one conventions document that is not shared.

**`docs/conventions-split-handoff.md`** records why conventions are split
across three documents with three owners. History rather than reference.

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

Requirements are Chat/Design's. Mechanisms are Code's. The test for which one a
statement is: *if the pipeline changed how it did this, would the searcher have
to change?* If not, it is a mechanism and belongs with the code.

## How the three layers close

`repository-structure.md` states a requirement → `pipeline-conventions.md` says
how it is met → `pipeline_selfcheck.py` verifies it on every run.

Each layer has one owner and the bottom one mechanically enforces the top one.
That loop is what keeps a requirement from quietly becoming false, which is
what happened when the completeness wording described copy-through for days
after the pipeline had moved to sidecars.
