# Lexicon

Word lists used to **prevent** keyword rejections, never to cause them.

A candidate keyword that looks implausible — an impossible letter pair, a long
consonant run — is dropped only if nothing vetoes it. Appearing in any file
here is a veto. So adding a term can only ever protect it.

## What goes here

**This folder**, shipped with the pipeline, holds general language lexicons:
English, and any other language whose vocabulary turns up across corpora.

**A corpus's own glossaries** live beside its wrapper, in that corpus's
`_Tools/`, and are passed with a second `--lexicon`. Those are the ones that
matter most: `Erlking`, `Cernunnos`, `crwth`, `Brigit` are exactly the terms
most at risk from any filter and least likely to appear in a general word list.

The loader treats both identically. Both are real words as far as the corpus is
concerned, and the filter has no reason to tell them apart.

## Format

Files ending `.txt`, `.tsv` or `.lst` are read; everything else is ignored.
Blank lines and lines starting with `#` are skipped.

A `.txt` is one term per line:

```
crwth
cwm
Erlking
```

A `.tsv` takes its term from the **first column** and ignores the rest, so you
can carry metadata the loader does not need to understand:

```
Erlking	loom-glossary	name	ruler of the Underwood
crwth	welsh	noun	bowed lyre
```

Matching is case-insensitive. A hyphenated term is also tried with the hyphens
removed, so `bells-and-bronze` matches `bellsandbronze`.

## Usage

```
python process_folder.py 1-Raw 2-Digested \
    --lexicon lexicon \
    --lexicon "I:\RPG\_Design\Loom-Nick\_Tools\glossaries"
```

This folder is used automatically when no `--lexicon` is given.

## Before adding anything

Run a digest with `--report-artifacts rejected.md` and read what is actually
being dropped. Add lexicon entries for the real words you find there. Adding
terms speculatively costs nothing but achieves nothing either.
