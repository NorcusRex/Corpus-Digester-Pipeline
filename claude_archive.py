#!/usr/bin/env python3
"""
claude_archive.py

Merge every Claude export in a corpus into one tree, and keep the record of
which exports have been taken in.

WHY THIS EXISTS

Exports are incremental. A chat is exported, digested, and may then be
deleted from Claude, so the next export does not contain it. No export is
ever superseded by a later one: each is part of the record, and the corpus is
all of them together.

So every Claude export under the raw tier is digested into ONE tree, keyed by
conversation UUID:

  - A conversation found in several exports is written once, from its newest
    version (by the export's own date), with that export's project placement.
  - An older version is kept beside it, suffixed `__as-of-<date>`, whenever it
    holds a message the newest version lacks -- something deleted in Claude
    since. Nothing an export ever contained is dropped.
  - Nothing is removed because a later export lacks it.
  - Project metadata takes the newest version; a project-knowledge document
    is kept even if a later export no longer has it. Memories keep the newest
    and any older text that differs.

THE LEDGER

`_claude-exports.json` at the corpus root lists every export taken in: its
folder, a fingerprint of its conversations.json, its date, and how it was
accepted. The manifest gate (claude_manifests.py) runs only on an export not in
the ledger -- or in it with a different fingerprint, i.e. replaced. An export
is checked once, when it arrives, and never again: re-checking history every
run would let one old slip block every future digest.

An export made before manifests were checked cannot pass the gate, and is not
wrong for that. It is taken in once, deliberately:

    python claude_archive.py accept <export folder> [--corpus-root DIR]

which records it as "accepted without manifest check". The ledger sits at the
corpus root, outside 2-Digested, so `--clean` does not erase it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import claude_manifests  # noqa: E402
import claude_to_markdown as c2m  # noqa: E402

LEDGER_NAME = "_claude-exports.json"
MERGED_DIR = "claude-merged"


# ---------------------------------------------------------------------------
# Exports: identity and date
# ---------------------------------------------------------------------------

def fingerprint(export_dir: Path) -> str:
    """sha256 of conversations.json: changes if the export is replaced."""
    h = hashlib.sha256()
    try:
        with (export_dir / "conversations.json").open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def export_time(conversations: list) -> datetime:
    """When the export was taken, from its contents: the latest activity in
    it. A folder's name or modified time says when it was unzipped or copied,
    not when the export was made."""
    latest = None
    for c in conversations:
        if not isinstance(c, dict):
            continue
        t = claude_manifests.last_activity(c)
        if t and (latest is None or t > latest):
            latest = t
    return latest or datetime.min.replace(tzinfo=timezone.utc)


def as_of_label(t: datetime, taken: set[str]) -> str:
    """`YYYY-MM-DD`, or with `-HHMM` when two exports share a day."""
    local = t.astimezone() if t.year > 1 else t
    label = local.strftime("%Y-%m-%d")
    if label in taken:
        label = local.strftime("%Y-%m-%d-%H%M")
    taken.add(label)
    return label


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def ledger_path(corpus_root: Path) -> Path:
    return corpus_root / LEDGER_NAME


def load_ledger(corpus_root: Path) -> dict:
    path = ledger_path(corpus_root)
    if not path.is_file():
        return {"exports": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: the export ledger {path} cannot be read "
                         f"({e}). It records which exports were checked; "
                         f"fix or restore it rather than deleting it.")
    data.setdefault("exports", {})
    return data


def save_ledger(corpus_root: Path, ledger: dict) -> None:
    path = ledger_path(corpus_root)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def ledger_key(export_dir: Path, corpus_root: Path) -> str:
    try:
        return export_dir.resolve().relative_to(corpus_root.resolve()).as_posix()
    except ValueError:
        return export_dir.resolve().as_posix()


def is_recorded(ledger: dict, key: str, fp: str) -> bool:
    entry = ledger["exports"].get(key)
    return bool(entry) and entry.get("fingerprint") == fp


def record(ledger: dict, key: str, fp: str, conversations: list,
           how: str) -> None:
    ledger["exports"][key] = {
        "fingerprint": fp,
        "export_date": export_time(conversations).isoformat(timespec="minutes"),
        "conversations": sum(1 for c in conversations if isinstance(c, dict)),
        "accepted": how,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="minutes"),
    }


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

class Export:
    """One export, loaded and resolved."""

    def __init__(self, path: Path, data: "c2m.ExportData",
                 resolution: "claude_manifests.Resolution"):
        self.path = path
        self.data = data
        self.resolution = resolution
        self.time = export_time(data.conversations)
        self.label = ""


def message_ids(conv: dict) -> set[str]:
    return {m.get("uuid") for m in conv.get("chat_messages") or []
            if isinstance(m, dict) and m.get("uuid")}


def merge(exports: list[Export]) -> tuple["c2m.ExportData", dict]:
    """One ExportData from several, oldest export first in `exports`.

    Returns the merged data and a small report for the run summary.
    """
    exports = sorted(exports, key=lambda e: (e.time, str(e.path)))
    taken: set[str] = set()
    for e in exports:
        e.label = as_of_label(e.time, taken)

    # Conversations: every version, oldest first.
    versions: dict[str, list[tuple[Export, dict]]] = {}
    for e in exports:
        for conv in e.data.conversations:
            if isinstance(conv, dict) and conv.get("uuid"):
                versions.setdefault(conv["uuid"], []).append((e, conv))

    merged = c2m.ExportData()
    res = claude_manifests.Resolution()
    report = {"exports": len(exports), "conversations": len(versions),
              "in_several_exports": 0, "earlier_versions_kept": 0}

    for uuid, vs in versions.items():
        newest_export, newest = vs[-1]
        merged.conversations.append(newest)
        if len(vs) > 1:
            report["in_several_exports"] += 1
        keep = message_ids(newest)
        for e, conv in vs[:-1]:
            if message_ids(conv) - keep:
                merged.earlier.append((conv, e.label))
                report["earlier_versions_kept"] += 1
        # Placement from the newest export that places it.
        for e, _ in reversed(vs):
            pid = e.resolution.conv_to_project.get(uuid)
            if pid:
                res.conv_to_project[uuid] = pid
                title = e.resolution.title_in_manifest.get(uuid)
                if title:
                    res.title_in_manifest[uuid] = title
                break

    # Projects: newest metadata, every knowledge document ever seen.
    projects: dict[str, dict] = {}
    docs: dict[str, dict[str, dict]] = {}
    for e in exports:
        for label, meta in e.data.project_metadata:
            pid = meta.get("uuid")
            if not pid:
                continue
            projects[pid] = (label, meta)
            for d in meta.get("docs") or []:
                if isinstance(d, dict):
                    key = d.get("uuid") or c2m.project_doc_name(d)
                    docs.setdefault(pid, {})[key] = d
        res.project_names.update(e.resolution.project_names)
        res.name_fallbacks += e.resolution.name_fallbacks
        for pid, mf in e.resolution.chosen.items():
            res.chosen[pid] = mf
        for pid, mfs in e.resolution.history.items():
            seen = {(m.filename, m.text) for m in res.history.get(pid, [])}
            for m in mfs:
                if (m.filename, m.text) not in seen:
                    res.history.setdefault(pid, []).append(m)
        res.notes += e.resolution.notes
    for pid, (label, meta) in projects.items():
        meta = dict(meta)
        meta["docs"] = list(docs.get(pid, {}).values())
        merged.project_metadata.append((label, meta))

    merged.memory_versions = [(e.label, m) for e in exports
                              for _, m in e.data.memory_versions]
    for e in reversed(exports):
        if e.data.users is not None:
            merged.users = e.data.users
            break
    merged.resolution = res
    return merged, report


# ---------------------------------------------------------------------------
# Tidy: a conversation written somewhere new this run
# ---------------------------------------------------------------------------

ID_RE = re.compile(r'^conversation_id:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
ASOF_RE = re.compile(r'^as_of_export:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def tidy_moved(merged_out: Path, written: dict) -> list[Path]:
    """Remove the old file of a conversation this run wrote elsewhere.

    A chat moved to another project, or renamed in Claude, is written to a
    new path; its previous file would otherwise sit on as a second copy.
    Only a conversation THIS run wrote is touched -- the same conversation,
    still in the raw exports, now living at another path. A conversation no
    longer in any export is never removed here: that is clean_stale.py's
    question, and it only reports.

    Removes the file, its .nlm.md sidecar, and its recovered-outputs folder
    (only if that folder carries the recovered-outputs manifest).
    """
    from claude_outputs import MANIFEST_NAME, OUTPUTS_DIR_SUFFIX
    removed: list[Path] = []
    root = merged_out / "conversations"
    if not root.is_dir():
        return removed
    keep = {p.resolve() for p in written.values()}
    for md in sorted(root.rglob("*.md")):
        if md.name.endswith(".nlm.md") or md.resolve() in keep:
            continue
        if any(part.endswith(OUTPUTS_DIR_SUFFIX) for part in
               md.relative_to(root).parts[:-1]):
            continue
        try:
            head = md.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        fm = head.split("\n---", 1)[0]
        m = ID_RE.search(fm)
        if not m:
            continue
        a = ASOF_RE.search(fm)
        key = (m.group(1).strip(), a.group(1).strip() if a else "")
        if key not in written:
            continue
        md.unlink()
        removed.append(md)
        sidecar = md.with_suffix(".nlm.md")
        if sidecar.exists():
            sidecar.unlink()
        outputs = md.with_name(md.stem + OUTPUTS_DIR_SUFFIX)
        if outputs.is_dir() and (outputs / MANIFEST_NAME).is_file():
            shutil.rmtree(outputs)
    # Project folders left empty by the moves.
    for d in sorted((p for p in root.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return removed


# ---------------------------------------------------------------------------
# accept
# ---------------------------------------------------------------------------

def accept(export_dir: Path, corpus_root: Path) -> int:
    """Take in an export made before manifests were checked, once."""
    if not c2m.is_claude_export(export_dir):
        print(f"ERROR: {export_dir} is not a Claude export.", file=sys.stderr)
        return 2
    ledger = load_ledger(corpus_root)
    key = ledger_key(export_dir, corpus_root)
    fp = fingerprint(export_dir)
    if is_recorded(ledger, key, fp):
        print(f"Already in the ledger: {key} "
              f"({ledger['exports'][key]['accepted']}).")
        return 0
    try:
        convs = json.loads((export_dir / "conversations.json")
                           .read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"ERROR: conversations.json cannot be read: {e}", file=sys.stderr)
        return 2
    res = claude_manifests.resolve(export_dir, convs)
    if res.problems:
        print(f"{export_dir} would not pass the manifest check:")
        for p in res.problems:
            print(f"  - {p}")
        print()
    record(ledger, key, fp, convs if isinstance(convs, list) else [],
           "without manifest check")
    save_ledger(corpus_root, ledger)
    print(f"Accepted without manifest check: {key}")
    print(f"Recorded in {ledger_path(corpus_root)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Claude export archive: accept an export made before "
                    "manifests were checked.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("accept", help="Take in a pre-gate export, once")
    a.add_argument("export", help="The export folder (holds conversations.json)")
    a.add_argument("--corpus-root", default=None,
                   help="The corpus root (default: the parent of the tier "
                        "holding the export, found by looking for 1-Raw)")
    args = ap.parse_args()
    export = Path(args.export).resolve()
    if args.corpus_root:
        root = Path(args.corpus_root).resolve()
    else:
        root = next((p.parent for p in export.parents if p.name == "1-Raw"),
                    None)
        if root is None:
            print("ERROR: the export is not under a 1-Raw folder; pass "
                  "--corpus-root.", file=sys.stderr)
            return 2
    return accept(export, root)


if __name__ == "__main__":
    raise SystemExit(main())
