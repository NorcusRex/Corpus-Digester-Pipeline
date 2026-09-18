#!/usr/bin/env python3
"""
fix_apostrophes.py

One-time fix: rename "Nick_s" -> "Nick's" and "Chris_s" -> "Chris's" in the
two D&D campaign folders that lost their apostrophes in earlier processing.

Usage:
    python fix_apostrophes.py "I:\\path\\to\\digested" --dry-run
    python fix_apostrophes.py "I:\\path\\to\\digested"

This script is intentionally narrow. It only touches the two specific folder
names and does nothing else. After running, your project_names.tsv (which
already has the apostrophes) will match the on-disk folders, and the
"not in archive: 4" count from the rename pass will drop to 2 (the genuinely
empty Games and GIS - Esri projects).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


RENAMES = [
    ("RPG - Nick_s D&D 5e Campaign",        "RPG - Nick's D&D 5e Campaign"),
    ("RPG - Chris_s Black Yak Campaign",    "RPG - Chris's Black Yak Campaign"),
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Restore apostrophes in two specific D&D campaign folder names."
    )
    ap.add_argument("root", help="Root directory of the digested archive")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be renamed without doing it")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    renamed = 0
    not_found = 0
    target_exists = 0

    for old_name, new_name in RENAMES:
        matches = [p for p in root.rglob(old_name) if p.is_dir()]
        if not matches:
            print(f"  not found: {old_name}")
            not_found += 1
            continue
        for src in matches:
            dst = src.parent / new_name
            if dst.exists():
                print(f"  skip (target exists): {src} -> {dst.name}")
                target_exists += 1
                continue
            print(f"  rename: {src.name}")
            print(f"      -> {dst.name}")
            if not args.dry_run:
                src.rename(dst)
            renamed += 1

    print()
    print(f"Renamed: {renamed}")
    if not_found:
        print(f"Not found: {not_found}")
    if target_exists:
        print(f"Target already exists: {target_exists}")
    if args.dry_run:
        print("(dry run -- no changes written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
