#!/usr/bin/env python3
"""
split_export.py

Split one AI data export into per-project exports, before any conversion.

WHY THIS EXISTS

An AI export is topic-blind: one bundle covering every subject you have ever
discussed. A corpus wants one project out of it. Until now the only way to get
there was to digest the whole export into Markdown, then mirror the project
folders that digestion produced into the corpus that wanted them -- and that
corpus then digested the Markdown again. Every conversation was converted
twice, and the first conversion existed only to make folders.

This script makes the folders without converting anything. The grouping
information -- which conversation belongs to which project -- is a plain JSON
read that never needed a converter. What comes out is a set of ordinary
exports, each holding one project's conversations in the provider's own
format, which the pipeline then digests once, in the corpus that keeps it.

    export/                        split/
      conversations.json  ---->      project_abc12345__rpg-the-loom/
      users.json                       conversations.json   (that project only)
      projects/                        users.json
        <uuid>.json                    projects/<uuid>.json
        <uuid>_manifest.json           projects/<uuid>_manifest.json
      memories.json                    memories.json        (that project only)
                                     project_def67890__rpg-theory/
                                       ...
                                     _ungrouped/
                                       conversations.json   (no project)
                                       users.json
                                       memories.json        (account-level)

Each output folder is a valid export in its own right: point the pipeline at
it and it converts exactly as it would the original.

ONE WRITER PER SOURCE

The sources do not share a grouping mechanism. Claude's lives in project
manifests beside the conversations; ChatGPT's is a field on each conversation.
So each gets its own writer, and the entry point dispatches on what the folder
looks like.

  Claude   -- implemented here.
  ChatGPT  -- not yet. It carries real media files, and how an export
              references them has changed across versions, so the routing
              needs `inspect_chatgpt_assets.py` run against a real export
              first. Until then this script refuses rather than guesses.
  Evernote -- not applicable. An Evernote export is already one HTML file per
              note in whatever folders you chose at export time, so there is
              no bundle to split. Those files go straight into `1-Raw`.

WHAT IT DOES NOT DO

It does not convert, digest, index or delete. It reads an export and writes
copies. The original is never modified, and re-running overwrites its own
output rather than accumulating.

USAGE

    python split_export.py EXPORT_DIR OUT_DIR
    python split_export.py EXPORT_DIR OUT_DIR --dry-run
    python split_export.py EXPORT_DIR OUT_DIR --only <project-uuid>

EXIT CODES

    0  split completed
    1  completed, but something needs attention (an empty split, a manifest
       naming conversations the export does not contain)
    2  a usage or path error, or a source with no writer yet
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import claude_to_markdown as c2m  # noqa: E402

UNGROUPED_DIR = "_ungrouped"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def read_json(path: Path):
    """Parse a JSON file, or return None with a warning. Never raises."""
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] could not read {path.name}: {e}", file=sys.stderr)
        return None


def write_json(path: Path, data, dry_run: bool) -> None:
    """Write JSON in the shape the providers use: UTF-8, 2-space, not ASCII-escaped."""
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def claude_grouping(export_dir: Path) -> tuple[dict, dict, dict, dict]:
    """Read the export's project structure without converting anything.

    Returns:
      conv_to_project    {conversation_uuid: project_uuid}
      project_name       {project_uuid: display name}
      metadata_files     {project_uuid: [Path, ...]}  files to carry along
      manifest_uuids     {project_uuid: {conversation_uuid, ...}} as claimed

    This mirrors what `claude_to_markdown.convert_export` does in its first
    pass. It is reimplemented rather than imported because that pass is
    interleaved with rendering; keeping a second, smaller reader here is
    honest about the duplication and avoids reshaping the converter while it
    is in use. If the two ever disagree, the converter is authoritative.
    """
    conv_to_project: dict[str, str] = {}
    project_name: dict[str, str] = {}
    metadata_files: dict[str, list[Path]] = defaultdict(list)
    manifest_uuids: dict[str, set[str]] = defaultdict(set)

    projects_dir = export_dir / "projects"
    if not projects_dir.is_dir():
        return conv_to_project, project_name, metadata_files, manifest_uuids

    for jp in sorted(projects_dir.glob("*.json")):
        data = read_json(jp)
        if data is None:
            continue
        if c2m._looks_like_manifest(data):
            pid = data.get("project_uuid") or ""
            if not pid:
                continue
            metadata_files[pid].append(jp)
            name = data.get("project_name") or ""
            if name and not project_name.get(pid):
                project_name[pid] = name
            for entry in data.get("conversations") or []:
                if not isinstance(entry, dict):
                    continue
                cuid = entry.get("uuid") or ""
                if not cuid:
                    continue
                manifest_uuids[pid].add(cuid)
                # First claim wins, matching the converter. A conversation in
                # two manifests is a stale manifest, not a shared conversation.
                conv_to_project.setdefault(cuid, pid)
        elif c2m._looks_like_project_metadata(data):
            pid = data.get("uuid") or ""
            if not pid:
                continue
            metadata_files[pid].append(jp)
            if data.get("name"):
                project_name[pid] = data["name"]

    return conv_to_project, project_name, metadata_files, manifest_uuids


def claude_folder_name(pid: str, name: str) -> str:
    """The same folder name the converter would produce, so the two agree."""
    return f"project_{c2m.short_uuid(pid)}__{c2m.slugify(name or 'untitled')}"


def split_claude(export_dir: Path, out_dir: Path, dry_run: bool,
                 only: str | None) -> int:
    conv_to_project, project_name, metadata_files, manifest_uuids = \
        claude_grouping(export_dir)

    conversations = read_json(export_dir / "conversations.json")
    if not isinstance(conversations, list):
        print("ERROR: conversations.json is missing or is not a list.",
              file=sys.stderr)
        return 2

    present = {c.get("uuid") for c in conversations
               if isinstance(c, dict) and c.get("uuid")}

    buckets: dict[str, list] = defaultdict(list)
    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        pid = conv_to_project.get(conv.get("uuid") or "")
        buckets[pid or UNGROUPED_DIR].append(conv)

    users = read_json(export_dir / "users.json")
    memories = read_json(export_dir / "memories.json")

    print(f"{len(conversations):,} conversation(s) in the export.")
    print(f"{len(project_name):,} project(s) named by manifests or metadata.")
    print()

    findings = 0
    written = 0
    for key, convs in sorted(buckets.items(),
                             key=lambda kv: (kv[0] == UNGROUPED_DIR, kv[0])):
        ungrouped = key == UNGROUPED_DIR
        if only and not ungrouped and key != only:
            continue
        if only and ungrouped:
            continue

        folder = (UNGROUPED_DIR if ungrouped
                  else claude_folder_name(key, project_name.get(key, "")))
        dest = out_dir / folder

        if not dry_run:
            # Replace rather than merge: a split is a projection of the
            # export, so a conversation removed upstream must not survive here.
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)

        write_json(dest / "conversations.json", convs, dry_run)
        if users is not None:
            write_json(dest / "users.json", users, dry_run)

        # `projects/` always exists, even empty. `is_claude_export` requires
        # the folder to be there, so an _ungrouped split without one is not
        # recognised as an export at all -- its conversations.json falls
        # through the converter dispatch and ends up as a sidecar, losing
        # every ungrouped conversation silently. Found in testing.
        if not dry_run:
            (dest / "projects").mkdir(parents=True, exist_ok=True)

        # Project metadata and the manifest travel with their project, so each
        # split is a complete export: the pipeline re-reads the manifest and
        # recreates the same project folder, keeping the name consistent all
        # the way down.
        if not ungrouped:
            for src in metadata_files.get(key, []):
                if not dry_run:
                    shutil.copy2(src, dest / "projects" / src.name)

        # Memory is split by scope, not copied wholesale. A project's own
        # memory belongs with it; the account-level conversations memory
        # belongs to no project, so it goes to _ungrouped rather than being
        # duplicated into every corpus.
        mem_out = claude_split_memories(memories, None if ungrouped else key)
        if mem_out:
            write_json(dest / "memories.json", mem_out, dry_run)

        claimed = manifest_uuids.get(key, set())
        missing = sorted(claimed - present) if claimed else []
        note = ""
        if missing:
            findings += 1
            note = f"  [!] {len(missing)} claimed by the manifest, not in the export"
        if not convs:
            findings += 1
            note += "  [!] empty"

        print(f"  {folder}/  {len(convs):,} conversation(s){note}")
        written += 1

    print()
    print(f"{written} split(s) {'previewed' if dry_run else 'written'} "
          f"to {out_dir}")
    if dry_run:
        print("(dry run -- nothing was written)")
    return 1 if findings else 0


def claude_split_memories(memories, pid: str | None):
    """memories.json holding only what belongs to this split.

    `pid` None means the ungrouped split, which takes the account-level
    conversations memory and no project memories.
    """
    if not isinstance(memories, list):
        return None
    out = []
    for entry in memories:
        if not isinstance(entry, dict):
            continue
        slim: dict = {}
        if pid is None:
            if entry.get("conversations_memory"):
                slim["conversations_memory"] = entry["conversations_memory"]
        else:
            proj = entry.get("project_memories")
            if isinstance(proj, dict) and pid in proj:
                slim["project_memories"] = {pid: proj[pid]}
        if slim:
            out.append(slim)
    return out or None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Split an AI data export into per-project exports, "
                    "before any conversion.")
    ap.add_argument("export_dir", help="Root of the unzipped export")
    ap.add_argument("out_dir", help="Where the per-project exports are written")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be written, change nothing")
    ap.add_argument("--only", default=None, metavar="PROJECT_UUID",
                    help="Split out a single project and nothing else")
    args = ap.parse_args()

    export_dir = Path(args.export_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    if not export_dir.is_dir():
        print(f"ERROR: not a directory: {export_dir}", file=sys.stderr)
        return 2
    if out_dir.resolve() == export_dir.resolve():
        print("ERROR: out_dir must differ from export_dir.", file=sys.stderr)
        return 2

    if c2m.is_claude_export(export_dir):
        print(f"Claude export: {export_dir}")
        return split_claude(export_dir, out_dir, args.dry_run, args.only)

    if (export_dir / "conversations.json").is_file():
        print("ERROR: this looks like a ChatGPT export, which has no writer "
              "yet.\n"
              "       Its media routing depends on how the export references "
              "assets,\n"
              "       which has changed across versions. Run "
              "inspect_chatgpt_assets.py\n"
              "       against it first.", file=sys.stderr)
        return 2

    print(f"ERROR: {export_dir} does not look like an export this script "
          f"can split.\n"
          f"       Expected a Claude export (conversations.json, users.json, "
          f"projects/).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
