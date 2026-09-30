#!/usr/bin/env python3
"""
clean_stale.py

Detect (and optionally delete) stale Markdown files in a digested archive
whose source material no longer exists in the corresponding raw tree.

Three conditions are detected:

1. **Absent source file.** A digested .md with `source_file: foo.docx` in
   its frontmatter, where `foo.docx` no longer exists anywhere under the
   raw tree.

2. **Absent export conversation.** A digested .md with `conversation_id:`
   in its frontmatter (from a Claude or ChatGPT export), where that UUID
   does not appear in any `conversations.json` under the raw tree.

3. **Unidentifiable orphans.** A digested .md with no `source_file` and
   no `conversation_id` -- nothing the script can use to verify the file
   belongs to anything in the raw tree. This is the 146-untitled-Claude-
   conversations case from earlier pipeline history: files written by an
   older converter version that can't be cross-checked against the
   current export structure.

**A renamed source is not a missing one.** Matching by filename cannot tell a
deleted source from a renamed one, and a spelling fix to a source filename
would otherwise orphan perfectly good output. Where a digested file records its
source's `source_sha256` and `source_bytes`, an absent source is searched for
by content before being reported: same bytes under a different name is a
RENAME, reported with both names and never deleted.

The search is cheap because size is checked first -- only raw files of exactly
the recorded size are hashed, rather than the whole tree. Files digested before
these fields existed simply have nothing to match on and fall through to the
reporting below.

**An absent source is not evidence of stale output.** From the digested side,
"the source was deleted upstream" and "the source was removed on purpose"
look identical. Both produce a digested file whose source cannot be found,
and only the corpus owner knows which happened. Bulky AI exports get cleared
to reclaim disk space after digestion; deleting the digested output in that
case destroys the only remaining copy.

So conditions 1 and 2 are reported as `source-absent` and are NOT deleted by
`--delete`. Removing them takes the dedicated `--delete-source-absent` flag,
which says explicitly that the sources are known to be gone for good.

To mark a file whose source was retired deliberately, set `source_retired:
true` in its frontmatter. This script then treats it as verified and never
counts it stale again -- the durable fix, since it survives re-runs and
records the intent in the file itself.

A bulk-delete guardrail refuses any run that would delete more than
`--max-delete-fraction` of the analyzed files (default 10%) unless `--force`
is given. A deletion that large is far more often a mis-pointed raw directory
than a real cleanup.

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
        # Deletes nothing on its own any more. Source-absent files need
        # --delete-source-absent; orphans need --delete-orphans.

    python clean_stale.py <raw_dir> <digested_dir> --delete-source-absent
        # Delete files whose source is genuinely gone for good.
        # Prompts for confirmation unless --yes is given.

    python clean_stale.py <raw_dir> <digested_dir> --delete-orphans
        # Delete unidentifiable orphans (use with caution).

    python clean_stale.py <raw_dir> <digested_dir> --verbose
        # Print every file's classification, not just stale ones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_log  # noqa: E402


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


# Frontmatter values that count as true for `source_retired`. The minimal
# parser below keeps unquoted scalars as strings, so `true` arrives as "true".
TRUE_VALUES = {"true", "yes", "1", "on"}


def is_source_retired(fm: dict) -> bool:
    """True if the owner has marked this file's source as deliberately removed.

    `source_retired: true` records the intent that an absent source is
    expected. It survives re-runs and lives in the file itself, so the
    knowledge does not depend on remembering which flag to pass.
    """
    return str(fm.get("source_retired", "")).strip().lower() in TRUE_VALUES


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


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed. Empty string if unreadable.

    Kept local rather than imported, so this script stays runnable on its own
    -- the same reason parse_frontmatter above is a local simplification.
    """
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
    except OSError:
        return ""
    return h.hexdigest()


def resolve_renames(absent: list[tuple[Path, str]], raw_dir: Path
                    ) -> tuple[list[tuple[Path, str, str]], list[tuple[Path, str]]]:
    """Split absent-source files into (renamed, still_absent).

    A digested file carrying `source_sha256` whose bytes turn up in the raw
    tree under another name was not orphaned -- its source was renamed. Size is
    matched first so only genuine size-matches are hashed.
    """
    wanted: dict[Path, tuple[int, str]] = {}
    for md_path, _reason in absent:
        try:
            head = md_path.open(encoding="utf-8").read(4096)
        except OSError:
            continue
        fm = parse_frontmatter(head)
        digest = str(fm.get("source_sha256", "") or "").strip().lower()
        size_raw = str(fm.get("source_bytes", "") or "").strip()
        if not digest or not size_raw.isdigit():
            continue
        wanted[md_path] = (int(size_raw), digest)

    if not wanted:
        return [], list(absent)

    # Only sizes we are actually looking for. Stat is cheap; hashing is not.
    sizes_wanted = {size for size, _ in wanted.values()}
    by_size: dict[int, list[Path]] = {}
    for candidate in raw_dir.rglob("*"):
        try:
            if not candidate.is_file():
                continue
            size = candidate.stat().st_size
        except OSError:
            continue
        if size in sizes_wanted:
            by_size.setdefault(size, []).append(candidate)

    hash_cache: dict[Path, str] = {}
    renamed: list[tuple[Path, str, str]] = []
    still_absent: list[tuple[Path, str]] = []

    for md_path, reason in absent:
        target = wanted.get(md_path)
        if target is None:
            still_absent.append((md_path, reason))
            continue
        size, digest = target
        match = None
        for candidate in by_size.get(size, []):
            if candidate not in hash_cache:
                hash_cache[candidate] = file_sha256(candidate)
            if hash_cache[candidate] == digest:
                match = candidate
                break
        if match is not None:
            renamed.append((md_path, reason, match.name))
        else:
            still_absent.append((md_path, reason))
    return renamed, still_absent


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
        "ok"           -- source verified present in raw
        "retired"      -- source deliberately removed; marked in frontmatter
        "skip"         -- non-conversation source, not analyzed
        "absent-file"  -- source_file not in raw tree
        "absent-conv"  -- conversation_id not in any raw conversations.json
        "orphan"       -- no recognizable source identifiers in frontmatter
        "no-fm"        -- file has no frontmatter at all

    An "absent-" status means the source cannot be found, NOT that the output
    is stale. Only the owner can tell those apart.
    """
    try:
        with md_path.open(encoding="utf-8") as f:
            head = f.read(4096)
    except OSError as e:
        return ("orphan", f"unreadable: {e}")

    fm = parse_frontmatter(head)
    if not fm:
        return ("no-fm", "no frontmatter present")

    if is_source_retired(fm):
        return ("retired", "source_retired: source removed deliberately")

    source = fm.get("source", "")
    if source in SKIP_SOURCES:
        return ("skip", f"non-conversation source: {source}")

    source_file = fm.get("source_file", "")
    conv_id = fm.get("conversation_id", "")

    # File-based converters always set source_file. Check raw tree.
    if source_file:
        if source_file.lower() in filenames:
            return ("ok", f"source_file present: {source_file}")
        return ("absent-file", f"source_file not in raw: {source_file}")

    # Export converters set conversation_id. Check the UUID index.
    if conv_id:
        if conv_id in conv_uuids:
            return ("ok", f"conversation_id present: {conv_id[:8]}…")
        return ("absent-conv",
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
                    help="Enter delete mode. On its own this now deletes NOTHING: "
                         "an absent source is not evidence that the output is "
                         "stale, so those files need --delete-source-absent and "
                         "orphans need --delete-orphans.")
    ap.add_argument("--delete-source-absent", action="store_true",
                    help="Delete files whose source_file or conversation_id "
                         "cannot be found in the raw tree. Only use this when "
                         "the sources are known to be gone for good -- if they "
                         "were cleared to reclaim disk space, this destroys the "
                         "only remaining copy. Implies --delete.")
    ap.add_argument("--delete-orphans", action="store_true",
                    help="Delete unidentifiable orphans (no source_file, no "
                         "conversation_id, or no frontmatter). Implies --delete. "
                         "Use with caution -- legitimate hand-edited files in the "
                         "digested tree may match this pattern.")
    ap.add_argument("--max-delete-fraction", type=float, default=0.10,
                    help="Refuse to delete more than this fraction of the "
                         "analyzed files (default: 0.10). A deletion that large "
                         "is usually a mis-pointed raw directory, not a cleanup. "
                         "Override with --force.")
    ap.add_argument("--force", action="store_true",
                    help="Override the bulk-delete guardrail. Requires --yes too, "
                         "so a large deletion can never be a single typo.")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the confirmation prompt when deleting")
    ap.add_argument("--verbose", action="store_true",
                    help="Print every file's classification, not just stale ones")
    ap.add_argument("--log", default=None,
                    help="Mirror this run's output to a log file. The console\n                         is unchanged; the log is what survives the window\n                         closing.")
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    digested_dir = Path(args.digested_dir)

    if not digested_dir.is_dir():
        print(f"ERROR: digested directory does not exist: {digested_dir}",
              file=sys.stderr)
        return 2

    # The specific delete flags imply --delete (otherwise they do nothing).
    delete_mode = args.delete or args.delete_orphans or args.delete_source_absent

    print()
    print("=" * 60)
    print("  Stale-file scan")
    print("=" * 60)
    print(f"  Raw     : {raw_dir}")
    print(f"  Digested: {digested_dir}")
    selected = []
    if args.delete_source_absent:
        selected.append("source-absent")
    if args.delete_orphans:
        selected.append("orphans")
    print(f"  Mode    : {'DELETE' if delete_mode else 'REPORT'}"
          f"{' (' + ', '.join(selected) + ')' if selected else ''}")
    print()

    # Build raw index once. This is the expensive step; everything else is
    # cheap per-file lookups.
    filenames, conv_uuids = build_raw_index(raw_dir, verbose=args.verbose)

    md_files = find_md_files(digested_dir)
    print(f"  Scanning {len(md_files):,} digested .md files...")
    print()

    # Classify everything first, then decide what to do.
    by_status: dict[str, list[tuple[Path, str]]] = {
        "ok": [], "retired": [], "skip": [],
        "absent-file": [], "absent-conv": [],
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
    print(f"    retired     : {len(by_status['retired']):>6,}  (source_retired: removed deliberately)")
    print(f"    skip        : {len(by_status['skip']):>6,}  (non-conversation, not analyzed)")
    print(f"    absent-file : {len(by_status['absent-file']):>6,}  (source_file not found in raw)")
    print(f"    absent-conv : {len(by_status['absent-conv']):>6,}  (conversation_id not found in raw)")
    print(f"    orphan      : {len(by_status['orphan']):>6,}  (no recognizable source)")
    print(f"    no-fm       : {len(by_status['no-fm']):>6,}  (no frontmatter)")
    print()
    print("  Resolving absent sources by content before reporting them...")

    # Source absent = the source cannot be found. NOT evidence of staleness:
    # it reads the same whether the source was deleted upstream or cleared on
    # purpose after digestion. Reported always, deleted only on demand.
    source_absent = by_status["absent-file"] + by_status["absent-conv"]

    # Before reporting anything absent, look for it under another name. A
    # source that was renamed is not a source that was lost.
    renamed: list[tuple[Path, str, str]] = []
    if source_absent:
        renamed, source_absent = resolve_renames(source_absent, raw_dir)

    # Orphans = unverifiable; only deleted if --delete-orphans is set.
    orphans = by_status["orphan"] + by_status["no-fm"]

    if renamed:
        print(f"  Renamed sources ({len(renamed)}): the source is present under")
        print("  a different name, so nothing was lost. Re-run the pipeline to")
        print("  refresh these, then remove the superseded output.")
        for path, reason, new_name in renamed:
            old_name = reason.split(": ", 1)[-1]
            print(f"    {path.relative_to(digested_dir)}")
            print(f"      {old_name}  ->  {new_name}")
        print()

    # Print the actual paths so the user can decide what to do.
    if source_absent:
        print("  Source-absent files (output kept; the source could not be found):")
        for path, reason in source_absent:
            print(f"    {path.relative_to(digested_dir)}")
            print(f"      ({reason})")
        print()

    if orphans:
        print("  Orphan / unidentifiable files:")
        for path, reason in orphans:
            print(f"    {path.relative_to(digested_dir)}")
            print(f"      ({reason})")
        print()

    if source_absent:
        print("  A source-absent file is NOT known to be stale. If these sources")
        print("  were cleared on purpose, mark the files with `source_retired: true`")
        print("  in their frontmatter and they will stop being reported.")
        print()

    if not source_absent and not orphans:
        if renamed:
            print("  No source-absent or orphan files. The renames above are the")
            print("  only finding, and nothing there needs deleting.")
            return 1
        print("  No source-absent or orphan files found. Nothing to clean.")
        return 0

    # Report mode: stop here, exit 1 to signal there's something to look at.
    if not delete_mode:
        print("  (Report mode. Deleting takes --delete-source-absent or")
        print("   --delete-orphans; --delete alone no longer removes anything.)")
        return 1

    # Figure out what's actually going to be deleted.
    to_delete: list[tuple[Path, str]] = []
    if args.delete_source_absent:
        to_delete += source_absent
    if args.delete_orphans:
        to_delete += orphans

    if not to_delete:
        print("  Nothing selected for deletion. Source-absent files need")
        print("  --delete-source-absent; orphans need --delete-orphans.")
        return 0

    # Bulk-delete guardrail. Deleting a large share of the tree is far more
    # often a mis-pointed raw directory than a real cleanup, so it has to be
    # asked for twice.
    analyzed = max(len(md_files), 1)
    fraction = len(to_delete) / analyzed
    if fraction > args.max_delete_fraction and not args.force:
        print(f"  REFUSING: this would delete {len(to_delete):,} of "
              f"{analyzed:,} files ({fraction:.1%}), above the "
              f"{args.max_delete_fraction:.1%} limit.")
        print("  Check that the raw directory is the right one and actually")
        print("  populated. If the deletion is genuinely intended, re-run with")
        print("  --force --yes, or raise --max-delete-fraction.")
        return 1
    if args.force and not args.yes:
        print("  REFUSING: --force also requires --yes, so a deletion this "
              "large cannot be a single typo.")
        return 1

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
    # The tee goes up before argparse runs, so a usage error is
    # logged too rather than vanishing with the console.
    with run_log.tee_stdio(run_log.log_path_from_argv(sys.argv),
                           header="Stale-file check"):
        raise SystemExit(main())
