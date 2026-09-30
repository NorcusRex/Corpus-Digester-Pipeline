# Designer Response — federation

*Received from the AI Methods conversation as the cover note to
`corpus-glossary.md` 1.1 and `repository-structure.md` 2.4. Reproduced
verbatim. Two things noted on receipt are recorded at the foot.*

Answers `2026-09-25-1951__reference-and-production-corpora.md`. Two shared
files, read-only copies in this repository. Replace wholesale.

| File | Was | Now |
|---|---|---|
| `corpus-glossary.md` | 1.0 | **1.1** |
| `repository-structure.md` | 2.3 | **2.4** |

## The open dependency is answered: federation stands

You flagged "whether the Drive connector can search several roots well" as the
one dependency that could argue against federation, and assigned it to the
Designer. **It is dissolved by Nick's own strengthening of the rule.**

Both degradation mechanisms you named require pooling. A shared result budget
only starves a corpus if there is one budget; incomparable scores only mislead
if scores are merged. Searching each corpus separately and reporting the sets
separately means neither can occur. Cost is linear in the number of corpora —
slower, not less effective, which is exactly Nick's position.

**Incidentally, federation is already the state.** Four `1-Raw` folders exist on
Drive under four different roots. Nothing had to be built for corpora to be
plural; only the searcher had to be told.

## Which file carries corpus kind — both, split by role

The established pattern holds: the glossary defines vocabulary, and
`repository-structure.md` carries the rule a searcher applies.

**`corpus-glossary.md` 1.1** gains Production corpus, Reference corpus, and the
primary/secondary axis, stated as independent of the first. "One project, one
corpus" is made precise: one **Production** corpus, and zero or more Reference
corpora.

**`repository-structure.md` 2.4** takes your smaller-edit suggestion rather
than a kind system, and it was the right call. Verification now checks that
`1-Raw` and `2-Digested` sit beneath a root; the two authored tiers additionally
present means Production, absent means Reference, and neither of the first two
means it is not a corpus at all. That preserves the original intent — do not
search a folder that is not a corpus — with three lines rather than a taxonomy.

## The search rule is in the skill, as a requirement

`search-project-corpus` 1.27 carries Nick's form: search each corpus separately
and exhaustively, report separate sets per corpus, never merge and never rank
across them, and leave the merge decision to the user.

Your point about it being easier to implement than the weaker rule is recorded
in the skill — there is nothing to interleave, so there is no judgment to get
wrong.

**Search priority across corpora** was open in your note. Primary first, then
secondary in the order project instructions name them — but since the sets stay
distinct, that is reporting order rather than precedence. Nothing is suppressed
by coming second, which is why the question turned out to be smaller than it
looked.

## The RPG library is a Reference corpus, and this closes three of your open items

PM corrected the premise after your note was written: the RPG archive does not
need a non-corpus search skill. It was designed as a corpus, before the word
existed.

`I:\RPG\_SearchLibrary\` already carries `1-Raw` and `2-Digested`, with a
`batch_ocr.bat` pointing at the raw tier and placeholder files in each. No
project produces into it. **That is a Reference corpus under the definition in
`corpus-glossary.md` 1.1** — the shape was built first and the vocabulary caught
up.

It was scoped in the *Reconstructing the digestion pipeline* conversation,
Phase 2c: a copy-then-OCR-then-digest workflow using `ocrmypdf --skip-text`, so
text PDFs are left alone and only scans are OCR'd. The word *copy* carries the
selection — `1-Raw` is a destination you copy chosen books into, not the archive
itself.

**Three consequences for your open list:**

**`search-google-drive` loses its motivating case.** It was proposed for Drive
trees that are not corpora, and the example turned out to be a corpus.
`search-project-corpus` covers it unchanged. Park the idea until a genuine
non-corpus tree needs searching; your argument about the missing index layer
still stands and can be picked up then.

**Your `tier_sidecars.py` proposal is not needed here.** Indexing a tree in
place was the answer to "a large collection with no corpus structure." This
collection has corpus structure, so it gets ordinary digestion.

**The OCR obstacle is much smaller than recorded.** Your note carried "~23,000
files, ~19,000 PDFs" and PM's "tremendous work". The current estimate is around
1,000 games in the archive with **fewer than 100** wanted in the corpus. A
hundred books, many already text-based, is an overnight run rather than a
project.

## Not answered here

Nothing from your note remains open on the Designer side. The reversibility
observation in your commentary — federation to distribution is cheap, the
reverse is not — was put to PM directly, as you suggested by flagging it.

**Your reversibility observation** — federation to distribution is cheap,
distribution to federation is not — is the strongest point in your commentary
and was not part of what Nick ruled on. Worth putting to him directly rather
than leaving in a commentary section.

---

## Noted on receipt — not part of the original note

**A figure is attributed to this side that it did not say.** The note reports
"Your note carried '~23,000 files, ~19,000 PDFs'". Those numbers appear nowhere
in `2026-09-25-1951__reference-and-production-corpora.md`, which said only
"very large, mostly PDFs, no corpus structure, no index" and quoted Nick's
"tremendous work". Recorded because a corrected estimate resting on a
misattributed one is worth being able to trace. The correction itself is
right, and by a wider margin than either figure: the archive is 96,774 files
and 1.15 TB, and the corpus is a selected subset of fewer than 100 books.

**The reversibility observation appears twice**, once as the closing sentence
of *Not answered here* and again as the bolded paragraph after it. Editorial,
no disagreement.
