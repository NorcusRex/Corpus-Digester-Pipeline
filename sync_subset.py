#!/usr/bin/env python3
"""
sync_subset.py

Idempotently mirror a named subset of immediate subfolders from one
digested tree into a destination tree.

This is a GENERIC tool. It contains no knowledge of any particular
corpus, project, topic, or folder name. All site-specific knowledge --
which folders, which source, which destination -- lives in data: a
plain-text selection list and a thin launcher .bat. This separation is
deliberate and matches the rest of the pipeline (generic .py engine,
site-specific .bat launcher, site-specific data files such as
project_names.tsv).

THE PROBLEM THIS SOLVES

Some exports (AI conversation exports, for example) are topic-blind at
the source: one undifferentiated blob covering every subject. The
project/topic structure only becomes legible AFTER digestion, because
digestion is the step that resolves it into named folders. If you want
only a subset of those folders in a downstream corpus, you cannot
filter before digesting -- the thing you would filter on does not exist
yet. So you must digest the whole thing, then select.

Doing that selection by hand-copying digested folders creates divergent
forests with no provenance and no idempotency: re-digest later and you
have two trees with no record of which is authoritative and no way to
tell what went stale. This script replaces the hand-copy with a
mechanical, directional, idempotent mirror.

WHAT IT DOES

Given a source digested tree, a destination, and a selection list:

  1. Reads the selection list (one folder name per line; blank lines
     and lines starting with # are ignored).
  2. For each listed name that exists as an immediate subfolder of the
     source, mirrors it into the destination.
  3. "Mirror" means: files present in the source subtree are copied if
     missing or changed at the destination; files at the destination
     that no longer exist in the source subtree are removed; the
     destination subtree ends up matching the source subtree exactly.
  4. Subfolders at the destination that correspond to a selection-list
     entry that is no longer present (removed from the list, or gone
     from the source) are reported, and removed only with --prune.

The mirror is one-directional (source -> destination) and idempotent:
same inputs, same result, safe to re-run any number of times.

IMPORTANT: the destination subtree IS made to match the source. Within
a selected folder, destination-only files are deleted so the copy stays
a true mirror rather than an ever-growing union. This is safe because
the destination is, by design, a projection of the source -- not a
place where independent edits should live. Do NOT point this at a
destination that contains hand-edited files you care about; those are
not the intended use and will be removed if absent from the source.

USAGE

    python sync_subset.py SOURCE DEST --list SELECTION.txt

    SOURCE        a digested tree whose immediate subfolders are the
                  selectable units (e.g. .../2-Digested/conversations)
    DEST          where selected folders are mirrored to
    --list FILE   the selection list (site-specific data, lives with
                  the corpus, NOT in the tooling folder)
    --prune       also remove destination folders that are no longer
                  selected (default: report them but leave them)
    --dry-run     show what would happen, change nothing
    --verbose     list every file action, not just folder summaries

EXIT CODES

    0  completed; nothing needing attention
    1  completed, but some selection-list entries were not found in
       SOURCE, or unselected folders exist at DEST without --prune
    2  a usage or path error prevented the run
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


def load_selection(list_path: Path) -> list[str]:
    """Parse the selection list. One folder name per line. Blank lines
    and lines beginning with # (after optional whitespace) are ignored.
    Surrounding whitespace on a name is stripped. Order is preserved and
    duplicates are removed (first occurrence wins) so the file can be
    organized with comments and grouping without affecting behaviour.
    """
    names: list[str] = []
    seen: set[str] = set()
    with list_path.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line not in seen:
                seen.add(line)
                names.append(line)
    return names


def mirror_folder(src: Path, dst: Path, dry_run: bool,
                   verbose: bool) -> tuple[int, int, int]:
    """Make dst match src exactly. Returns (copied, updated, removed)
    counts. Copies new/changed files, removes destination files and
    subfolders that are not present in src.
    """
    copied = updated = removed = 0

    # Pass 1: copy new and changed files from src into dst.
    for src_file in sorted(src.rglob("*")):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        if not dst_file.exists():
            if verbose:
                print(f"    + {rel}")
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            copied += 1
        elif not _same(src_file, dst_file):
            if verbose:
                print(f"    ~ {rel}")
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            updated += 1

    # Pass 2: remove destination files not present in src.
    if dst.exists():
        for dst_file in sorted(dst.rglob("*"), reverse=True):
            if dst_file.is_dir():
                continue
            rel = dst_file.relative_to(dst)
            if not (src / rel).exists():
                if verbose:
                    print(f"    - {rel}")
                if not dry_run:
                    dst_file.unlink()
                removed += 1
        # Remove now-empty directories left behind by removals.
        for d in sorted((p for p in dst.rglob("*") if p.is_dir()),
                        reverse=True):
            if not dry_run and not any(d.iterdir()):
                d.rmdir()

    return copied, updated, removed


def _same(a: Path, b: Path) -> bool:
    """Shallow file equality: size + mtime, then a content compare only
    if those differ. filecmp.cmp(shallow=True) is the size+mtime check;
    we fall back to a full compare to be safe against mtime drift.
    """
    try:
        if filecmp.cmp(a, b, shallow=True):
            return True
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Idempotently mirror a named subset of digested "
                    "subfolders from a source tree to a destination.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("source", help="Source digested tree (its immediate "
                                   "subfolders are the selectable units)")
    ap.add_argument("dest", help="Destination tree to mirror into")
    ap.add_argument("--list", dest="list_path", required=True,
                    help="Selection list file (one folder name per line)")
    ap.add_argument("--prune", action="store_true",
                    help="Remove destination folders no longer selected")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen without changing anything")
    ap.add_argument("--verbose", action="store_true",
                    help="List every file action")
    args = ap.parse_args()

    source = Path(args.source)
    dest = Path(args.dest)
    list_path = Path(args.list_path)

    if not source.is_dir():
        print(f"ERROR: source is not a directory: {source}", file=sys.stderr)
        return 2
    if not list_path.is_file():
        print(f"ERROR: selection list not found: {list_path}", file=sys.stderr)
        return 2

    names = load_selection(list_path)
    if not names:
        print(f"ERROR: selection list is empty: {list_path}", file=sys.stderr)
        return 2

    print()
    print("=" * 60)
    print("  Subset mirror")
    print("=" * 60)
    print(f"  Source : {source}")
    print(f"  Dest   : {dest}")
    print(f"  List   : {list_path}  ({len(names)} entries)")
    print(f"  Mode   : {'DRY-RUN' if args.dry_run else 'LIVE'}"
          f"{' +prune' if args.prune else ''}")
    print()

    attention = False

    # Mirror each selected folder that exists in source.
    selected_present: set[str] = set()
    for name in names:
        src_folder = source / name
        if not src_folder.is_dir():
            print(f"  [missing] '{name}' not found in source -- skipped")
            attention = True
            continue
        selected_present.add(name)
        dst_folder = dest / name
        print(f"  [mirror ] {name}")
        copied, updated, removed = mirror_folder(
            src_folder, dst_folder, args.dry_run, args.verbose)
        print(f"            +{copied} new  ~{updated} changed  "
              f"-{removed} removed")

    # Identify destination folders that are not in the current selection.
    if dest.is_dir():
        for child in sorted(dest.iterdir()):
            if not child.is_dir():
                continue
            if child.name not in selected_present:
                if args.prune:
                    print(f"  [prune  ] {child.name}")
                    if not args.dry_run:
                        shutil.rmtree(child)
                else:
                    print(f"  [stale  ] {child.name}  "
                          f"(not selected; use --prune to remove)")
                    attention = True

    print()
    print("=" * 60)
    if args.dry_run:
        print("  Dry run complete. No changes were made.")
    else:
        print("  Mirror complete.")
    print("=" * 60)
    return 1 if attention else 0


if __name__ == "__main__":
    raise SystemExit(main())
