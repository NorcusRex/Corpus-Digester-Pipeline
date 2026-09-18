#!/usr/bin/env python3
"""
tier_sidecars.py

Make the files in an authored tier findable without modifying any of them.

`4-Canon` holds released artifacts -- the things the project actually ships.
They are often authored outside any tooling, and they must not be rewritten to
suit a search index: no frontmatter stamped into them, no generated index block
inserted into their prose, no bytes changed at all. But an artifact that nothing
can find is an artifact that may as well not be filed.

This script resolves that by writing a *companion* Markdown file beside each
artifact, named for it and carrying the fields search relies on:

    4-Canon/loom-rulebook-v1.0.pdf         <- untouched
    4-Canon/loom-rulebook-v1.0.pdf.md      <- sidecar, written here

The sidecar records the artifact's title, keywords, type, size, and path
relative to the corpus root. A reader who wants the artifact follows
`source_path`; a reader who wants to know what exists reads the sidecars.

This is the same mechanism the digester uses for files it cannot convert,
applied to a tier rather than to a conversion failure.

Usage
-----
    python tier_sidecars.py 4-Canon
    python tier_sidecars.py 4-Canon --corpus-root I:\\RPG\\_Design\\Loom
    python tier_sidecars.py 4-Canon --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import add_metadata  # noqa: E402

# Marks a file this script wrote, so re-runs recognise their own output and
# never make a sidecar of a sidecar.
SIDECAR_SOURCE = "artifact sidecar"

# Never given a sidecar: our own output, pipeline bookkeeping, editor state.
SKIP_NAMES = {"_index.json", "_manifest.json", ".DS_Store", "Thumbs.db"}
SKIP_PREFIXES = ("~$", ".")

# Files whose text we can read cheaply to get better keywords than the
# filename alone provides. Anything else is described by name and path.
TEXT_SUFFIXES = {".md", ".txt", ".markdown"}


def is_skippable(path: Path, tier_root: Path) -> bool:
    """True for files that are not artifacts: our own output and utility junk."""
    if path.name in SKIP_NAMES:
        return True
    if any(path.name.startswith(p) for p in SKIP_PREFIXES):
        return True
    if path.name.endswith(".nlm.md"):
        return True
    if re.match(r"^_pipeline_\d{8}_\d{6}\.log$", path.name):
        return True
    rel_parent = path.parent.relative_to(tier_root)
    # Editor and tool configuration lives in dot-folders at any depth.
    return any(part.startswith(".") for part in rel_parent.parts)


def is_sidecar(path: Path) -> bool:
    """True if this file is a sidecar previously written by this script."""
    if path.suffix.lower() != ".md":
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2048]
    except OSError:
        return False
    fm, _ = add_metadata.parse_frontmatter(head)
    return str(fm.get("source", "")) == SIDECAR_SOURCE


def has_frontmatter(path: Path) -> bool:
    """True if a Markdown artifact already describes itself.

    A report written by the write-report skill arrives with frontmatter of its
    own. It needs no sidecar, and duplicating it would only create a second
    record to keep in step with the first.
    """
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    fm, _ = add_metadata.parse_frontmatter(head)
    return bool(fm)


def corpus_relative(path: Path, tier_root: Path,
                    corpus_root: Path | None) -> str:
    """Path relative to the corpus root, with forward slashes.

    The same string resolves on every mirror, because the reader supplies the
    root it already knows. An absolute path breaks the moment it is pushed.
    """
    for base in (corpus_root, tier_root.parent, tier_root):
        if base is None:
            continue
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.name


def artifact_title(path: Path) -> str:
    """A human-readable title, taken from a Markdown H1 where one exists."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            text = ""
        m = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return path.name


def artifact_keywords(path: Path, fm: dict, n: int = 12) -> list[str]:
    """Keywords from the artifact's text where readable, else name and path."""
    name_kw = add_metadata.sidecar_keywords(fm, n=n)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return name_kw
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return name_kw
    _, body = add_metadata.parse_frontmatter(text)
    body_kw = add_metadata.top_keywords(body, n=n)
    # Name-derived terms first: they identify the artifact. Content terms
    # follow, filling out what it is about.
    merged: list[str] = []
    for term in name_kw + body_kw:
        if term not in merged:
            merged.append(term)
    return merged[:n]


def build_sidecar(path: Path, tier_root: Path,
                  corpus_root: Path | None) -> tuple[dict, str]:
    """Return (frontmatter, body) for one artifact's sidecar."""
    source_path = corpus_relative(path, tier_root, corpus_root)
    try:
        stat = path.stat()
        size = stat.st_size
        date_str = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(
            timespec="minutes")
    except OSError:
        size = 0
        date_str = datetime.now().astimezone().isoformat(timespec="minutes")

    ext = path.suffix.lower() or "(none)"
    fm = {
        "title":       artifact_title(path),
        "date":        date_str,
        "source":      SIDECAR_SOURCE,
        "source_file": path.name,
        "source_path": source_path,
        "file_type":   ext,
        "size_bytes":  size,
    }
    fm["keywords"] = artifact_keywords(path, fm)

    body = (
        f"# {fm['title']}\n\n"
        f"Catalog record for a released artifact. The artifact itself is "
        f"unmodified; this file exists so it can be found.\n\n"
        f"- **File:** {path.name}\n"
        f"- **Type:** {ext}\n"
        f"- **Size:** {size:,} bytes\n"
        f"- **Path from corpus root:** `{source_path}`\n"
    )
    return fm, body


def sidecar_path_for(path: Path) -> Path:
    """Keep the artifact's full name, extension included, so rulebook.pdf and
    rulebook.docx cannot collide on one sidecar."""
    return path.with_name(path.name + ".md")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Write catalog sidecars beside the artifacts in a tier, "
                    "without modifying any of them."
    )
    ap.add_argument("tier", help="Tier directory, e.g. 4-Canon")
    ap.add_argument("--corpus-root", default=None,
                    help="Corpus root holding the four tiers. Sidecars record "
                         "source paths relative to it. Default: the tier's parent.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be written; change nothing")
    ap.add_argument("--keywords", type=int, default=12,
                    help="Keywords per sidecar (default: 12)")
    args = ap.parse_args()

    tier_root = Path(args.tier).resolve()
    if not tier_root.is_dir():
        print(f"ERROR: not a directory: {tier_root}", file=sys.stderr)
        return 1
    corpus_root = (Path(args.corpus_root).resolve()
                   if args.corpus_root else tier_root.parent)

    print(f"Tier   : {tier_root}")
    print(f"Corpus : {corpus_root}")
    if args.dry_run:
        print("Mode   : DRY RUN (nothing will be written)")
    print()

    stats: Counter = Counter()
    files = sorted(p for p in tier_root.rglob("*") if p.is_file())

    # Resolve sidecars first so an artifact is never mistaken for one, and so
    # a sidecar written earlier in this run is not itself given a sidecar.
    existing_sidecars = {p for p in files if is_sidecar(p)}

    for path in files:
        if is_skippable(path, tier_root):
            stats["skipped"] += 1
            continue
        if path in existing_sidecars:
            stats["is_sidecar"] += 1
            continue
        # A Markdown artifact that already carries frontmatter describes
        # itself. Leave it alone rather than creating a rival record.
        if path.suffix.lower() == ".md" and has_frontmatter(path):
            stats["self_describing"] += 1
            continue

        target = sidecar_path_for(path)
        fm, body = build_sidecar(path, tier_root, corpus_root)
        new_text = add_metadata.emit_frontmatter(fm) + "\n\n" + body

        if target.exists():
            try:
                if target.read_text(encoding="utf-8") == new_text:
                    stats["unchanged"] += 1
                    continue
            except OSError:
                pass
            # Never overwrite a Markdown file that is not one of ours.
            if target not in existing_sidecars:
                print(f"  [warn] {target.name} exists and is not a sidecar; "
                      f"leaving it alone", file=sys.stderr)
                stats["conflict"] += 1
                continue
            stats["updated"] += 1
        else:
            stats["written"] += 1

        rel = path.relative_to(tier_root)
        print(f"  sidecar  {rel}")
        if not args.dry_run:
            target.write_text(new_text, encoding="utf-8")

    print()
    print("=" * 60)
    print(f"  artifacts catalogued : {stats['written'] + stats['updated']}")
    print(f"    newly written      : {stats['written']}")
    print(f"    refreshed          : {stats['updated']}")
    print(f"  already current      : {stats['unchanged']}")
    print(f"  self-describing .md  : {stats['self_describing']}")
    print(f"  existing sidecars    : {stats['is_sidecar']}")
    print(f"  utility skipped      : {stats['skipped']}")
    if stats["conflict"]:
        print(f"  CONFLICTS            : {stats['conflict']} "
              f"(a non-sidecar .md occupies the sidecar name)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
