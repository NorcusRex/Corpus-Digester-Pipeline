#!/usr/bin/env python3
"""
rename_chatgpt_projects.py

Rename project_g-p-XXX/ folders in your digested archive to human-readable
names. Reads a simple TSV file mapping project IDs to names and renames the
matching folders in place.

Workflow
--------
1. Visit chatgpt.com and open each ChatGPT Project in turn. The URL will
   show /g/g-p-XXXXX/project. Copy that g-p-XXXXX ID and the project name.

2. Create a plain text file (e.g. project_names.tsv) with one project per
   line, ID and name separated by a tab:

       g-p-67f8deab3a0c819189bcc16e697ccd67    My Project Name
       g-p-aabb1122334455667788aabbccddeeff    Cooking notes
       g-p-deadbeefcafef00d12345678abcdef00    Tax planning 2026

   Use a real tab character between ID and name (not spaces). Most editors
   will let you type a tab; in some you may need to copy one from elsewhere.
   Lines starting with # are comments. Blank lines are ignored.

3. Run this script:

       python rename_chatgpt_projects.py project_names.tsv "C:\\path\\to\\digested"

   The script searches the digested tree for folders named project_<id>
   and renames each one. It does NOT modify the conversation files inside;
   the conversation_template_id frontmatter remains intact, so the pipeline
   will continue using the renamed folder on future runs.

The same approach works for Custom GPT folders (gpt_g-XXX) — just include
their IDs in the TSV.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def load_tsv(path: Path) -> dict[str, str]:
    """Parse the TSV map. Returns {project_id: human_name}."""
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" not in line:
                print(f"  WARNING: line {lineno} has no tab character, skipping: {line!r}",
                      file=sys.stderr)
                continue
            project_id, _, name = line.partition("\t")
            project_id = project_id.strip()
            name = name.strip()
            if not project_id or not name:
                print(f"  WARNING: line {lineno} missing id or name, skipping",
                      file=sys.stderr)
                continue
            mapping[project_id] = name
    return mapping


def safe_folder_name(name: str) -> str:
    """Sanitize a name for use as a Windows-and-everywhere-compatible folder."""
    # Disallowed characters on Windows: < > : " / \ | ? *
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned[:120] or "renamed_project"


def find_folder_by_template_id(root: Path, template_id: str) -> Path | None:
    """Find a folder anywhere under `root` whose first .md file has frontmatter
    matching this template_id. This is the durable identifier — folder names
    can be changed by the user, by Drive sync, by OS quirks, or by previous
    versions of this script, but the conversation_template_id baked into each
    conversation's frontmatter remains stable.

    Returns the folder Path if found, else None. Uses the same lookup
    technique as chatgpt_to_markdown.existing_folder_for_template, but walks
    the entire tree rather than one parent.
    """
    if not template_id:
        return None
    needle = f'conversation_template_id: "{template_id}"'
    for child in root.rglob("*"):
        if not child.is_dir():
            continue
        # Look at canonical .md files only -- skip .nlm.md sidecars, which
        # have their frontmatter stripped by the NotebookLM pass and never
        # contain the needle.
        try:
            md_files = sorted(
                md for md in child.glob("*.md")
                if not md.name.endswith(".nlm.md")
            )
        except OSError:
            continue
        if not md_files:
            continue
        md = md_files[0]
        try:
            with md.open(encoding="utf-8") as f:
                head = f.read(2048)
        except OSError:
            continue
        if needle in head:
            return child
    return None


def apply_renames(mapping: dict, root: Path, dry_run: bool = False,
                  verbose: bool = True) -> dict:
    """Apply id-to-name mapping to project_<id>/ and gpt_<id>/ folders under root.

    Returns a stats dict with renamed/skipped_existing/skipped_missing/already.
    Idempotent: re-running on already-renamed folders is a no-op.
    """
    stats = {"renamed": 0, "skipped_existing": 0,
             "skipped_missing": 0, "already": 0}
    for project_id, human_name in mapping.items():
        target_name = safe_folder_name(human_name)

        # Look for both project_ and gpt_ prefixed folders.
        candidates = list(root.rglob(f"project_{project_id}"))
        candidates += list(root.rglob(f"gpt_{project_id}"))

        # If no raw-id folder exists, the folder may already have been
        # renamed (by us, by the user, by Drive sync, or by an earlier
        # version of this script). Look for it by reading frontmatter --
        # the conversation_template_id is the durable identifier that
        # survives any name change.
        if not candidates:
            existing = find_folder_by_template_id(root, project_id)
            if existing is None:
                # Genuinely no folder for this id (project has zero
                # conversations in this export, or id is wrong/stale).
                if verbose:
                    print(f"  not found: {project_id}  (no folder for this id)")
                stats["skipped_missing"] += 1
                continue
            # We found a folder belonging to this project. Is it already
            # named correctly?
            if existing.name == target_name:
                stats["already"] += 1
                continue
            # Different name: rename it to match the TSV. This handles
            # cases where the user changed the TSV after a previous run,
            # or where Drive sync mangled the name (e.g. apostrophes).
            dst = existing.parent / target_name
            if dst.exists() and dst != existing:
                if verbose:
                    print(f"  skip (target exists): {existing.name} -> {dst.name}")
                stats["skipped_existing"] += 1
                continue
            if verbose:
                print(f"  rename: {existing.name} -> {dst.name}")
            if not dry_run:
                existing.rename(dst)
            stats["renamed"] += 1
            continue

        # Raw-id folder(s) exist: rename them to the target name.
        for src in candidates:
            if not src.is_dir():
                continue
            dst = src.parent / target_name
            if dst.exists():
                if dst == src:
                    stats["already"] += 1
                    continue
                if verbose:
                    print(f"  skip (target exists): {src.name} -> {dst.name}")
                stats["skipped_existing"] += 1
                continue
            if verbose:
                print(f"  rename: {src.name} -> {dst.name}")
            if not dry_run:
                src.rename(dst)
            stats["renamed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rename project_g-p-XXX folders to human-readable names."
    )
    ap.add_argument("tsv", help="TSV file mapping project IDs to names")
    ap.add_argument("root", help="Root directory to search for project folders")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be renamed without doing it")
    args = ap.parse_args()

    mapping = load_tsv(Path(args.tsv))
    if not mapping:
        print("No project mappings loaded. Check your TSV file.")
        return 1

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 1

    stats = apply_renames(mapping, root, dry_run=args.dry_run, verbose=True)

    print()
    print(f"Renamed: {stats['renamed']}")
    if stats["already"]:
        print(f"Already named correctly: {stats['already']}")
    if stats["skipped_existing"]:
        print(f"Skipped (target exists): {stats['skipped_existing']}")
    if stats["skipped_missing"]:
        print(f"Not found in archive: {stats['skipped_missing']}")
    if args.dry_run:
        print("(dry run -- no changes written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
