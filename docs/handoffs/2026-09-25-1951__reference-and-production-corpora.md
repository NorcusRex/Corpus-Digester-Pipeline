---
title: Reference and Production Corpora — the federation decision and what it asks of the searcher
date: 2026-09-25T19:51-07:00
source: "Claude Code conversation, Corpus-Digester-Pipeline repository"
keywords: ["Reference corpus", "Production corpus", "corpus kind", "primary and secondary corpora", "search-project-corpus", "search-google-drive", "two-part and four-part corpora", "distinct result sets", "provenance boundary"]
---

# Reference and Production Corpora — the federation decision and what it asks of the searcher

2026-09-25 · Claude Code conversation in the `Corpus-Digester-Pipeline`
repository · written by the Code-side assistant (Developer role)

**Abstract.** Nick ruled that archived project material will **not** be copied
into the corpora that need it. Each archived project stays its own corpus, and a
project agent reaches across several. Two corpus kinds follow: a **Production
corpus**, which is the home of a project and carries all four tiers, and a
**Reference corpus**, which carries `1-Raw` and `2-Digested` only because no
project produces into it. Three consequences land on the Designer. First,
`search-project-corpus` must handle both shapes, so `repository-structure.md`'s
instruction to verify a root by checking for four tiers has to become
conditional on corpus kind. Second, a search across several corpora returns **several
distinct result sets, never one**: each corpus is searched separately and
exhaustively, results are reported per corpus — *"I looked here and found this;
I looked there and found that"* — and whether to merge them is the user's
decision, not the assistant's. Third, Nick wants a second, general skill — provisionally
`search-google-drive` — for Drive trees that are not corpora at all. The
pipeline side needs no change to support any of this; the mechanism that
distributes or withholds material already exists and is already configured per
corpus.

**Keywords:** Reference corpus · Production corpus · corpus kind · primary and
secondary corpora · `search-project-corpus` · `search-google-drive` ·
two-part and four-part corpora · distinct result sets · provenance boundary

*Moderate compression, prose with tables where a comparison is the point. Draft
one: reasoning is kept, and a short editorial note at the foot says what was
left out.*

## How this came up, and why it is arriving from the Code side

The question started as a pipeline question and turned into a design question
two exchanges in. Nick was working through what he needs to do locally before
digesting fresh exports, and reached a real problem underneath it: you cannot
control what an AI export contains. Claude allows a date range and nothing
finer; ChatGPT allows nothing at all. So an export is a single undifferentiated
bundle covering every topic you have ever discussed, and the material any one
corpus wants is mixed into it.

The pipeline already answers the extraction half of that, which is covered
below. What it cannot answer is where the extracted material should *live* when
more than one corpus wants it — and that turned out to determine both the
repository's shape and the searcher's configuration. Hence this report, written
on the Code side and handed over.

Nick's framing of the choice is the one worth carrying, because it is sharper
than the one it replaced:

> If we pull two archived projects into one corpus, a live project agent using
> search instructions and a search skill will treat them as one. If we keep each
> archived project in its own corpus [...] then a live project agent [...] will
> need configuration that allows it to find two or more corpora.

He also ruled that these are two answers to one problem and that one had to be
picked. That corrected the Code-side assistant, which had described them as "not
exclusive" — a framing Nick rejected on the grounds that leaving both open means
neither side builds cleanly.

## The decision

**Federate.** Each archived project remains its own corpus. A project agent is
configured with one Production corpus and zero or more Reference corpora.

## The two corpus kinds

Nick named them, and corrected the axis the Code side had proposed for telling
them apart.

| | Production corpus | Reference corpus |
|---|---|---|
| Tiers | All four | `1-Raw` and `2-Digested` |
| A project produces into it | Yes | No |
| Written to by the searcher | No | No |

The Code side had proposed distinguishing them by read/write access —
"reference corpora are read-only, the working corpus is where output lands."
Nick rejected that: *"Reference Corpora are read-only, but then so are
Production Corpora."* He is right, and the correction improves the definition
rather than just fixing a word. The searcher never writes to either. The real
distinction is **whether a project produces into the corpus**, and the tier
structure follows from that rather than being an independent fact about it.
`3-Reporting` and `4-Canon` exist in a Production corpus because a project's
derived writing and released artifacts accumulate there. A Reference corpus has
neither because nothing is accumulating.

Two properties worth recording:

- **One project, one Production corpus.** This is consistent with the glossary's
  existing "One project, one corpus", now made precise about which corpus.
- **A Reference corpus can be promoted.** `RPG Theory` is a Reference corpus
  today; if a project starts on it, it gains the two authored tiers and becomes
  Production. Nothing about the decision is one-way.

Nick's term is *Production*, replacing the Code side's *working corpus*. The
earlier term is superseded and should not appear in the shared files.

## Why federation rather than distribution

The deciding argument was put by the Code-side assistant and Nick endorsed it in
the form quoted below, as part of the search requirement. Recording it because
the requirement rests on it:

**The corpus is a provenance boundary.** Everything else in this system works to
preserve where a statement came from — the pipeline's keyword weighting is 128:1
on whose turn a term appeared in, and `write-report` indexes acceptance tiers to
the subject. Distribution discards that one level up. Once `RPG Theory` sits
inside `Loom-Nick\2-Digested`, a search hit cannot tell you whether an idea is
Loom's own thinking or imported reference material. Under federation the corpus
a hit came from is itself evidence: *"a labelled result set tells you 'Loom is
silent on this, RPG Theory isn't', which a merged list hides."*

Three supporting points, weaker individually:

- **Frequency.** Nick's stated need is occasional — Loom conversations reach for
  `RPG Theory` and `RPG - Tension` "on occasion". Permanently embedding whole
  projects to serve occasional queries is a lot of duplication for the rate.
- **One copy rather than N.** Under distribution, re-digesting the central
  archive means re-mirroring into every corpus that selected the material, and
  Drive holds a copy per corpus. The existing mirror is idempotent, so this is a
  cost in storage and sync time rather than a correctness risk.
- **Write-back stays clean.** Reports land in the Production corpus; Reference
  corpora are never written to.

**One consideration runs the other way**, and it is recorded because an earlier
version of the Code side's argument had it backwards. The intuition that mixing
corpora contaminates TF-IDF does not survive the arithmetic. Adding 300 theory
documents to 500 Loom documents raises the document count faster than it raises
document frequency for either body's own jargon, so each body's signature terms
become *more* distinctive, not less; terms common to both are suppressed, which
is arguably correct. Keyword quality under distribution is therefore roughly
neutral, possibly slightly better. It does not outweigh the provenance argument,
but it is not a point in federation's favour and should not be cited as one.

## What this requires of `repository-structure.md`

Nick: *"I think the skill `search-project-corpus` should be able to search any
corpus, whether 2-part or 4-part."*

`repository-structure.md` 2.3, under *Durability tiers*, currently says:

> **Architectural.** The four tier names, and the root named in project
> instructions. Assert and rely on these. Verify the root by checking that the
> four tiers sit beneath it; a named root without them is an error worth
> surfacing, not a folder to search anyway.

Under federation that check rejects every Reference corpus. **The four-tier
verification becomes the Production-corpus check**, and a root carrying `1-Raw`
and `2-Digested` alone is a valid Reference corpus rather than an error.

This is a shared-file change and belongs with the Designer. The notion of corpus
kind probably wants to be introduced in `corpus-glossary.md`, since it is
vocabulary, with `repository-structure.md` carrying the changed verification
rule — but which file holds which is the Designer's call, not the Developer's.

Nothing in the pipeline reads either statement, so there is no code change
waiting on it.

## What this requires of the searcher

Nick's position: *"A search over a larger domain should be slower, but not less
effective."*

Mostly right, and the Code side agreed with the "slower" half without
qualification. Two specific mechanisms would make it less effective if the skill
is not built against them, and both are avoidable:

**A fixed result budget.** If the skill returns the top N results overall, more
corpora means each corpus gets a smaller share of the budget and one corpus's
hits crowd out another's. Total coverage rises while recall per corpus falls —
the shape of failure that is hardest to notice, because the result set looks
healthy.

**Score comparability.** TF-IDF scores are corpus-relative. A keyword's weight in
`Loom-Nick` is computed against Loom's vocabulary; the same term in `RPG Theory`
is computed against a different one. The numbers are not on the same scale, so
merging ranked lists by score is not a ranking, it is noise with an ordering.
This is the same corpus-relativity that appears in the argument above, seen from
the other side.

**The rule, in Nick's own form.** The Code side proposed "search each corpus
separately and exhaustively, label every result with the corpus it came from,
and don't pool into a single global ranking." Nick accepted that and then went
further, and his version is the one that governs:

> When a primary and secondary corpora are searched, it seems like they should
> be treated as entirely distinct. "I looked here and found this; I looked
> there and found that". How to merge their results, if desired, should be a
> decision for the user, not the assistant.

The difference matters. The Code side's version forbids one specific bad
behaviour — a pooled ranking — and leaves the assistant free to combine results
in other ways. Nick's version withholds the merge decision from the assistant
altogether. A search returns several result sets and says where each came from;
the reader decides what to do with them, and the skill does not decide on their
behalf.

That also disposes of the presentation question. Under the weaker rule the
skill still has to choose how to interleave and display results; under Nick's,
there is nothing to interleave, because the sets stay separate all the way to
the reader.

Stating this as a requirement rather than as advice is deliberate. It is
exactly the kind of constraint that gets optimised away later by someone
reasonably trying to make the skill faster or tidier, and the thing it
protects — the provenance boundary federation was chosen for — is not visible in
the code that would remove it.

**A second axis, in Nick's words.** He speaks of *primary* and *secondary*
corpora, which is not the same distinction as Production and Reference.
Production versus Reference is a fact about a corpus's structure and whether a
project produces into it. Primary versus secondary is a fact about a particular
agent's relationship to it in a particular search. They are independent: a
Production corpus owned by one project can be a secondary corpus for another
project's agent. Worth naming explicitly in the shared files, because
collapsing the two axes would make "Reference" mean "secondary" and quietly
rule out the case Nick started from — Loom reaching into `RPG Theory`, which
may itself become Production later.

This also interacts with a change the Designer made this week on their own
initiative: `search-project-corpus` now reports the exact queries it used,
because a thin conjunctive result looks the same whether material is absent or
the query excluded it. Under federation that reporting matters more, since the
same ambiguity now exists per corpus.

## A second skill, for Drive trees that are not corpora

Nick: *"We also probably need a more general (e.g., `search-google-drive`)
skill — since we have learned a lot about how to search large collections in
Drive, Claude, and Evernote efficiently and conclusively, and it isn't just by
using the out-of-the-box search methods."*

His example is his `RPG` library: very large, mostly PDFs, no corpus structure,
no index.

The Code side's view, offered and not ruled on: the reason this is a separate
skill is stronger than structure. What makes corpus search work is not the
folder layout but `_index.json` and the frontmatter behind it — titles,
keywords, dates, all precomputed by the pipeline. A tree without that layer
requires content search over PDFs, which is a different technique rather than a
variant of the same one. That argues for two genuinely separate skills rather
than one skill with a mode flag.

**A third option was raised and deferred.** `tier_sidecars.py` already builds a
catalogue beside files it must not modify — that is how `4-Canon` works. Pointed
at a non-corpus tree it would write a companion `.md` next to each PDF recording
title, type, size and path, leaving every original byte-identical, producing an
index over a tree without restructuring it. The honest limitation is that it
currently extracts text only from formats it can read cheaply, so PDFs would get
keywords derived from filename and path — findable by title, not by content.
Making it real means wiring in the existing PDF extraction.

Nick set this aside as future work and named the real obstacle: many of the
games in that library are not OCR'd, so genuinely mining it would involve OCR
and *"tremendous work"*. He wants to do it *"some day"*. Nothing further is
proposed here.

## What the pipeline side already provides

Recorded so the Designer knows what is already load-bearing rather than
aspirational.

**Selective extraction already exists.** `sync_subset.py`, wired into each
corpus's wrapper as a `--sync` step, mirrors named project folders from a
central digested archive into a corpus's `1-Raw`. Selection is a plain text
list, one folder name per line, living beside the corpus's wrapper. The mirror
is one-directional and idempotent.

**Selection happens after digestion, and has to.** The readable project name
does not exist in the raw export. Claude's export carries no project grouping at
all — `<UUID>_manifest.json` supplies it and the converter applies it during
conversion. ChatGPT's export carries project IDs, but as opaque `g-p-…` strings
that mean nothing until `project_names.tsv` resolves them. In both cases the
name comes into existence inside the converter, so "digest the whole archive
once, then select by name" is the only order available.

**Federation costs the pipeline nothing.** It is the cheaper option here: under
federation each corpus is simply digested, with no cross-corpus mirroring at
all. The `--sync` mechanism stays in place for the case it was built for —
pulling a project out of the shared export archive into the corpus that owns it
— rather than for lending material between corpora.

**Double digestion, where it happens, is clean.** Verified in the code rather
than assumed: existing `date` and `title` frontmatter are preserved, `.nlm.md`
sidecars are excluded from both the metadata and sidecar passes, and keywords
are recomputed against the receiving corpus. That last is correct behaviour
given that IDF is corpus-relative.

## Open, deferred, and not settled here

- **Whether the Drive connector can in fact search several roots well** is
  unverified. Nick's position is that it should be slower but not less
  effective; the Code side named two mechanisms that would make it less
  effective if unaddressed. Nobody has tested it. This is the one dependency
  that could still argue against federation, and it is the Designer's to
  answer.
- **Which shared file carries corpus kind** — glossary, `repository-structure.md`,
  or both — is the Designer's call.
- **Search priority across a Production corpus and its Reference corpora** was
  not discussed. The existing priority runs conversation, past conversations,
  Evernote, repository; how several repositories order among themselves is
  open.
- **`search-google-drive`** exists as a named intention and nothing more. Its
  scope, and whether it also covers Claude and Evernote collections as Nick's
  phrasing suggests, is undefined.
- **Indexing the `RPG` library in place** was raised and deferred to "some day",
  with OCR named as the real obstacle.

## Reporter's commentary

Three observations, mine rather than Nick's, offered for the Designer to weigh
or discard.

**The decision is more reversible than it looks, in one direction only.**
Federation to distribution is easy — add an entry to a selection list and
re-sync. Distribution to federation means extracting material back out of
corpora that have absorbed it, after those corpora's keyword statistics have
already been computed over the mixed body. Starting federated preserves the
option; starting distributed spends it. This was not part of the argument Nick
ruled on and may be worth more than the supporting points that were.

**The corpus-kind change may be smaller than it sounds.** Read again,
`repository-structure.md`'s durability section is not really asserting that
every corpus has four tiers; it is telling the searcher how to avoid searching a
folder that is not a corpus at all. The Reference corpus does not break that
intent, only the test that implements it. A rule phrased as "verify the root by
checking that `1-Raw` and `2-Digested` sit beneath it, and that a Production
corpus additionally carries `3-Reporting` and `4-Canon`" would preserve the
purpose with a smaller edit than introducing a kind system might imply.

**The strengthened rule is also easier to implement than the weaker one.** A
rule against pooling still requires judgment at presentation time — how to
interleave, in what order, under what budget. A rule that the result sets stay
distinct removes the judgment: report each search as its own answer. Where the
weaker rule needed care to obey, this one is obeyed by doing less.

## Provenance

Written by the Code-side assistant in the `Corpus-Digester-Pipeline` repository,
from the conversation in which the decisions were made [S1], with supporting
detail read directly from the repository's source files [S2] [S3] [S4]. The
subject is Nick.

**Acceptance rubric 4.13; provenance and citation standard 4.13.**

**Nick's own positions** (user-acceptance tier 0 — Subject's Own Assertion):
that distribution and federation are two answers to one problem and one must be
chosen; the names *Reference* and *Production*; that Reference corpora need not
carry `3-Reporting` or `4-Canon`; that both kinds are read-only, correcting the
axis proposed for distinguishing them; that `search-project-corpus` must handle
both two-part and four-part corpora; that a general `search-google-drive` skill
is probably needed and that the out-of-the-box search methods are not what
works; that a search over a larger domain should be slower but not less
effective; and that digesting the `RPG` library is future work involving OCR and
tremendous effort. The framing quoted in *How this came up* is his, verbatim.

Also tier 0, and added after the first draft: that a primary and a secondary
corpus are treated as **entirely distinct** in a search, and that merging their
results is the user's decision rather than the assistant's. Quoted in full
under *What this requires of the searcher*. The terms *primary* and *secondary*
are his; the observation that they form an axis independent of
Production/Reference is the reporter's.

**Nick accepted this** (user-acceptance tier 1 — Explicitly Accepted, clear
referent): the search requirement — per-corpus exhaustive search, corpus-labelled
results, no global ranking — together with the provenance-boundary rationale
stated in the same passage, which he quoted before answering "Agreed!". Also the
configuration model, "a project agent is configured with one working corpus and
zero or more reference corpora", which he quoted and answered "Good idea!".

**Two bifurcations, both recorded rather than merged into the accepted form.**

Nick accepted the configuration model and then renamed its terms, so the
accepted form is *one Production corpus and zero or more Reference corpora*;
the Code side's "working corpus" is superseded and attributed to the assistant,
not to Nick.

Nick accepted the search requirement and then strengthened it. The Code side's
version forbade pooling into a global ranking; Nick's requires the corpora be
treated as entirely distinct and withholds the merge decision from the
assistant. The Code side's version is superseded — it permits combinations
Nick's does not — and the governing form is his, tier 0. Both are printed in
the body, because the difference between them is the substance of the ruling.

**Nick's own characterisation of what he accepted**, given when this draft was
reviewed: *"I think your proposals are fine. I did accept the general idea,
although perhaps not all the details."* That confirms the tiering below rather
than changing it — the general conclusions are accepted, the individual
supporting arguments are not, and the items marked indeterminate should stay
marked.

**Nick objected to this, and it was resolved in his favour** (user-acceptance
tier 3 — Contested, clear referent): the Code side's claim that read/write access
distinguishes the two corpus kinds. He quoted it and corrected it; the
correction is recorded above as the definition.

Also tier 3, resolved: the Code side's initial position that distribution and
federation were "not exclusive". Nick quoted it and rejected it. The report is
written on his ruling.

**Nick built on this without explicitly endorsing it** (user-acceptance tier 5 —
Tacitly Accepted, clear referent): federation as the chosen approach. He never
said "federate"; he responded to the recommendation by naming the two corpus
kinds and specifying their structure, which is action on the conclusion rather
than a statement about it. The Code side judges this strong evidence, and the
whole report depends on it, so it is flagged rather than quietly promoted.

**Nick never responded to these** (user-acceptance tier 7 — Indeterminate), and
they must not be read as agreed: the TF-IDF correction, that mixing corpora
sharpens rather than contaminates each body's keywords; the argument that
`search-google-drive` is a separate skill because of the missing index layer
rather than because of folder structure; the `tier_sidecars.py` proposal for
indexing a non-corpus tree in place; the two search-degradation mechanisms
individually, since his "Agreed!" quoted the requirement sentence and its
rationale but not the mechanisms that preceded them, and endorsement scope
defaults narrow; and everything under *Reporter's commentary*, which is the
assistant's and is marked as such.

**Overrides.** Two, both recorded rather than silent. The skill's standard
requires the model to be named in frontmatter and the header; this repository's
own rules prohibit model identifiers in any artifact pushed to it, and that
instruction outranks a skill reference file, so the assistant is identified by
role instead. Nick can add the identifier if he files this copy elsewhere. The
skill also specifies writing to `/mnt/user-data/outputs/`; this report is
written to `docs/handoffs/` instead, matching the repository's existing handoff
notes and the branch it will be pushed on.

**Uncertainty about the filename.** The convention wants a local timestamp. The
container clock reads UTC; `19:51 -07:00` assumes Nick is on Pacific daylight
time, inferred from the `-07:00` offsets in the manifest format and from the
timestamp on the previous handoff note. If that inference is wrong the filename
and `date` field are wrong with it, and renaming is harmless.

**Revision.** This is draft one, revised in place after Nick reviewed it. The
revision strengthened the search rule to his form, added the primary/secondary
axis, and replaced the third reporter's observation, which the strengthened
rule made moot. Nothing was removed on the grounds of being wrong; the
superseded Code-side formulation is retained and marked.

**Substantive omission.** No corpus search was performed for this report and
none of Nick's past conversations were consulted. It is an account of one
conversation, and a position he took elsewhere could contradict it without this
report knowing.

## Sources

### S1 — Conversation: Corpus-Digester-Pipeline, branch `claude/vigilant-davinci-amht34`
- Type: Claude Code conversation
- Locator: the current session; no shareable URL. The exchanges cited run from
  "Bear with me as we take another step up to a higher altitude" through
  "A search over a larger domain should be slower, but not less effective."
- Accessed: 2026-09-25
- Note: all rulings and quotations above are from this conversation, including
  the review exchange after draft one, which supplied the governing form of the
  search rule

### S2 — File: `sync_subset.py`
- Type: repository source file
- Locator: `sync_subset.py` (repository root)
- Version: as of commit `d165bd4` on `claude/vigilant-davinci-amht34`
- Accessed: 2026-09-25
- Note: read for the selective-extraction mechanism and the reason selection
  follows digestion; its module docstring states that reasoning independently

### S3 — File: `tier_sidecars.py`
- Type: repository source file
- Locator: `tier_sidecars.py` (repository root)
- Version: as of commit `d165bd4`
- Accessed: 2026-09-25
- Note: read for the index-in-place option and for the limits of its current
  keyword extraction on non-text formats

### S4 — File: `references/repository-structure.md`
- Type: shared reference file, Designer-owned, read-only copy in this repository
- Locator: `references/repository-structure.md`
- Version: 2.3
- Accessed: 2026-09-25
- Note: the *Durability tiers* passage quoted above

---

*Editorial note, draft one.* Dropped by category: the step-by-step local setup
discussion that preceded this thread, which is operational and lives in
`BACKLOG.md`; the `project_names.tsv` path question, same reason; and the
worked arithmetic behind the TF-IDF correction, kept as its conclusion only.
Marginal calls kept rather than cut: the *What the pipeline side already
provides* section, which the Designer may already know, and the reversibility
observation in the commentary, which is the assistant's own and was not
discussed.
