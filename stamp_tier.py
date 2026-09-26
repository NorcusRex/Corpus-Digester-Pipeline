#!/usr/bin/env python3
"""
stamp_tier.py

Give the Markdown files in an authored tier the frontmatter search needs,
without disturbing the ones that already have it.

WHY

`3-Reporting` holds derived writing: reports, transcripts, commentary. A
report written by the `write-report` skill arrives with a complete header --
title, date, keywords, source -- because the skill writes one. Anything
hand-written, pasted, or predating that skill does not, and search cannot see
a file that lacks those fields. The failure is quiet: the file is sitting
right there, and every search misses it.

The pipeline never touched this tier, because the pipeline's job is `1-Raw`
into `2-Digested`. That left a gap nothing was closing.

WHAT IT CHANGES, AND WHAT IT WILL NOT

It fills in missing fields. It does not overwrite a field that is already
there, so a title you wrote by hand survives, and a date you set deliberately
is not replaced by the file's mtime.

It does not insert anything into the prose. The digester adds a generated
index block to the documents it writes; that is right for a converted
conversation and wrong for authored writing, so it is off here. Only the
frontmatter block changes.

A file whose frontmatter is already complete is left byte-identical and
reported as untouched.

AUTHORED TIERS ARE NOT `2-Digested`

Two deliberate differences from the digester's metadata pass:

  * No index block, as above.
  * Keywords are computed against this tier alone, not against `2-Digested`.
    TF-IDF is relative to the body it is measured over, and a report's
    distinctive terms should be distinctive among reports.

`4-Canon` IS NOT STAMPED BY THIS SCRIPT

Released artifacts are never modified -- that is a standing rule, and most of
them are not Markdown anyway. A `4-Canon` artifact becomes findable through
the companion record `tier_sidecars.py` writes beside it, which carries the
same four fields and leaves the artifact byte-identical.

USAGE

    python stamp_tier.py 3-Reporting
    python stamp_tier.py 3-Reporting --corpus-root I:\\RPG\\_Design\\Loom
    python stamp_tier.py 3-Reporting --dry-run

EXIT CODES

    0  every Markdown file in the tier now carries the required fields
    1  completed, but something could not be stamped
    2  a usage or path error prevented the run
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import add_metadata  # noqa: E402

REQUIRED_FIELDS = ("title", "keywords", "date", "source")

# A file this script or the digester generated rather than something authored.
DERIVED_SUFFIXES = (".nlm.md",)


# `source` names where a document came from. In `2-Digested` a converter
# supplies it -- "Claude export", "docx". An authored file has no converter,
# so nothing ever set it, and the metadata pass does not invent one. This is
# what the pipeline can honestly say: not produced by a converter, origin not
# otherwise recorded.
AUTHORED_SOURCE = "authored"


def ensure_source(path: Path, value: str = AUTHORED_SOURCE) -> bool:
    """Set `source` if the file lacks one. Returns True if it was added."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    fm, body = add_metadata.parse_frontmatter(text)
    if str(fm.get("source", "") or "").strip():
        return False
    fm["source"] = value
    path.write_text(add_metadata.emit_frontmatter(fm) + "\n\n" + body.lstrip("\n"),
                    encoding="utf-8")
    return True


def missing_fields(path: Path) -> list[str]:
    """Which required fields this file lacks. Empty means it is complete."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return list(REQUIRED_FIELDS)
    fm, _ = add_metadata.parse_frontmatter(text)
    return [k for k in REQUIRED_FIELDS
            if not str(fm.get(k, "") or "").strip()]


def candidates(tier_root: Path) -> list[Path]:
    return [f for f in sorted(tier_root.rglob("*.md"))
            if not f.name.endswith(DERIVED_SUFFIXES)
            and not add_metadata.is_utility_path(f, tier_root)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stamp missing frontmatter on the Markdown files in an "
                    "authored tier.")
    ap.add_argument("tier", help="The tier folder, e.g. 3-Reporting")
    ap.add_argument("--corpus-root", default=None,
                    help="Corpus root, for reporting paths")
    ap.add_argument("--keywords", type=int, default=None,
                    help="Keyword count (default: scale by document length)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be stamped, change nothing")
    args = ap.parse_args()

    tier_root = Path(args.tier).expanduser()
    if not tier_root.is_dir():
        print(f"ERROR: not a directory: {tier_root}", file=sys.stderr)
        return 2

    files = candidates(tier_root)
    if not files:
        print(f"No Markdown files in {tier_root}.")
        return 0

    incomplete = [(f, missing_fields(f)) for f in files]
    incomplete = [(f, m) for f, m in incomplete if m]

    print(f"{len(files):,} Markdown file(s) in {tier_root.name}.")
    print(f"{len(incomplete):,} missing at least one required field.")
    if not incomplete:
        print("Nothing to do.")
        return 0

    # Corpus statistics over this tier only. A report's distinctive terms
    # should be distinctive among reports, not among conversations.
    doc_freq = None
    total_docs = 0
    if len(files) >= 5:
        doc_freq, total_docs = add_metadata.build_corpus_doc_freq(files)
        print(f"  vocabulary: {len(doc_freq):,} terms over {total_docs:,} files")

    dictionary, _ = add_metadata.load_lexicons(
        [SCRIPT_DIR / "lexicon"] if (SCRIPT_DIR / "lexicon").is_dir() else [],
        None)

    stats: Counter = Counter()
    stamped = 0
    failed = 0
    for f, missing in incomplete:
        rel = f.relative_to(tier_root).as_posix()
        if args.dry_run:
            print(f"  would stamp {rel}  (missing: {', '.join(missing)})")
            stamped += 1
            continue
        try:
            # write_index=False: authored prose is not a converted
            # conversation and must not gain a generated index block.
            add_metadata.process_file(
                f, n_keywords=args.keywords, write_index=False,
                doc_freq=doc_freq, total_docs=total_docs,
                stats=stats, dictionary=dictionary or None)
            ensure_source(f)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] {rel}: {e}", file=sys.stderr)
            failed += 1
            continue
        still = missing_fields(f)
        if still:
            print(f"  [warn] {rel}: still missing {', '.join(still)}",
                  file=sys.stderr)
            failed += 1
        else:
            print(f"  stamped {rel}  (added: {', '.join(missing)})")
            stamped += 1

    print()
    print(f"  stamped : {stamped}")
    if failed:
        print(f"  failed  : {failed}")
    if args.dry_run:
        print("(dry run -- nothing was written)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
