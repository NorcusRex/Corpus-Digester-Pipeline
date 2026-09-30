# Designer Response — 2026-09-25

*Received from the AI Methods conversation as the cover note to a bundle
carrying `repository-structure.md` 2.3 and `project-manifest-format.md` 1.3.
Reproduced verbatim; kept as the record of what was decided upstream and why.
One defect found on receipt is noted at the foot.*

Answers `2026-09-25-1514__reference-file-ownership.md`. Two files, both
read-only copies in the pipeline repository. Replace wholesale.

| File | Was | Now |
|---|---|---|
| `repository-structure.md` | 2.1 | **2.3** |
| `project-manifest-format.md` | 1.1 | **1.3** |

**`corpus-glossary.md` is unchanged at v1.0.** It is not in this bundle and
needs no action.

## repository-structure.md 2.3

**Cut list applied.** The measurement was confirmed independently before
acting — *The four tiers* 19 lines, *Non-tier siblings* 11. Both removed. The
file is 99 lines, down from 121. A short *Scope* section points at
`corpus-glossary.md` for vocabulary.

**The contradiction is resolved.** It was real, and in two places rather than
one: the preamble's vocabulary paragraph and the closing *Project and corpus*
section both said three sources. The preamble now defers to the glossary
instead of restating a corpus definition, and *Project and corpus* names all
four, Evernote included.

**Everything on the keep list is kept** — durability, the index format, what a
searcher can rely on, who writes what, project and corpus.

## project-manifest-format.md 1.3

**The rule is replaced, not patched.** Diagnosis accepted: the rule was wrong
and an editorial revision proved it. The *Versioning* section now states the
mapping explicitly — this document is 1.3 and describes
`manifest_format_version` **1.0** — and says the two are independent, the
document version changing whenever the file changes and the format version only
when the JSON a consumer must parse changes.

**The wire format is unchanged.** `manifest_format_version` is still `"1.0"`.
No pipeline change follows.

## Two items not in these files

**Multi-word keywords — backlog, not this round.** The observation is accepted:
the requirement existed in `repository-structure.md` v1.11, vanished in the
split, and the pipeline emits single words. PM has ruled it a backlog item. It
improves browsing, and would not have prevented the retrieval failure, which
was caused by conjunctive queries and by searching in the wrong vocabulary.

**One correction to that item's spec, for when it is picked up.** The proposed
step "drop single words a chosen phrase covers" is wrong. A word occurring
fifty times, ten of them inside a phrase, has earned its own entry; dropping it
discards forty occurrences of evidence. Score phrases and single words
independently and keep both where both earn a place.

## Changes on the skill side, for context

Not shared files; listed so the pipeline knows what the searcher now does.

`search-project-corpus` reports the **exact queries used**, not only the
results — a thin conjunctive result looks the same whether material is absent
or the query excluded it, and the searcher is the party least able to notice
the difference. On a second pass, when the first answer did not satisfy, it
reports its method before searching again: sources covered, exact queries,
what was read against what was swept, and the coverage denominator.

---

## Found on receipt — not part of the original note

`project-manifest-format.md` 1.3 carries two different versions of itself. The
header says **Version 1.3**, the README above says 1.3, and the *Versioning*
section's own first line says "This document is version 1.2". The stale line is
almost certainly the body one, since the cover note describes 1.2 as the
editorial revision that exposed the bad rule and 1.3 as its replacement.

Not corrected here: shared files are replaced wholesale, never edited locally.
Raised for the next round. See `BACKLOG.md` item 4.
