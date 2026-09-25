#!/usr/bin/env python3
"""
pipeline_selfcheck.py

Check the pipeline's own output after a run.

This is offline Python over local files, where the whole tree is in hand and
computation is cheap. It is not the corpus-audit skill's job, which sees only
Drive, and it is not `rclone check`'s job, which reconciles local against the
mirror. It is the exhaustive mechanical pass that only makes sense where the
files actually are.

Six checks:

1. **Completeness.** Every file in `1-Raw` is accounted for in `2-Digested` --
   converted, copied through, or represented by a sidecar. A silent drop is
   the failure this exists to prevent.
2. **Index integrity.** `_index.json` entries that point at absent files, and
   Markdown files absent from the index.
3. **Frontmatter.** Files in `2-Digested` and `3-Reporting` missing `title`,
   `keywords`, `date` or `source`. `4-Canon` is exempt: released artifacts are
   often authored outside any tooling and legitimately carry none.
4. **Filename conformance.** Authored documents should be named by version
   where a version exists and by timestamp where none does.
5. **Duplicate content.** Sources duplicate across formats -- .docx, Google
   Docs, PDF, Evernote and conversation exports of the same material. All
   convert to Markdown first, so the comparison is uniform. Candidates are
   found by fingerprinting several windows through each document, not only the
   head, because a pasted copy may begin at a different point than an export
   of the same conversation.
6. **Suggest, never delete.** This script has no deletion path at all. Where
   two documents overlap it reports the passages present in one and not the
   other, because **that is where hand-added commentary lives and it must not
   be lost to deduplication.**

Only the four tier names are architectural. Everything below them is
enumerated, never resolved by a name seen before.

Usage
-----
    python pipeline_selfcheck.py I:\\RPG\\_Design\\Loom
    python pipeline_selfcheck.py <corpus_root> --report audit.md
    python pipeline_selfcheck.py <corpus_root> --skip-duplicates
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import add_metadata  # noqa: E402

TIER_RAW       = "1-Raw"
TIER_DIGESTED  = "2-Digested"
TIER_REPORTING = "3-Reporting"
TIER_CANON     = "4-Canon"

# Frontmatter fields the pipeline writes and search relies on.
REQUIRED_FIELDS = ("title", "keywords", "date", "source")

# Not corpus content. The distinction is by role, not by naming pattern,
# though a leading underscore or dot marks most of them.
EXCLUDED_DIR_NAMES = {"_audit", "_Tools", "__pycache__", "node_modules"}
EXCLUDED_FILE_NAMES = {"DIRTREE.txt", "FILETREE.txt", "tree.txt",
                       ".DS_Store", "Thumbs.db"}
EXCLUDED_FILE_PREFIXES = ("~$",)          # Office lock files
EXCLUDED_FILE_SUFFIXES = (".pyc",)

# Authored filenames: version where a version exists, timestamp where none does.
VERSIONED_NAME_RE = re.compile(r"^.+-(?:v\d+(?:\.\d+)*|draft\d*)\.[A-Za-z0-9]+$",
                               re.IGNORECASE)
TIMESTAMPED_NAME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}-\d{4}__[a-z0-9]+(?:-[a-z0-9]+)*\.[A-Za-z0-9]+$")

# Duplicate fingerprinting.
WINDOW_TOKENS = 40      # tokens per fingerprint window
WINDOW_COUNT = 8        # windows taken through each document
MIN_PASSAGE = 15        # tokens; shorter differences are noise
MAX_DIFF_TOKENS = 20000  # cap per document when diffing a candidate pair
MAX_PAIRS_DIFFED = 200


# ---------------------------------------------------------------------------
# Tree walking
# ---------------------------------------------------------------------------

def is_excluded(path: Path, root: Path) -> bool:
    """True for utility files and folders that are not corpus content.

    Delegates to add_metadata so the digester and this check cannot drift
    apart. They did once, and sidecars turned that into visible noise.
    """
    return add_metadata.is_utility_path(path, root)


def walk_content(root: Path) -> list[Path]:
    """Every content file under root, utility files excluded."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and not is_excluded(p, root))


def find_export_roots(raw_root: Path) -> set[Path]:
    """Folders that are AI data exports, converted wholesale rather than
    file by file. Detected by content, not by folder name.

    ChatGPT: `user.json` plus at least one `conversations*.json`.
    Claude:  `users.json` plus `conversations.json` plus a `projects/` folder.
    """
    roots: set[Path] = set()
    for marker in ("user.json", "users.json"):
        for hit in raw_root.rglob(marker):
            if not hit.is_file():
                continue
            parent = hit.parent
            if marker == "user.json":
                ok = any(parent.glob("conversations*.json"))
            else:
                ok = ((parent / "conversations.json").is_file()
                      and (parent / "projects").is_dir())
            if ok:
                try:
                    roots.add(parent.resolve())
                except OSError:
                    continue
    return roots


def inside_any(path: Path, roots: set[Path]) -> bool:
    if not roots:
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Digested-tree index
# ---------------------------------------------------------------------------

class DigestedIndex:
    """What the digested tree contains, in the forms the checks need."""

    def __init__(self, digested_root: Path, corpus_root: Path):
        self.root = digested_root
        self.corpus_root = corpus_root
        self.files: list[Path] = walk_content(digested_root)
        self.md_files: list[Path] = [
            f for f in self.files
            if f.suffix.lower() == ".md" and not f.name.endswith(".nlm.md")
        ]
        self.rel_paths: set[str] = {
            f.relative_to(digested_root).as_posix() for f in self.files
        }
        self.names: set[str] = {f.name.lower() for f in self.files}
        self.frontmatter: dict[Path, dict] = {}
        self.source_files: set[str] = set()
        self.source_paths: set[str] = set()
        # Content identity of the sources, so a renamed original is still
        # recognised as accounted for.
        self.source_hashes: set[str] = set()
        self.source_sizes: set[int] = set()
        self.output_dirs: set[str] = {
            f.parent.relative_to(digested_root).as_posix() for f in self.files
        }

        for md in self.md_files:
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, _ = add_metadata.parse_frontmatter(text)
            self.frontmatter[md] = fm
            sf = str(fm.get("source_file", "") or "").strip().lower()
            if sf:
                self.source_files.add(sf)
            sp = str(fm.get("source_path", "") or "").strip()
            if sp:
                self.source_paths.add(sp.replace("\\", "/").lower())
            digest = str(fm.get(add_metadata.SOURCE_HASH_FIELD, "") or "").strip().lower()
            if digest:
                self.source_hashes.add(digest)
            size = fm.get(add_metadata.SOURCE_SIZE_FIELD)
            if isinstance(size, int):
                self.source_sizes.add(size)

    def accounts_for(self, raw_file: Path, raw_root: Path) -> bool:
        """True if this raw file has a counterpart in the digested tree."""
        rel = raw_file.relative_to(raw_root)
        rel_posix = rel.as_posix()

        # Copied through unchanged at the mirrored path.
        if rel_posix in self.rel_paths:
            return True
        # Converted to Markdown beside where it would have landed.
        if rel.with_suffix(".md").as_posix() in self.rel_paths:
            return True
        # Sidecar keeps the original's full name, extension included.
        if f"{rel_posix}.md" in self.rel_paths:
            return True
        # A converter recorded it, wherever the output landed.
        if raw_file.name.lower() in self.source_files:
            return True
        # A sidecar recorded its corpus-relative path.
        try:
            corpus_rel = raw_file.relative_to(self.corpus_root).as_posix().lower()
        except ValueError:
            corpus_rel = ""
        if corpus_rel and corpus_rel in self.source_paths:
            return True
        # The same filename somewhere in the tree. Weaker than a path match,
        # but a real counterpart rather than a silent drop.
        if raw_file.name.lower() in self.names:
            return True
        # Finally, by content. A renamed source is not a missing one, and a
        # name match is not available once it has been renamed. Size is checked
        # first so only a plausible candidate is ever hashed.
        try:
            size = raw_file.stat().st_size
        except OSError:
            return False
        if size not in self.source_sizes:
            return False
        return add_metadata.file_sha256(raw_file) in self.source_hashes


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_completeness(raw_root: Path, index: DigestedIndex) -> list[str]:
    """Every file in 1-Raw must be accounted for in 2-Digested."""
    findings: list[str] = []
    export_roots = find_export_roots(raw_root)
    export_out_ok: dict[Path, bool] = {}

    for export_root in export_roots:
        # An export is converted wholesale. It is accounted for when the
        # mirrored output folder exists and holds Markdown.
        try:
            rel = export_root.relative_to(raw_root.resolve()).as_posix()
        except ValueError:
            rel = export_root.name
        export_out_ok[export_root] = any(
            d == rel or d.startswith(rel + "/") for d in index.output_dirs
        )

    for raw_file in walk_content(raw_root):
        if inside_any(raw_file, export_roots):
            owner = next((r for r in export_roots if inside_any(raw_file, {r})),
                         None)
            if owner is not None and export_out_ok.get(owner, False):
                continue
        if index.accounts_for(raw_file, raw_root):
            continue
        findings.append(raw_file.relative_to(raw_root).as_posix())
    return findings


def check_index(index: DigestedIndex) -> tuple[list[str], list[str], str]:
    """Compare _index.json against what is actually on disk."""
    index_path = index.root / "_index.json"
    legacy = index.root / "_manifest.json"
    # The old name does not mean the index is missing.
    if not index_path.is_file() and legacy.is_file():
        index_path = legacy
    if not index_path.is_file():
        return [], [], "no index found"

    try:
        with index_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [], [], f"index unreadable: {e}"

    listed = {str(e.get("path", "")).replace("\\", "/")
              for e in data.get("files", []) if e.get("path")}
    on_disk = {f.relative_to(index.root).as_posix() for f in index.md_files}

    missing_files = sorted(listed - on_disk)   # index points at nothing
    missing_entries = sorted(on_disk - listed)  # file absent from the index
    return missing_files, missing_entries, index_path.name


def check_frontmatter(tiers: dict[str, Path]) -> dict[str, list[tuple[str, list[str]]]]:
    """Report Markdown missing required fields. 4-Canon is exempt by design."""
    results: dict[str, list[tuple[str, list[str]]]] = {}
    for tier_name in (TIER_DIGESTED, TIER_REPORTING):
        root = tiers.get(tier_name)
        if root is None or not root.is_dir():
            continue
        rows: list[tuple[str, list[str]]] = []
        for md in walk_content(root):
            if md.suffix.lower() != ".md" or md.name.endswith(".nlm.md"):
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, _ = add_metadata.parse_frontmatter(text)
            missing = [k for k in REQUIRED_FIELDS
                       if not str(fm.get(k, "") or "").strip()]
            if missing:
                rows.append((md.relative_to(root).as_posix(), missing))
        if rows:
            results[tier_name] = rows
    return results


def check_filenames(tiers: dict[str, Path]) -> list[str]:
    """Authored documents: version where a version exists, timestamp where none.

    Applied to 3-Reporting only. Files in 2-Digested inherit their source's
    name by design, and 4-Canon artifacts are named by whatever released them.
    """
    root = tiers.get(TIER_REPORTING)
    if root is None or not root.is_dir():
        return []
    bad: list[str] = []
    for f in walk_content(root):
        if f.suffix.lower() != ".md" or f.name.endswith(".nlm.md"):
            continue
        if VERSIONED_NAME_RE.match(f.name) or TIMESTAMPED_NAME_RE.match(f.name):
            continue
        bad.append(f.relative_to(root).as_posix())
    return bad


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def normalized_tokens(path: Path) -> list[str]:
    """Lowercase word tokens with frontmatter, generated index and code removed."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    _, body = add_metadata.parse_frontmatter(text)
    body = add_metadata.INDEX_BLOCK_RE.sub(" ", body)
    body = add_metadata.strip_code(body)
    return [w.lower() for w in add_metadata.WORD_RE.findall(body)]


def fingerprints(tokens: list[str]) -> set[str]:
    """Hashes of several windows taken through the document.

    Several windows rather than only the head: a pasted copy may begin at a
    different point than an export of the same conversation, so a head-only
    fingerprint would miss the match entirely.
    """
    if len(tokens) < WINDOW_TOKENS:
        return set()
    span = len(tokens) - WINDOW_TOKENS
    step = max(1, span // max(1, WINDOW_COUNT - 1))
    out: set[str] = set()
    for start in range(0, span + 1, step):
        window = " ".join(tokens[start:start + WINDOW_TOKENS])
        out.add(hashlib.blake2b(window.encode("utf-8"), digest_size=16).hexdigest())
        if len(out) >= WINDOW_COUNT:
            break
    return out


def differing_passages(a: list[str], b: list[str]) -> tuple[list[str], list[str]]:
    """Passages present in one document and not the other.

    These are what deduplication would destroy. Hand-added commentary on a
    pasted conversation lives exactly here.
    """
    a = a[:MAX_DIFF_TOKENS]
    b = b[:MAX_DIFF_TOKENS]
    only_a: list[str] = []
    only_b: list[str] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace") and (i2 - i1) >= MIN_PASSAGE:
            only_a.append(" ".join(a[i1:i2])[:300])
        if tag in ("insert", "replace") and (j2 - j1) >= MIN_PASSAGE:
            only_b.append(" ".join(b[j1:j2])[:300])
    return only_a, only_b


def check_duplicates(index: DigestedIndex) -> tuple[list[dict], int]:
    """Find candidate duplicate pairs and report where they differ."""
    by_hash: dict[str, list[Path]] = defaultdict(list)
    tokens_by_file: dict[Path, list[str]] = {}

    for md in index.md_files:
        toks = normalized_tokens(md)
        if len(toks) < WINDOW_TOKENS:
            continue
        tokens_by_file[md] = toks
        for h in fingerprints(toks):
            by_hash[h].append(md)

    pairs: set[tuple[Path, Path]] = set()
    for paths in by_hash.values():
        if len(paths) < 2:
            continue
        ordered = sorted(set(paths))
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pairs.add((ordered[i], ordered[j]))

    results: list[dict] = []
    for n, (a, b) in enumerate(sorted(pairs)):
        if n >= MAX_PAIRS_DIFFED:
            break
        ta, tb = tokens_by_file.get(a, []), tokens_by_file.get(b, [])
        only_a, only_b = differing_passages(ta, tb)
        results.append({
            "a": a.relative_to(index.root).as_posix(),
            "b": b.relative_to(index.root).as_posix(),
            "a_tokens": len(ta),
            "b_tokens": len(tb),
            "only_a": only_a,
            "only_b": only_b,
            "identical": not only_a and not only_b,
        })
    return results, len(pairs)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class Report:
    """Collects lines for the console and, optionally, a Markdown file."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.findings = 0

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def section(self, title: str) -> None:
        self.say()
        self.say(f"## {title}")
        self.say()

    def listing(self, items: list[str], limit: int, noun: str) -> None:
        for item in items[:limit]:
            self.say(f"  - {item}")
        if len(items) > limit:
            self.say(f"  ... and {len(items) - limit:,} more {noun}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check the pipeline's output. Reports only; never deletes.")
    ap.add_argument("corpus_root",
                    help="Corpus root: the folder holding the four tiers")
    ap.add_argument("--report", default=None,
                    help="Also write the findings to this Markdown file")
    ap.add_argument("--max-listed", type=int, default=50,
                    help="Cap on items listed per finding (default: 50)")
    ap.add_argument("--skip-duplicates", action="store_true",
                    help="Skip duplicate detection, the slowest check")
    args = ap.parse_args()

    corpus_root = Path(args.corpus_root).resolve()
    if not corpus_root.is_dir():
        print(f"ERROR: not a directory: {corpus_root}", file=sys.stderr)
        return 2

    # The four tier names are architectural: resolve them by name. Everything
    # below them is enumerated.
    tiers = {name: corpus_root / name
             for name in (TIER_RAW, TIER_DIGESTED, TIER_REPORTING, TIER_CANON)}
    missing_tiers = [n for n, p in tiers.items() if not p.is_dir()]

    r = Report()
    r.say("# Pipeline self-check")
    r.say()
    r.say(f"Corpus: `{corpus_root}`")
    if missing_tiers:
        r.say()
        r.say(f"Tiers not present: {', '.join(missing_tiers)}. "
              f"Checks needing them are skipped.")

    if not tiers[TIER_RAW].is_dir() or not tiers[TIER_DIGESTED].is_dir():
        r.say()
        r.say("ERROR: 1-Raw and 2-Digested are both required.")
        return 2

    index = DigestedIndex(tiers[TIER_DIGESTED], corpus_root)
    r.say()
    r.say(f"Digested files: {len(index.files):,} "
          f"({len(index.md_files):,} Markdown)")

    counts: Counter = Counter()

    # --- 1. Completeness --------------------------------------------------
    r.section("1. Completeness of 2-Digested")
    unaccounted = check_completeness(tiers[TIER_RAW], index)
    if unaccounted:
        counts["unaccounted"] = len(unaccounted)
        r.say(f"**{len(unaccounted):,} file(s) in 1-Raw have no counterpart "
              f"in 2-Digested.** Each was neither converted, copied, nor "
              f"given a sidecar.")
        r.say()
        r.listing(unaccounted, args.max_listed, "files")
    else:
        r.say("Every file in 1-Raw is accounted for.")

    # --- 2. Index integrity ----------------------------------------------
    r.section("2. Index integrity")
    dangling, unindexed, index_name = check_index(index)
    if index_name == "no index found":
        r.say("No `_index.json` or `_manifest.json` in 2-Digested. "
              "Run the pipeline to write one.")
        counts["no_index"] = 1
    else:
        r.say(f"Index: `{index_name}`")
        r.say()
        if dangling:
            counts["dangling"] = len(dangling)
            r.say(f"**{len(dangling):,} index entry/entries point at files "
                  f"that do not exist.**")
            r.listing(dangling, args.max_listed, "entries")
            r.say()
        if unindexed:
            counts["unindexed"] = len(unindexed)
            r.say(f"**{len(unindexed):,} Markdown file(s) are absent from "
                  f"the index.**")
            r.listing(unindexed, args.max_listed, "files")
            r.say()
        if not dangling and not unindexed:
            r.say("Index matches the tree in both directions.")

    # --- 3. Frontmatter ---------------------------------------------------
    r.section("3. Frontmatter")
    r.say("`4-Canon` is exempt: released artifacts legitimately carry none.")
    r.say()
    fm_results = check_frontmatter(tiers)
    if fm_results:
        for tier_name, rows in fm_results.items():
            counts["frontmatter"] += len(rows)
            field_counts = Counter(f for _, miss in rows for f in miss)
            r.say(f"**{tier_name}: {len(rows):,} file(s) missing required "
                  f"fields.** By field: "
                  + ", ".join(f"{k} ({v:,})"
                              for k, v in sorted(field_counts.items())))
            r.say()
            r.listing([f"{p} -- missing {', '.join(m)}" for p, m in rows],
                      args.max_listed, "files")
            r.say()
    else:
        r.say("All required fields present.")

    # --- 4. Filenames -----------------------------------------------------
    r.section("4. Filename conformance")
    r.say("Applied to 3-Reporting. Version where a version exists, timestamp "
          "where none does.")
    r.say()
    bad_names = check_filenames(tiers)
    if bad_names:
        counts["filenames"] = len(bad_names)
        r.say(f"**{len(bad_names):,} file(s) match neither form.**")
        r.listing(bad_names, args.max_listed, "files")
    elif tiers[TIER_REPORTING].is_dir():
        r.say("All names conform.")
    else:
        r.say("3-Reporting not present; skipped.")

    # --- 5. Duplicates ----------------------------------------------------
    r.section("5. Duplicate content")
    if args.skip_duplicates:
        r.say("Skipped (--skip-duplicates).")
    else:
        dupes, pair_count = check_duplicates(index)
        if dupes:
            counts["duplicates"] = pair_count
            r.say(f"**{pair_count:,} candidate duplicate pair(s).** "
                  f"Showing {len(dupes):,}.")
            r.say()
            r.say("Where two documents overlap, the passages below are present "
                  "in one and not the other. **That is where hand-added "
                  "commentary lives. Do not lose it to deduplication.**")
            r.say()
            for d in dupes[:args.max_listed]:
                r.say(f"### `{d['a']}` vs `{d['b']}`")
                r.say()
                if d["identical"]:
                    r.say("  No material difference found.")
                    r.say()
                    continue
                for label, key in (("Only in the first", "only_a"),
                                   ("Only in the second", "only_b")):
                    if d[key]:
                        r.say(f"  {label} ({len(d[key])} passage(s)):")
                        for passage in d[key][:3]:
                            r.say(f"    > {passage}")
                        if len(d[key]) > 3:
                            r.say(f"    ... and {len(d[key]) - 3} more")
                        r.say()
        else:
            r.say("No candidate duplicates found.")

    # --- Summary ----------------------------------------------------------
    r.section("Summary")
    if not counts:
        r.say("No findings.")
    else:
        for key, label in (
            ("unaccounted", "files in 1-Raw with no counterpart"),
            ("no_index", "missing index"),
            ("dangling", "index entries pointing at absent files"),
            ("unindexed", "Markdown files absent from the index"),
            ("frontmatter", "files missing required frontmatter"),
            ("filenames", "files not matching either naming form"),
            ("duplicates", "candidate duplicate pairs"),
        ):
            if counts[key]:
                r.say(f"  {counts[key]:>7,}  {label}")
    r.say()
    r.say("Nothing here has been changed or removed. Deletion is the owner's.")

    if args.report:
        try:
            Path(args.report).write_text("\n".join(r.lines) + "\n",
                                         encoding="utf-8")
            print(f"\nReport written to {args.report}")
        except OSError as e:
            print(f"\n[warn] could not write report: {e}", file=sys.stderr)

    return 1 if counts else 0


if __name__ == "__main__":
    raise SystemExit(main())
