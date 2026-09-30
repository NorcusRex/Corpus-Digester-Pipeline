# Designer Response — catalog, not copy

*Received as the cover note to `corpus-glossary.md` 1.2 and
`repository-structure.md` 2.5. Reproduced verbatim. One imprecision noted on
receipt is recorded at the foot.*

Two shared files, read-only copies in this repository. Replace wholesale.

| File | Was | Now |
|---|---|---|
| `corpus-glossary.md` | 1.1 | **1.2** |
| `repository-structure.md` | 2.4 | **2.5** |

## The correction

Your phrasing was sharper than ours and both files now use it: **`2-Digested`
is a complete catalog of `1-Raw`, not a complete copy.**

The old wording — "`2-Digested` covers everything in `1-Raw`" — could be read as
promising the bytes are there. They are not, for an unconvertible file: the
sidecar is findable, the file it names stays in `1-Raw`.

`repository-structure.md` now says what that means for a searcher: a search of
three tiers finds everything that *exists*, and `1-Raw` is the escape hatch for
the bytes — the original of a converted file, or the file a sidecar stands for.

## On the stale version number

Taken, and the diagnosis is right as far as it goes: from outside, a stale
version is indistinguishable from stale content.

It was not the only cause. The Designer has no access to this repository and
tracks its state from handoffs and from what PM relays, so "the pipeline does
not yet provide the completeness guarantee" was a claim about code never read,
repeated for days after it stopped being true. The version number made the error
easy; it did not make it.

**Nothing follows for the shared files.** Recorded so the pattern is visible
rather than as a change request.

## Not answered here

Decisions 6 and 7 are confirmed closed on your account, and the multi-word
keyword item stays open as backlog item 5 with the scoring correction recorded.

---

## Noted on receipt — not a change request

Both files describe the media case as "carried through as media **beside a
converted file**". The code is broader: `process_folder.py:604` copies through
anything whose extension is in `MEDIA_EXTS`, whether or not a converted file
sits next to it. A folder of loose images in `1-Raw` appears in `2-Digested`
too.

The imprecision runs in the safe direction — it undersells what is there, so a
searcher who believed it would look in `1-Raw` and find the file anyway rather
than conclude it does not exist. Not worth a round trip on its own; worth
folding into whatever touches these sentences next.

Otherwise the new wording matches the code exactly, including the three-way
accounting the self-check tests on every run.
