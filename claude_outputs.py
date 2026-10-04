#!/usr/bin/env python3
"""
claude_outputs.py

Recover the files Claude wrote in a conversation, from a Claude data export.

WHY THIS EXISTS

A Claude export does not carry output files. It carries the tool calls that
made them: `create_file` with the file's full text, `str_replace` with each
later edit, `bash` commands that copied files about, and `present_files`
naming what was shown in the side panel. Replaying those calls in order
rebuilds each text file as it stood when the conversation ended -- the copy
you may have forgotten to download, or forgotten which chat holds.

WHAT IS RECOVERED, AND WHAT IS NOT

  - Every file written with `create_file`, with its edits applied. A file is
    recovered whether or not it was presented: the text is in the export
    either way, and a working copy in /home/claude is still Claude's output.
  - Files copied or moved with a plain `cp` / `mv`, followed to their new
    path so that what was presented is recognised as the same file. A copy
    the replay cannot follow (a loop, a script) costs nothing but the label:
    the text is still recovered under the name it was written with.
  - Not recovered: binary outputs (a .zip, a .docx built by a script). The
    export holds only the command that built them. They are listed by name
    as unrecoverable, so the gap is visible rather than silent.

An edit whose old text is not found exactly once is not applied, and the file
is marked as having incomplete edits. Nothing is guessed. A tool call whose
result was an error is skipped, because it changed nothing.

OUTPUT

Recovered files are written byte-identical into `<conversation-stem>_outputs/`
beside the conversation's Markdown, with `_recovered-outputs.json` recording
where each came from. That manifest is what marks the folder: the other
passes (metadata, sidecars, index, stale check, self-check) leave a folder
holding it alone, so a recovered file is never stamped or rewritten -- the
same catalogue-not-stamp rule 4-Canon follows. Search reaches the text
through the conversation, which carries it and links to the files.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import shlex
import shutil
from urllib.parse import quote
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "_recovered-outputs.json"
OUTPUTS_DIR_SUFFIX = "_outputs"

# Tool names. The ones seen in a real export; extend here when another
# appears. `artifacts` (the older side-panel tool) is counted, not replayed:
# no example of its input has been seen yet, and its schema is not guessed.
CREATE_TOOLS = {"create_file"}
EDIT_TOOLS = {"str_replace"}
BASH_TOOLS = {"bash_tool"}
PRESENT_TOOLS = {"present_files"}
UNHANDLED_FILE_TOOLS = {"artifacts"}

SHELL_SEPARATORS = {";", "&&", "||", "|", "&", "\n"}

WINDOWS_BAD = set('<>:"|?*\\')

# Where Claude works and where it puts deliverables. A file is written under
# its path relative to the first of these that contains it, so a working tree
# such as loom-writing-suite/architect/SKILL.md keeps its folders instead of
# collapsing into SKILL.md, SKILL__2.md, ...
WORK_ROOTS = ("/mnt/user-data/outputs", "/home/claude", "/mnt/user-data",
              "/tmp")


@dataclass
class TrackedFile:
    path: str                       # current path, after any cp / mv
    text: str
    written_as: str                 # path given to create_file
    edits_applied: int = 0
    edits_failed: int = 0
    inactive_branch: bool = False


@dataclass
class Recovery:
    files: dict[str, TrackedFile] = field(default_factory=dict)
    presented: list[str] = field(default_factory=list)
    archives: dict[str, list[str]] = field(default_factory=dict)  # zip -> members
    unhandled_tool_calls: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def failed_tool_ids(messages: list[dict]) -> set[str]:
    """Ids of tool calls whose result was an error. They changed nothing."""
    failed = set()
    for m in messages:
        for b in m.get("content") or []:
            if (isinstance(b, dict) and b.get("type") == "tool_result"
                    and b.get("is_error") and b.get("tool_use_id")):
                failed.add(b["tool_use_id"])
    return failed


def shell_commands(command: str) -> list[list[str]]:
    """Split a shell string into simple commands, each a list of words.

    Only good enough to find plain `cp`, `mv` and `cd`. Anything it cannot
    tokenise is returned as nothing, never as a wrong guess.
    """
    # A newline separates commands just as `;` does, so it is punctuation
    # here, not whitespace -- otherwise two `cp` lines run together into one
    # command. A backslash-newline is a continuation and is joined first.
    command = command.replace("\\\n", " ")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    out, cur = [], []
    for t in tokens:
        if t in SHELL_SEPARATORS or set(t) <= set(";&|\n"):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def resolve(path: str, cwd: str | None) -> str:
    if posixpath.isabs(path) or cwd is None:
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(cwd, path))


def apply_copy(rec: Recovery, words: list[str], cwd: str | None,
               branch_flag: bool) -> None:
    """Follow one `cp` / `mv` between files the replay knows about."""
    move = words[0] == "mv"
    operands = [w for w in words[1:] if not w.startswith("-")]
    if len(operands) < 2:
        return
    *sources, dest = operands
    dest_is_dir = (dest.endswith("/") or len(sources) > 1
                   or any(c in s for s in sources for c in "*?"))
    dest = resolve(dest, cwd)

    matched: list[str] = []
    for s in sources:
        s = resolve(s, cwd)
        if any(c in s for c in "*?"):
            matched += [p for p in rec.files if fnmatch.fnmatchcase(p, s)]
        elif s in rec.files:
            matched.append(s)
        elif s in rec.archives:
            target = (posixpath.join(dest, posixpath.basename(s))
                      if dest_is_dir or posixpath.splitext(dest)[1] == ""
                      else dest)
            rec.archives[target] = rec.archives[s]
            continue
        elif s.rstrip("/") and any(p.startswith(s.rstrip("/") + "/")
                                   for p in rec.files):
            # A directory copy: carry every known file beneath it.
            base = s.rstrip("/")
            for p in [p for p in rec.files if p.startswith(base + "/")]:
                target = posixpath.join(
                    dest, posixpath.basename(base), p[len(base) + 1:])
                copy_one(rec, p, target, move, branch_flag)
            continue
    for src in matched:
        # A destination with no extension, copied from a file with one, is
        # a directory: `cp report.md /mnt/user-data/outputs`.
        if (dest_is_dir or (posixpath.splitext(dest)[1] == ""
                            and posixpath.splitext(src)[1] != "")):
            target = posixpath.join(dest, posixpath.basename(src))
        else:
            target = dest
        copy_one(rec, src, target, move, branch_flag)


def note_archive(rec: Recovery, words: list[str], cwd: str | None) -> None:
    """Remember what a `zip` was built from. The archive itself is binary and
    cannot be recovered, but its members usually can, and saying so turns
    "lost" into "lost as a zip, here are its files"."""
    operands = [w for w in words[1:] if not w.startswith("-")]
    if len(operands) < 2:
        return
    archive = resolve(operands[0], cwd)
    if not archive.endswith(".zip"):
        archive += ".zip"
    members = []
    for o in operands[1:]:
        o = resolve(o, cwd).rstrip("/")
        members += [p for p in rec.files if p == o or p.startswith(o + "/")]
    rec.archives[archive] = sorted(set(members))


def copy_one(rec: Recovery, src: str, target: str, move: bool,
             branch_flag: bool) -> None:
    f = rec.files[src]
    rec.files[target] = TrackedFile(
        path=target, text=f.text, written_as=f.written_as,
        edits_applied=f.edits_applied, edits_failed=f.edits_failed,
        inactive_branch=f.inactive_branch or branch_flag)
    if move and target != src:
        del rec.files[src]


def replay(rec: Recovery, messages: list[dict], failed: set[str],
           inactive: bool = False) -> None:
    """Apply one chain of messages' file operations, in order."""
    for m in messages:
        for b in m.get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if b.get("id") in failed:
                continue
            name = b.get("name") or ""
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue

            if name in CREATE_TOOLS:
                path = inp.get("path")
                text = inp.get("file_text")
                if isinstance(path, str) and isinstance(text, str):
                    path = posixpath.normpath(path)
                    if inactive and path in rec.files:
                        continue          # the active branch's version stands
                    rec.files[path] = TrackedFile(
                        path=path, text=text, written_as=path,
                        inactive_branch=inactive)

            elif name in EDIT_TOOLS:
                path = inp.get("path")
                old, new = inp.get("old_str"), inp.get("new_str", "")
                if not isinstance(path, str) or not isinstance(old, str):
                    continue
                path = posixpath.normpath(path)
                f = rec.files.get(path)
                if f is None:
                    if not inactive:
                        rec.notes.append(f"edit to a file not written in this "
                                         f"conversation: {path}")
                    continue
                if inactive and not f.inactive_branch:
                    continue
                if f.text.count(old) == 1:
                    f.text = f.text.replace(old, new if isinstance(new, str)
                                            else "", 1)
                    f.edits_applied += 1
                else:
                    f.edits_failed += 1

            elif name in BASH_TOOLS:
                command = inp.get("command")
                if not isinstance(command, str):
                    continue
                cwd = None
                for words in shell_commands(command):
                    if words[0] == "cd" and len(words) == 2:
                        cwd = resolve(words[1], cwd)
                    elif words[0] in ("cp", "mv"):
                        apply_copy(rec, words, cwd, inactive)
                    elif words[0] == "zip":
                        note_archive(rec, words, cwd)

            elif name in PRESENT_TOOLS and not inactive:
                for p in inp.get("filepaths") or []:
                    if isinstance(p, str):
                        p = posixpath.normpath(p)
                        if p not in rec.presented:
                            rec.presented.append(p)

            elif name in UNHANDLED_FILE_TOOLS:
                rec.unhandled_tool_calls += 1


def recover(conv: dict, active: list[dict],
            inactive: dict[str, list[list[dict]]]) -> Recovery:
    """Replay a conversation's file operations: the active branch first, then
    any file that exists only on an abandoned branch."""
    rec = Recovery()
    messages = conv.get("chat_messages") or []
    failed = failed_tool_ids(messages)
    replay(rec, active, failed)
    for branches in inactive.values():
        for chain in branches:
            replay(rec, chain, failed, inactive=True)
    return rec


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def is_recovered_outputs_dir(path: Path) -> bool:
    return (path / MANIFEST_NAME).is_file()


def plan(rec: Recovery) -> tuple[list[tuple[str, TrackedFile, bool]], list[str]]:
    """Which files to write, under which names, and what cannot be recovered.

    A presented file is written under the name it was presented with. Every
    other file is written too, unless its text is identical to a presented
    one -- that is the working copy the presented file was copied from, and
    writing it twice would only be clutter.
    """
    chosen: list[tuple[str, TrackedFile, bool]] = []
    taken: set[str] = set()
    presented_texts = set()

    def name_for(path: str, keep_folders: bool) -> str:
        base = posixpath.basename(path) or "untitled"
        if keep_folders:
            for root in WORK_ROOTS:
                if path.startswith(root + "/"):
                    base = path[len(root) + 1:]
                    break
        # Windows refuses these characters in a name; the corpus lives there.
        base = "/".join(
            "".join("_" if c in WINDOWS_BAD or ord(c) < 32 else c
                    for c in part).rstrip(" .") or "_"
            for part in base.split("/"))
        stem, ext = posixpath.splitext(base)
        name, n = base, 2
        while name.lower() in taken:
            name = f"{stem}__{n}{ext}"
            n += 1
        taken.add(name.lower())
        return name

    unrecoverable = []
    for p in rec.presented:
        f = rec.files.get(p)
        if f is None:
            unrecoverable.append(p)
            continue
        chosen.append((name_for(p, False), f, True))
        presented_texts.add(f.text)
    for p, f in sorted(rec.files.items()):
        if p in rec.presented or f.text in presented_texts:
            continue
        chosen.append((name_for(p, True), f, False))
    return chosen, unrecoverable


def unrecoverable_entry(rec: Recovery, path: str, chosen) -> dict:
    members = rec.archives.get(path)
    if members:
        by_path = {f.path: name for name, f, _ in chosen}
        names = [by_path[m] for m in members if m in by_path]
        if names:
            return {"path": path,
                    "reason": f"a zip archive; its {len(names)} file(s) are "
                              f"recovered individually",
                    "contents_recovered_as": names}
    return {"path": path, "reason": "no text in the export; likely binary"}


def write_outputs(rec: Recovery, out_dir: Path, conv: dict) -> dict:
    """Write the recovered files and their manifest. Returns the manifest.

    The folder is rebuilt on every run, since a re-digest must not leave a
    file behind that the export no longer produces. It is only ever removed
    when it carries the manifest, i.e. when this pass made it.
    """
    chosen, unrecoverable = plan(rec)
    if out_dir.exists() and is_recovered_outputs_dir(out_dir):
        shutil.rmtree(out_dir)
    manifest = {
        "conversation_id": conv.get("uuid") or "",
        "conversation_title": conv.get("name") or "",
        "source": "Claude export (recovered from tool calls)",
        "files": [],
        "unrecoverable": [unrecoverable_entry(rec, p, chosen)
                          for p in unrecoverable],
        "notes": rec.notes,
    }
    if rec.unhandled_tool_calls:
        manifest["notes"].append(
            f"{rec.unhandled_tool_calls} call(s) to the `artifacts` tool were "
            f"not replayed; its input format has not been verified yet")
    if not chosen and not unrecoverable and not rec.unhandled_tool_calls:
        return manifest
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, f, presented in chosen:
        target = out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" so the text is written exactly as Claude wrote it.
        with target.open("w", encoding="utf-8", newline="") as fh:
            fh.write(f.text)
        entry = {
            "name": name,
            "path": f.path,
            "written_as": f.written_as,
            "presented": presented,
            "edits_applied": f.edits_applied,
        }
        if f.edits_failed:
            entry["edits_not_applied"] = f.edits_failed
        if f.inactive_branch:
            entry["inactive_branch"] = True
        manifest["files"].append(entry)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return manifest


def md_link(folder_name: str, name: str) -> str:
    """A Markdown link that survives names like `[SKILL] The Loom.md`."""
    text = name.replace("[", "\\[").replace("]", "\\]")
    return f"[{text}]({quote(folder_name + '/' + name)})"


def section(manifest: dict, folder_name: str) -> str:
    """The "Recovered outputs" section appended to the conversation."""
    files, lost = manifest["files"], manifest["unrecoverable"]
    if not files and not lost and not manifest["notes"]:
        return ""
    lines = ["## Recovered outputs", "",
             "_Rebuilt from this conversation's tool calls; see "
             f"`{folder_name}/{MANIFEST_NAME}`._", ""]
    for e in files:
        flags = ["presented" if e["presented"] else "working file"]
        if e["edits_applied"]:
            flags.append(f"{e['edits_applied']} edit(s) applied")
        if e.get("edits_not_applied"):
            flags.append(f"**{e['edits_not_applied']} edit(s) could not be "
                         f"applied**")
        if e.get("inactive_branch"):
            flags.append("from an abandoned branch")
        lines.append(f"- {md_link(folder_name, e['name'])} — {', '.join(flags)}")
    for e in lost:
        lines.append(f"- {posixpath.basename(e['path'])} — **not recoverable**"
                     f" ({e['reason']})")
        for name in e.get("contents_recovered_as", []):
            lines.append(f"  - {md_link(folder_name, name)}")
    for n in manifest["notes"]:
        lines.append(f"- _note: {n}_")
    return "\n".join(lines) + "\n"
