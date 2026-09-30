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

  Claude   -- implemented here. No media: the export lists attached files
              by name and does not include their bytes.
  ChatGPT  -- implemented here, including media. Its grouping key is
              `conversation_template_id` on each conversation rather than a
              manifest, and it has real asset files that must follow their
              conversation into the right split. Which files those are is
              resolved through `chatgpt_assets`, whose pointer handling was
              written against a measured export rather than guessed.
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

import chatgpt_assets  # noqa: E402
import chatgpt_to_markdown as g2m  # noqa: E402
import claude_to_markdown as c2m  # noqa: E402

# Export-level files that belong in every split: account settings and the
# like, small and identical everywhere, the same reasoning as users.json on
# the Claude side.
CHATGPT_AUX = {
    "user.json", "user_settings.json", "export_manifest.json",
    "shared_conversations.json", "message_feedback.json",
    "model_comparisons.json", "chat.html",
}

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
# ChatGPT
# ---------------------------------------------------------------------------

def chatgpt_conversation_ids(conv: dict) -> list[str]:
    """Every asset id this conversation references, at any depth.

    Both kinds: pointer URLs in message parts, and the bare ids of uploaded
    attachments. The second set is mostly not on disk, but the ones that are
    must travel with the conversation rather than being left in the export.
    """
    mapping = conv.get("mapping") or {}
    ids = chatgpt_assets.pointer_ids(mapping)
    seen = set(ids)
    return ids + [i for i in chatgpt_assets.attachment_ids(mapping)
                  if not (i in seen or seen.add(i))]


def split_chatgpt(export_dir: Path, out_dir: Path, dry_run: bool,
                  only: str | None) -> int:
    conv_path = export_dir / "conversations.json"
    conversations = read_json(conv_path)
    if not isinstance(conversations, list):
        print("ERROR: conversations.json is missing or is not a list.",
              file=sys.stderr)
        return 2

    index = chatgpt_assets.AssetIndex(export_dir)
    print(f"{len(conversations):,} conversation(s) in the export.")
    print(f"asset index: {len(index.by_id):,} id(s) from "
          f"{index.files_scanned:,} file(s).")
    print()

    buckets: dict[str, list] = defaultdict(list)
    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        # subdir_for_template rather than pick_subdir: the latter reuses
        # folders already on disk, which is right when writing into an
        # existing digested tree and wrong here, where the output is rebuilt.
        tid = conv.get("conversation_template_id") or ""
        key = g2m.subdir_for_template(tid) if tid else UNGROUPED_DIR
        buckets[key].append(conv)

    aux = [f for f in sorted(export_dir.iterdir())
           if f.is_file() and f.name.lower() in CHATGPT_AUX]

    findings = 0
    written = 0
    for key, convs in sorted(buckets.items(),
                             key=lambda kv: (kv[0] == UNGROUPED_DIR, kv[0])):
        if only and key != only:
            continue
        dest = out_dir / key
        if not dry_run:
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)

        write_json(dest / "conversations.json", convs, dry_run)
        for f in aux:
            if not dry_run:
                shutil.copy2(f, dest / f.name)

        # Assets follow their conversation. Each split therefore holds only
        # the files its own conversations reference -- the same boundary the
        # conversations themselves get, applied to the media.
        wanted: dict[str, Path] = {}
        missing = 0
        for conv in convs:
            for aid in chatgpt_conversation_ids(conv):
                src = index.resolve(aid)
                if src is None:
                    missing += 1
                else:
                    wanted[src.name] = src
        if not dry_run:
            for name, src in wanted.items():
                try:
                    shutil.copy2(src, dest / name)
                except OSError as e:
                    print(f"  [warn] could not copy {name}: {e}",
                          file=sys.stderr)

        note = ""
        if missing:
            # Not a fault: ChatGPT exports the reference to an uploaded file,
            # not the file. The converter names them in the output.
            note = f", {missing} reference(s) with no file in the export"
        if not convs:
            findings += 1
            note += "  [!] empty"
        print(f"  {key}/  {len(convs):,} conversation(s), "
              f"{len(wanted):,} asset file(s){note}")
        written += 1

    print()
    print(f"{written} split(s) {'previewed' if dry_run else 'written'} "
          f"to {out_dir}")
    if dry_run:
        print("(dry run -- nothing was written)")
    return 1 if findings else 0


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
    ap.add_argument("--only", default=None, metavar="PROJECT",
                    help="Split out one project and nothing else. A project "
                         "uuid for Claude; the folder name "
                         "(project_g-p-...) for ChatGPT.")
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
        print(f"ChatGPT export: {export_dir}")
        return split_chatgpt(export_dir, out_dir, args.dry_run, args.only)

    print(f"ERROR: {export_dir} does not look like an export this script "
          f"can split.\n"
          f"       Expected a Claude export (conversations.json, users.json, "
          f"projects/)\n"
          f"       or a ChatGPT export (conversations.json).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
