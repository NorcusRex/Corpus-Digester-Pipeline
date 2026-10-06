#!/usr/bin/env python3
"""
claude_manifests.py

Find, check and choose the project manifests for a Claude data export, and
stop the run before anything is written if they are not right.

WHY THIS EXISTS

Claude's export does not record which project a conversation belongs to. A
manifest does: one JSON file per project listing its conversations. Manifests
used to be downloaded by hand and dropped into the export's `projects/`
folder. They no longer need to be. The `update-project-manifest` skill writes
each manifest with `create_file`, and a create_file call keeps the file's full
text in `conversations.json`, so the export already carries every manifest
ever generated. This module reads them from there.

Where manifests come from, in order of preference:

  1. Written by `create_file` into /mnt/user-data/outputs in a conversation in
     the export (format 1.1, a dated and numbered filename). Each regeneration
     is another call, so every revision is kept.
  2. A file in the export's `projects/` folder, as before (format 1.0 or 1.1).
     Still read, so an export prepared the old way still works.

The newest manifest per project is used. Older ones are history.

THE GATE

Every check runs on the export alone, before anything is written. A failure
stops the run with nothing changed: a wrong grouping written into the corpus
is worse than no run. The checks:

  - Every project in the export has a manifest, even an empty one.
  - A manifest names a project that exists, under that project's own name.
  - The chosen manifest is well formed: count matches entries, no duplicate
    conversations, and for format 1.1 the filename agrees with the contents
    (datetime with generated_at, uuid, revision, format version), it was
    presented, it was not edited after it was written, and its revision is
    higher than the one before it.
  - No conversation is claimed by two projects.
  - No manifest is provably out of date: every conversation it lists is in
    the export, and none has a message newer than the manifest.
  - No conversation is left in no project.

What cannot be detected, and why the "every project" rule matters: a manifest
generated in the wrong project, under the right UUID and name, lists another
project's conversations. That other project then either has its own manifest
(which claims the same conversations, a conflict) or has none (a missing
manifest). Both stop the run.

The conversation a manifest was written in belongs to that manifest's project,
since the skill can only enumerate the project it runs in. It is placed there
even if the manifest does not list it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

OUTPUTS_DIR = "/mnt/user-data/outputs"

# Format versions this pipeline reads. 1.0 is the original (fixed filename,
# no revision); 1.1 adds `revision` and the dated, numbered filename.
ACCEPTED_FORMATS = {"1.0", "1.1"}

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# Format 1.1:  2026-10-05-0930__<project-uuid>_manifest_r3_v1.1.json
NAME_V11 = re.compile(
    rf"^(?P<dt>\d{{4}}-\d{{2}}-\d{{2}}-\d{{4}})__(?P<uuid>{UUID})"
    rf"_manifest_r(?P<rev>\d+)_v(?P<ver>\d+\.\d+)\.json$")
# Format 1.0:  <project-uuid>_manifest.json
NAME_V10 = re.compile(rf"^(?P<uuid>{UUID})_manifest\.json$")


class ManifestGateError(Exception):
    """The export's manifests failed the gate. Nothing has been written."""

    def __init__(self, problems: list[str]):
        super().__init__(f"{len(problems)} manifest problem(s)")
        self.problems = problems


@dataclass
class Manifest:
    data: dict
    source: str                    # "conversation" or "projects/ file"
    filename: str
    timestamp: datetime | None     # generated_at, else when it was written
    conversation_id: str = ""      # the chat that wrote it, if embedded
    conversation_title: str = ""
    text: str = ""                 # exactly as written, for the sidecar
    presented: bool = False
    edited_after: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def project_id(self) -> str:
        return self.data.get("project_uuid") or ""

    @property
    def label(self) -> str:
        where = (f"in chat \"{self.conversation_title}\""
                 if self.source == "conversation" else "in projects/")
        return f"{self.filename} ({where})"


@dataclass
class Resolution:
    conv_to_project: dict[str, str] = field(default_factory=dict)
    title_in_manifest: dict[str, str] = field(default_factory=dict)
    project_names: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, dict] = field(default_factory=dict)
    chosen: dict[str, Manifest] = field(default_factory=dict)
    history: dict[str, list[Manifest]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    name_fallbacks: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def looks_like_manifest(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("project_uuid"), str):
        return False
    convs = data.get("conversations")
    if not isinstance(convs, list):
        return False
    return not convs or (isinstance(convs[0], dict) and "uuid" in convs[0])


def looks_like_project_metadata(data: object) -> bool:
    return (isinstance(data, dict) and isinstance(data.get("uuid"), str)
            and "name" in data)


def parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def last_activity(conv: dict) -> datetime | None:
    times = [parse_time(m.get("created_at"))
             for m in conv.get("chat_messages") or []]
    times = [t for t in times if t]
    return max(times) if times else parse_time(conv.get("updated_at"))


def short(uuid: str) -> str:
    return uuid[:8] if uuid else "(none)"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def embedded_manifests(conversations: list) -> list[Manifest]:
    """Manifests written by create_file into outputs, in any conversation."""
    found: list[Manifest] = []
    for conv in conversations:
        if not isinstance(conv, dict):
            continue
        messages = sorted(conv.get("chat_messages") or [],
                          key=lambda m: m.get("created_at") or "")
        failed = {b.get("tool_use_id") for m in messages
                  for b in m.get("content") or []
                  if isinstance(b, dict) and b.get("type") == "tool_result"
                  and b.get("is_error")}
        written: dict[str, Manifest] = {}
        for m in messages:
            for b in m.get("content") or []:
                if (not isinstance(b, dict) or b.get("type") != "tool_use"
                        or b.get("id") in failed):
                    continue
                inp = b.get("input") or {}
                if not isinstance(inp, dict):
                    continue
                name = b.get("name")
                path = inp.get("path")
                if name == "create_file" and isinstance(path, str):
                    folder, _, fname = path.rpartition("/")
                    text = inp.get("file_text")
                    if folder != OUTPUTS_DIR or not isinstance(text, str):
                        continue
                    if not fname.endswith(".json"):
                        continue
                    try:
                        data = json.loads(text)
                    except ValueError:
                        if "manifest" in fname:
                            mf = Manifest({}, "conversation", fname,
                                          parse_time(m.get("created_at")),
                                          conv.get("uuid") or "",
                                          conv.get("name") or "", text)
                            mf.problems.append("is not valid JSON")
                            written[path] = mf
                        continue
                    if not looks_like_manifest(data):
                        continue
                    written[path] = Manifest(
                        data, "conversation", fname,
                        parse_time(data.get("generated_at"))
                        or parse_time(m.get("created_at")),
                        conv.get("uuid") or "", conv.get("name") or "", text)
                elif name == "str_replace" and path in written:
                    written[path].edited_after = True
                elif name == "present_files":
                    for p in inp.get("filepaths") or []:
                        if p in written:
                            written[p].presented = True
        found += written.values()
    return found


def folder_manifests(export_dir: Path) -> tuple[list[Manifest], dict[str, dict],
                                                list[str]]:
    """Manifests and project metadata from the export's projects/ folder."""
    manifests: list[Manifest] = []
    metadata: dict[str, dict] = {}
    problems: list[str] = []
    projects_dir = export_dir / "projects"
    if not projects_dir.is_dir():
        return manifests, metadata, problems
    for jp in sorted(projects_dir.glob("*.json")):
        try:
            text = jp.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, ValueError) as e:
            problems.append(f"projects/{jp.name} could not be read: {e}")
            continue
        if looks_like_manifest(data):
            manifests.append(Manifest(data, "projects/ file", jp.name,
                                      parse_time(data.get("generated_at")),
                                      text=text, presented=True))
        elif looks_like_project_metadata(data) and data.get("uuid"):
            metadata[data["uuid"]] = data
    return manifests, metadata, problems


# ---------------------------------------------------------------------------
# Checks on one manifest
# ---------------------------------------------------------------------------

def check_manifest(mf: Manifest) -> None:
    """Problems with a manifest on its own terms. Appends to mf.problems."""
    if mf.problems:                       # unreadable; nothing more to check
        return
    d = mf.data
    version = str(d.get("manifest_format_version") or "1.0")
    if version not in ACCEPTED_FORMATS:
        mf.problems.append(f"format version {version} is not one this "
                           f"pipeline reads ({', '.join(sorted(ACCEPTED_FORMATS))})")
        return
    convs = d.get("conversations") or []
    if d.get("conversation_count") is not None and \
            d.get("conversation_count") != len(convs):
        mf.problems.append(f"conversation_count says {d.get('conversation_count')}"
                           f" but {len(convs)} are listed")
    uuids = [c.get("uuid") for c in convs if isinstance(c, dict)]
    if len(set(uuids)) != len(uuids):
        mf.problems.append("lists the same conversation more than once")

    if mf.source != "conversation":
        return
    if version == "1.1":
        m = NAME_V11.match(mf.filename)
        if not m:
            mf.problems.append("filename does not follow "
                               "YYYY-MM-DD-HHMM__<uuid>_manifest_r<N>_v<format>.json")
        else:
            gen = parse_time(d.get("generated_at"))
            if gen is None:
                mf.problems.append("has no usable generated_at")
            elif gen.strftime("%Y-%m-%d-%H%M") != m["dt"]:
                mf.problems.append(f"filename time {m['dt']} does not match "
                                   f"generated_at {d.get('generated_at')}")
            if m["uuid"] != mf.project_id:
                mf.problems.append("filename UUID does not match project_uuid")
            if m["ver"] != version:
                mf.problems.append(f"filename says format v{m['ver']}, "
                                   f"contents say {version}")
            if str(d.get("revision")) != m["rev"]:
                mf.problems.append(f"filename says revision {m['rev']}, "
                                   f"contents say {d.get('revision')}")
        if not isinstance(d.get("revision"), int) or d.get("revision") < 1:
            mf.problems.append("has no revision number")
    elif not NAME_V10.match(mf.filename):
        mf.problems.append("filename does not match its format version")
    if not mf.presented:
        mf.problems.append("was written but never presented")
    if mf.edited_after:
        mf.problems.append("was edited after it was written; create_file "
                           "must be the final step")


# ---------------------------------------------------------------------------
# Resolution and the gate
# ---------------------------------------------------------------------------

def resolve(export_dir: Path, conversations: list | None = None) -> Resolution:
    """Choose a manifest per project and check the whole export.

    Never raises for a bad manifest: problems are collected in
    `Resolution.problems`, and `gate()` turns them into a stop.
    """
    res = Resolution()
    if conversations is None:
        try:
            conversations = json.loads(
                (export_dir / "conversations.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            res.problems.append(f"conversations.json could not be read: {e}")
            conversations = []
    if not isinstance(conversations, list):
        conversations = []
    convs = {c["uuid"]: c for c in conversations
             if isinstance(c, dict) and c.get("uuid")}

    from_folder, res.metadata, read_problems = folder_manifests(export_dir)
    res.problems += read_problems
    candidates = embedded_manifests(conversations) + from_folder
    for mf in candidates:
        check_manifest(mf)
        res.history.setdefault(mf.project_id, []).append(mf)

    # Newest per project. A manifest with no time at all (an old one dropped
    # into projects/) sorts oldest, so anything written in a chat wins.
    floor = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
    rejected: set[str] = set()     # projects whose newest manifest failed
    for pid, mfs in res.history.items():
        mfs.sort(key=lambda m: m.timestamp or floor)
        newest = mfs[-1]
        if newest.problems:
            res.problems += [f"manifest {newest.label}: {p}"
                             for p in newest.problems]
        for older in mfs[:-1]:
            if older.problems:
                res.notes.append(f"older manifest {older.label} ignored: "
                                 f"{'; '.join(older.problems)}")
        if newest.problems:
            rejected.add(pid)
        else:
            res.chosen[pid] = newest
        # Revisions must climb. Compared with the previous numbered one only:
        # history cannot be rewritten, so an old slip must not stop every
        # future run.
        rev = newest.data.get("revision")
        prior = [m.data.get("revision") for m in mfs[:-1]
                 if isinstance(m.data.get("revision"), int) and not m.problems]
        if isinstance(rev, int) and prior and rev <= prior[-1]:
            res.problems.append(
                f"manifest {newest.label}: revision {rev} is not higher than "
                f"the previous manifest's revision {prior[-1]}")

    # Names: the export's metadata is authoritative.
    for pid, meta in res.metadata.items():
        res.project_names[pid] = meta.get("name") or ""

    for pid, mf in res.chosen.items():
        name = (mf.data.get("project_name") or "").strip()
        if pid not in res.metadata:
            res.problems.append(
                f"manifest {mf.label} names project {pid}, which is not in "
                f"this export (a wrong UUID, or the export omitted the "
                f"project)")
            if name:
                res.project_names[pid] = name
                res.name_fallbacks += 1
        elif name != (res.metadata[pid].get("name") or "").strip():
            res.problems.append(
                f"manifest {mf.label} calls project {short(pid)} \"{name}\", "
                f"but the export calls it "
                f"\"{res.metadata[pid].get('name')}\"")

    for pid, meta in res.metadata.items():
        if pid not in res.chosen and pid not in rejected:
            res.problems.append(
                f"project \"{meta.get('name')}\" ({pid}) has no manifest. "
                f"Every project needs one, even if it is empty.")

    # Placement: manifest entries first, then each manifest's own chat.
    for pid, mf in res.chosen.items():
        when = mf.timestamp
        for entry in mf.data.get("conversations") or []:
            cuid = entry.get("uuid") if isinstance(entry, dict) else None
            if not cuid:
                continue
            other = res.conv_to_project.get(cuid)
            if other and other != pid:
                res.problems.append(
                    f"conversation \"{entry.get('title')}\" is claimed by "
                    f"both {res.project_names.get(other) or short(other)} and "
                    f"{res.project_names.get(pid) or short(pid)}")
                continue
            res.conv_to_project[cuid] = pid
            res.title_in_manifest[cuid] = entry.get("title") or ""
            if cuid not in convs:
                res.problems.append(
                    f"manifest {mf.label} lists \"{entry.get('title')}\", "
                    f"which is not in the export (deleted, or the manifest "
                    f"is out of date)")
                continue
            if cuid == mf.conversation_id:
                continue              # the manifest's own chat runs on after it
            act = last_activity(convs[cuid])
            if when and act and act > when:
                res.problems.append(
                    f"manifest {mf.label} is out of date: \"{entry.get('title')}\""
                    f" has activity at {act.isoformat(timespec='minutes')}, "
                    f"after the manifest was made")

    for pid, mfs in res.history.items():
        if pid not in res.chosen:
            continue
        for mf in mfs:
            cuid = mf.conversation_id
            if not cuid or cuid not in convs:
                continue
            other = res.conv_to_project.get(cuid)
            if other and other != pid:
                res.problems.append(
                    f"the chat \"{mf.conversation_title}\" wrote a manifest "
                    f"for {res.project_names.get(pid) or short(pid)} but is "
                    f"listed by {res.project_names.get(other) or short(other)}")
            else:
                res.conv_to_project[cuid] = pid

    unplaced = [c for u, c in convs.items() if u not in res.conv_to_project]
    for c in sorted(unplaced, key=lambda c: c.get("created_at") or ""):
        res.problems.append(
            f"conversation \"{c.get('name') or '(untitled)'}\" "
            f"({(c.get('created_at') or '')[:10]}, {short(c.get('uuid'))}) is "
            f"in no project")
    return res


def gate(res: Resolution, export_dir: Path, lenient: bool = False) -> None:
    """Stop the run when the manifests are not right.

    Raises ManifestGateError unless `lenient`, which reports and carries on:
    for backfilling exports made before manifests were written this way.
    """
    if not res.problems:
        return
    if lenient:
        print(f"  [manifests] {len(res.problems)} problem(s), continuing "
              f"because --lenient-manifests is set:")
        for p in res.problems:
            print(f"    - {p}")
        return
    raise ManifestGateError(res.problems)


def banner(export_dir: Path, problems: list[str]) -> str:
    rule = "!" * 72
    lines = [rule,
             "  STOPPED: the project manifests for this export are not right.",
             f"  Export: {export_dir}",
             "  Nothing has been written or changed.",
             rule, ""]
    lines += [f"  - {p}" for p in problems]
    lines += ["",
              "  Fix the manifests (regenerate in the project's \"Update "
              "manifest\" chat),",
              "  re-export, and run again. See docs/runbook.md.",
              rule]
    return "\n".join(lines)


def write_sidecars(res: Resolution, projects_out: Path, slug_for) -> int:
    """File every usable manifest revision beside its project, verbatim.

    `slug_for(pid)` gives the project's folder stem, so the manifests land in
    `<stem>_manifests/` next to `<stem>.md` and `<stem>_docs/`.
    """
    written = 0
    for pid, mfs in res.history.items():
        if pid not in res.chosen:
            continue
        good = [m for m in mfs if not m.problems and m.source == "conversation"]
        if not good:
            continue
        folder = projects_out / f"{slug_for(pid)}_manifests"
        folder.mkdir(parents=True, exist_ok=True)
        for mf in good:
            with (folder / mf.filename).open("w", encoding="utf-8",
                                             newline="") as fh:
                fh.write(mf.text)
            written += 1
    return written
