#!/usr/bin/env python3
"""
clean_stale.py

Detect (and optionally delete) stale Markdown files in a digested archive
whose source material no longer exists in the corresponding raw tree.

Two kinds of staleness are detected:

1. **Missing source file.** A digested .md with `source_file: foo.docx` in
   its frontmatter, where `foo.docx` no longer exists anywhere under the
   raw tree. Most common cause: the source was deleted, moved out of the
   tree, or renamed in raw without re-running the pipeline.

2. **Missing export conversation.** A digested .md with `conversation_id:`
   in its frontmatter (from a Claude or ChatGPT export), where that UUID
   does not appear in any `conversations.json` under the raw tree. Most
   common cause: the conversation was deleted from the source platform
   between exports.

3. **Unidentifiable orphans.** A digested .md with no `source_file` and
   no `conversation_id` -- nothing the script can use to verify the file
   belongs to anything in the raw tree. This is the 146-untitled-Claude-
   conversations case from earlier pipeline history: files written by an
   older converter version that can't be cross-checked against the
   current export structure. These are flagged for review but the script
   is conservative -- with `--delete` it deletes only verified-stale
   (categories 1 and 2). Unidentifiable orphans require `--delete-orphans`
   to remove.

When deleting, paired `.nlm.md` sidecars are removed alongside their
canonical `.md`.

By default the script is REPORT-ONLY: it lists what it would delete and
exits 0 (or exits 1 if any stale items were found, for scripting purposes).

Files always skipped (never analyzed, never deleted):

- `.nlm.md` sidecars (handled implicitly when their .md is deleted)
- Files with `source: "Claude export (project metadata)"`,
  `"Claude export (memory)"`, `"Claude export (project memory)"`,
  `"Claude export (account)"`, or `"ChatGPT export auxiliary file"`.
  These have legitimate non-conversation sources that aren't worth
  cross-checking automatically.

Usage:
    python clean_stale.py <raw_dir> <digested_dir>
        # Report mode (default). Exits 1 if stale files found.

    python clean_stale.py <raw_dir> <digested_dir> --delete
        # Delete verified-stale .md files (and paired .nlm.md sidecars).
        # Prompts for confirmation unless --yes is given.

    python clean_stale.py <raw_dir> <digested_dir> --delete --yes
        # Delete without prompting (for scripted use).

    python clean_stale.py <raw_dir> <digested_dir> --delete-orphans
        # Also delete unidentifiable orphans (use with caution).

    python clean_stale.py <raw_dir> <digested_dir> --verbose
        # Print every file's classification, not just stale ones.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)

# Sources that aren't conversation-based and shouldn't be auto-analyzed.
# These files come from Claude's data export but represent non-conversation
# objects (project memory, user account, etc.). Leave them alone.
SKIP_SOURCES = {
    "Claude export (project metadata)",
    "Claude export (memory)",
    "Claude export (project memory)",
    "Claude export (account)",
    "ChatGPT export auxiliary file",
}


def parse_frontmatter(text: str) -> dict:
    """Minimal frontmatter parser. Returns dict of string-valued fields only.

    Borrowed from add_metadata.parse_frontmatter, simplified: we only need
    string lookups for `source`, `source_file`, and `conversation_id`.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        fm[key] = val
    return fm


def build_raw_index(raw_dir: Path, verbose: bool = False) -> tuple[set[str], set[str]]:
    """Scan the raw tree once and build two indexes:

    Returns:
        filenames: set of every filename (basename, lowercased) found in raw
        conv_uuids: set of every conversation UUID found in any
                    `conversations.json` file under raw
    """
    filenames: set[str] = set()
    conv_uuids: set[str] = set()

    if not raw_dir.is_dir():
        print(f"  [warn] raw tree not found: {raw_dir}")
        return filenames, conv_uuids

    json_files_scanned = 0
    for path in raw_dir.rglob("*"):
        if not path.is_file():
            continue
        # Index every filename so we can check source_file matches.
        filenames.add(path.name.lower())

        # Specifically pull conversation UUIDs out of conversations.json.
        # Both Claude and ChatGPT exports use this filename; their formats
        # differ but both put a "uuid" or "id" on each conversation object.
        if path.name == "conversations.json":
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                if verbose:
                    print(f"  [warn] could not parse {path}: {e}")
                continue
            if not isinstance(data, list):
                continue
            for conv in data:
                if not isinstance(conv, dict):
                    continue
                uid = conv.get("uuid") or conv.get("id") or ""
                if uid:
                    conv_uuids.add(uid)
            json_files_scanned += 1

    if verbose:
        print(f"  raw index: {len(filenames):,} filenames, "
              f"{len(conv_uuids):,} conversation UUIDs "
              f"from {json_files_scanned} conversations.json files")
    return filenames, conv_uuids


def classify_file(md_path: Path,
                  filenames: set[str],
                  conv_uuids: set[str]) -> tuple[str, str]:
    """Classify a single .md file. Returns (status, reason).

    status is one of:
        "ok"          -- source verified present in raw
        "skip"        -- non-conversation source, not analyzed
        "stale-file"  -- source_file not in raw tree
        "stale-conv"  -- conversation_id not in any raw conversations.json
        "orphan"      -- no recognizable source identifiers in frontmatter
        "no-fm"       -- file has no frontmatter at all
    """
    try:
        with md_path.open(encoding="utf-8") as f:
            head = f.read(4096)
    except OSError as e:
        return ("orphan", f"unreadable: {e}")

    fm = parse_frontmatter(head)
    if not fm:
        return ("no-fm", "no frontmatter present")

    source = fm.get("source", "")
    if source in SKIP_SOURCES:
        return ("skip", f"non-conversation source: {source}")

    source_file = fm.get("source_file", "")
    conv_id = fm.get("conversation_id", "")

    # File-based converters always set source_file. Check raw tree.
    if source_file:
        if source_file.lower() in filenames:
            return ("ok", f"source_file present: {source_file}")
        return ("stale-file", f"source_file not in raw: {source_file}")

    # Export converters set conversation_id. Check the UUID index.
    if conv_id:
        if conv_id in conv_uuids:
            return ("ok", f"conversation_id present: {conv_id[:8]}…")
        return ("stale-conv",
                f"conversation_id not in any raw conversations.json: {conv_id[:8]}…")

    # Has frontmatter but no source identifier we can verify against.
    # This is the 146-orphans signature: empty Untitled conversation files
    # from an older pipeline run that couldn't extract a conversation_id.
    return ("orphan",
            f"no source_file or conversation_id; source={source or '(unset)'}")


def find_md_files(digested_dir: Path) -> list[Path]:
    """Return canonical .md files under digested_dir, excluding .nlm.md sidecars."""
    return [p for p in digested_dir.rglob("*.md")
            if p.is_file() and not p.name.endswith(".nlm.md")]


def paired_sidecar(md_path: Path) -> Path:
    """Return the expected .nlm.md sidecar path for a canonical .md."""
    return md_path.with_suffix(".nlm.md")


def delete_with_sidecar(md_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """Delete md_path and its paired .nlm.md sidecar (if it exists).

    Returns (md_deleted, sidecar_deleted) as 0/1 counts.
    """
    md_count = 0
    nlm_count = 0
    if md_path.is_file():
        if not dry_run:
            md_path.unlink()
        md_count = 1
    sidecar = paired_sidecar(md_path)
    if sidecar.is_file():
        if not dry_run:
            sidecar.unlink()
        nlm_count = 1
    return md_count, nlm_count


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detect (and optionally delete) stale digested .md files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("raw_dir", help="Path to the raw archive tree (1-Raw)")
    ap.add_argument("digested_dir", help="Path to the digested archive tree (2-Digested)")
    ap.add_argument("--delete", action="store_true",
                    help="Delete verified-stale files (categories: stale-file, stale-conv). "
                         "Prompts for confirmation unless --yes is given.")
    ap.add_argument("--delete-orphans", action="store_true",
                    help="Also delete unidentifiable orphans (no source_file, no "
                         "conversation_id, or no frontmatter). Implies --delete. "
                         "Use with caution -- legitimate hand-edited files in the "
                         "digested tree may match this pattern.")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the confirmation prompt when --delete is in effect")
    ap.add_argument("--verbose", action="store_true",
                    help="Print every file's classification, not just stale ones")
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    digested_dir = Path(args.digested_dir)

    if not digested_dir.is_dir():
        print(f"ERROR: digested directory does not exist: {digested_dir}",
              file=sys.stderr)
        return 2

    # --delete-orphans implies --delete (otherwise the flag does nothing)
    delete_mode = args.delete or args.delete_orphans

    print()
    print("=" * 60)
    print("  Stale-file scan")
    print("=" * 60)
    print(f"  Raw     : {raw_dir}")
    print(f"  Digested: {digested_dir}")
    print(f"  Mode    : {'DELETE' if delete_mode else 'REPORT'}"
          f"{' (with orphans)' if args.delete_orphans else ''}")
    print()

    # Build raw index once. This is the expensive step; everything else is
    # cheap per-file lookups.
    filenames, conv_uuids = build_raw_index(raw_dir, verbose=args.verbose)

    md_files = find_md_files(digested_dir)
    print(f"  Scanning {len(md_files):,} digested .md files...")
    print()

    # Classify everything first, then decide what to do.
    by_status: dict[str, list[tuple[Path, str]]] = {
        "ok": [], "skip": [],
        "stale-file": [], "stale-conv": [],
        "orphan": [], "no-fm": [],
    }
    for md in md_files:
        status, reason = classify_file(md, filenames, conv_uuids)
        by_status.setdefault(status, []).append((md, reason))
        if args.verbose:
            print(f"  [{status:11s}] {md.relative_to(digested_dir)} -- {reason}")

    # Summary counts
    print("  Classification summary:")
    print(f"    ok          : {len(by_status['ok']):>6,}  (source verified)")
    print(f"    skip        : {len(by_status['skip']):>6,}  (non-conversation, not analyzed)")
    print(f"    stale-file  : {len(by_status['stale-file']):>6,}  (source_file missing from raw)")
    print(f"    stale-conv  : {len(by_status['stale-conv']):>6,}  (conversation_id missing from raw)")
    print(f"    orphan      : {len(by_status['orphan']):>6,}  (no recognizable source)")
    print(f"    no-fm       : {len(by_status['no-fm']):>6,}  (no frontmatter)")
    print()

    # Verified-stale = the two categories we can be sure about.
    stale_verified = by_status["stale-file"] + by_status["stale-conv"]
    # Orphans = unverifiable; only deleted if --delete-orphans is set.
    orphans = by_status["orphan"] + by_status["no-fm"]

    # Print the actual paths so the user can decide what to do.
    if stale_verified:
        print("  Verified-stale files:")
        for path, reason in stale_verified:
            print(f"    {path.relative_to(digested_dir)}")
            print(f"      ({reason})")
        print()

    if orphans:
        print("  Orphan / unidentifiable files:")
        for path, reason in orphans:
            print(f"    {path.relative_to(digested_dir)}")
            print(f"      ({reason})")
        print()

    if not stale_verified and not orphans:
        print("  No stale or orphan files found. Nothing to clean.")
        return 0

    # Report mode: stop here, exit 1 to signal there's something to look at.
    if not delete_mode:
        print("  (Report mode. Re-run with --delete to remove verified-stale files,")
        print("   or --delete-orphans to also remove unidentifiable orphans.)")
        return 1

    # Figure out what's actually going to be deleted.
    to_delete = list(stale_verified)
    if args.delete_orphans:
        to_delete += orphans

    if not to_delete:
        print("  Nothing to delete (no verified-stale files found; orphans require --delete-orphans).")
        return 0

    # Confirm unless --yes was given.
    if not args.yes:
        print(f"  About to delete {len(to_delete)} .md files (plus paired .nlm.md sidecars).")
        try:
            resp = input("  Proceed? [y/N]: ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("  Aborted by user.")
            return 1

    # Delete.
    md_deleted = 0
    nlm_deleted = 0
    errors = 0
    for path, _ in to_delete:
        try:
            mc, nc = delete_with_sidecar(path, dry_run=False)
            md_deleted += mc
            nlm_deleted += nc
        except OSError as e:
            errors += 1
            print(f"  [error] could not delete {path}: {e}")

    print()
    print(f"  Deleted: {md_deleted} .md files + {nlm_deleted} .nlm.md sidecars")
    if errors:
        print(f"  Errors : {errors}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
