#!/usr/bin/env python3
"""
claude_to_markdown.py

Convert a Claude data export into per-conversation Markdown files, plus
sidecar files for project metadata and memory contents.

A Claude export is a folder containing at minimum:
  - conversations.json   (array of conversation objects)
  - users.json           (account metadata)
  - memories.json        (cross-conversation memory + project memories)
  - projects/            (folder of <project-uuid>.json files)

Output structure (mirroring the export under the OUTPUT_DIR):

  conversations/
    YYYY-MM-DD__title-slug.md      (one per conversation, flat)

  projects/
    <short-uuid>__name-slug.md     (one per project, metadata only)

  memories/
    conversations_memory.md        (cross-conversation memory)
    project_<short-uuid>__name-slug.md   (one per project memory)

  users.md                         (account info, rendered)


Important schema note: Claude's conversation export does NOT include a
project_uuid on each conversation. The connection between conversations
and projects exists in the live UI but is not preserved in the export.
So conversations are flat under conversations/, not grouped by project.
This is a limitation of Claude's export format, not of this converter.


Conversation rendering preserves all branches:
  - The active branch (parent->child chain reaching the most-recent leaf)
    is rendered first as the main body.
  - Each branch point with multiple children produces an "Inactive branches"
    section after the active body.
  - Thinking content blocks are rendered as collapsible details to keep the
    main flow readable.
  - Tool use / tool result pairs are rendered as readable named blocks.
  - Attachments are inlined when extracted_content is present in the export.
  - Files are listed by name (the export does not include file bytes).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_claude_export(folder: Path) -> bool:
    """Return True if `folder` looks like the root of a Claude data export."""
    if not folder.is_dir():
        return False
    has_conv = (folder / "conversations.json").is_file()
    has_users = (folder / "users.json").is_file()
    has_projects = (folder / "projects").is_dir()
    return has_conv and has_users and has_projects


# ---------------------------------------------------------------------------
# Slug & path utilities
# ---------------------------------------------------------------------------

_SLUG_BAD = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_SLUG_WS = re.compile(r"[\s_]+")


def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe lowercase slug, hyphen-separated."""
    if not text:
        return "untitled"
    text = _SLUG_BAD.sub("", text.strip())
    text = _SLUG_WS.sub("-", text)
    # Collapse any runs of hyphens (from " - " in source) to a single hyphen
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return (text[:max_len].rstrip("-") or "untitled")


def short_uuid(uuid: str) -> str:
    """First 8 hex chars of a UUID, for use in filenames."""
    if not uuid:
        return "noid"
    parts = uuid.replace("-", "")
    return parts[:8] if len(parts) >= 8 else parts


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (with optional Z suffix). Returns None on failure."""
    if not ts:
        return None
    try:
        # Replace trailing Z with +00:00 for fromisoformat
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def date_str(dt: datetime | None) -> str:
    """YYYY-MM-DD or 'unknown'."""
    if dt is None:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def iso_str(dt: datetime | None) -> str:
    """Full ISO-8601 UTC string or 'unknown'."""
    if dt is None:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------

def yaml_escape(val: Any) -> str:
    """Escape a value for embedding in a YAML scalar."""
    if val is None:
        return '""'
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    # Always quote strings to avoid YAML's many implicit-typing pitfalls.
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def to_yaml_frontmatter(fm: dict) -> str:
    """Serialize a flat dict into a YAML frontmatter block.

    All values are emitted as quoted strings (or bools/numbers when typed),
    matching the convention used by chatgpt_to_markdown.py so that downstream
    consumers (Obsidian, scripts that grep frontmatter) see a uniform format.
    """
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {yaml_escape(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Branch traversal
# ---------------------------------------------------------------------------

def build_message_index(messages: list[dict]) -> tuple[dict, dict]:
    """Return (by_uuid, children_by_parent) indexes."""
    by_uuid: dict[str, dict] = {}
    children: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        uid = m.get("uuid")
        if not uid:
            continue
        by_uuid[uid] = m
        children[m.get("parent_message_uuid") or ""].append(m)
    # Sort each sibling list by created_at so traversal is deterministic.
    for siblings in children.values():
        siblings.sort(key=lambda x: x.get("created_at") or "")
    return by_uuid, dict(children)


# Claude exports use a fixed sentinel for "no parent": the all-zeros UUID.
ROOT_PARENT = "00000000-0000-4000-8000-000000000000"


def find_active_branch(messages: list[dict]) -> tuple[list[dict], dict[str, list[list[dict]]]]:
    """Walk the message tree to identify the active branch and inactive branches.

    The active branch is the path from a root message (parent == ROOT_PARENT,
    parent missing/null, or parent points to a uuid not in by_uuid) to the
    message with the latest created_at, choosing the most-recently-updated
    child at each fork.

    For legacy conversations where parent_message_uuid is null on every
    message (Claude exports from before threading was tracked), this falls
    back to a flat chronological sequence with no inactive branches.

    Returns:
      active: list of messages in chronological order along the active path.
      inactive: dict mapping parent_uuid -> list of branches, where each branch
                is a list of messages descending the inactive branch in
                chronological order.
    """
    if not messages:
        return [], {}

    by_uuid, children = build_message_index(messages)

    def is_root(m: dict) -> bool:
        p = m.get("parent_message_uuid")
        # None, missing, the all-zeros sentinel, or a parent we don't have
        # all count as "root".
        if not p or p == ROOT_PARENT:
            return True
        return p not in by_uuid

    roots = [m for m in messages if is_root(m)]
    roots.sort(key=lambda x: x.get("created_at") or "")

    # Legacy / degenerate case: when every (or nearly every) message looks
    # like a root, threading information is absent. Render flat instead of
    # picking one arbitrary "root" and dropping everything else.
    if len(roots) >= max(2, len(messages) - 1) and len(messages) > 1:
        flat = sorted(messages, key=lambda x: x.get("created_at") or "")
        return flat, {}

    if not roots:
        return sorted(messages, key=lambda x: x.get("created_at") or ""), {}

    # Build active branch by walking from each root forward, preferring the
    # most-recently-updated child at every fork. We pick the root whose
    # subtree contains the message with the latest created_at overall.
    def latest_in_subtree(m: dict) -> str:
        latest = m.get("created_at") or ""
        for c in children.get(m.get("uuid", ""), []):
            sub = latest_in_subtree(c)
            if sub > latest:
                latest = sub
        return latest

    root = max(roots, key=latest_in_subtree)

    active: list[dict] = []
    inactive: dict[str, list[list[dict]]] = {}

    def walk(node: dict) -> None:
        active.append(node)
        kids = children.get(node.get("uuid", ""), [])
        if not kids:
            return
        if len(kids) == 1:
            walk(kids[0])
            return
        # Branch point: pick the child whose subtree contains the latest message.
        chosen = max(kids, key=latest_in_subtree)
        # Record the other children as inactive branches (full descendant chains).
        others = [c for c in kids if c.get("uuid") != chosen.get("uuid")]
        if others:
            inactive[node.get("uuid", "")] = [collect_chain(c, children) for c in others]
        walk(chosen)

    walk(root)
    return active, inactive


def collect_chain(start: dict, children: dict[str, list[dict]]) -> list[dict]:
    """Linearize a subtree by following the most-recently-updated child at
    each step. Used for inactive branches: we still want to render the full
    descendant chain, not just the first message.
    """
    chain = [start]
    node = start
    while True:
        kids = children.get(node.get("uuid", ""), [])
        if not kids:
            break
        node = max(kids, key=lambda x: x.get("created_at") or "")
        chain.append(node)
    return chain


# ---------------------------------------------------------------------------
# Content rendering
# ---------------------------------------------------------------------------

def render_text_block(block: dict) -> str:
    return (block.get("text") or "").rstrip()


def render_thinking_block(block: dict) -> str:
    """Render a thinking block as a collapsible details element.

    Markdown supports raw HTML <details>/<summary> in most renderers including
    Obsidian and GitHub, which keeps the main conversation flow readable while
    preserving the full content.
    """
    text = (block.get("thinking") or "").strip()
    summaries = block.get("summaries") or []
    summary_lines = [
        s.get("summary", "").strip()
        for s in summaries
        if isinstance(s, dict) and s.get("summary")
    ]
    parts = ["<details>", "<summary>Thinking</summary>", ""]
    if summary_lines:
        for s in summary_lines:
            parts.append(f"- *{s}*")
        parts.append("")
    if text:
        parts.append(text)
    parts.append("")
    parts.append("</details>")
    return "\n".join(parts)


def render_tool_use_block(block: dict) -> str:
    """Render a tool_use block as a labeled, fenced section."""
    name = block.get("name") or "tool"
    inp = block.get("input") or {}
    integration = block.get("integration_name")
    label_bits = [f"**Tool use: `{name}`**"]
    if integration:
        label_bits.append(f"_(via {integration})_")
    header = " ".join(label_bits)
    try:
        body = json.dumps(inp, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        body = str(inp)
    return f"{header}\n\n```json\n{body}\n```"


def render_tool_result_block(block: dict) -> str:
    """Render a tool_result block: surface text content, note errors."""
    name = block.get("name") or "tool"
    is_error = bool(block.get("is_error"))
    content = block.get("content") or []
    parts = []
    if is_error:
        parts.append(f"**Tool result: `{name}` (error)**")
    else:
        parts.append(f"**Tool result: `{name}`**")
    parts.append("")
    text_chunks = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            t = (c.get("text") or "").strip()
            if t:
                text_chunks.append(t)
    if text_chunks:
        parts.append("\n\n".join(text_chunks))
    else:
        # Fall back to the message field if present
        msg = block.get("message")
        if msg:
            parts.append(str(msg))
        else:
            parts.append("_(no text content)_")
    return "\n".join(parts)


def render_content_block(block: dict) -> str:
    """Dispatch a single content block to its renderer."""
    if not isinstance(block, dict):
        return str(block)
    btype = block.get("type")
    if btype == "text":
        return render_text_block(block)
    if btype == "thinking":
        return render_thinking_block(block)
    if btype == "tool_use":
        return render_tool_use_block(block)
    if btype == "tool_result":
        return render_tool_result_block(block)
    # Unknown block type: surface the raw JSON in a code block so nothing is lost.
    try:
        raw = json.dumps(block, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(block)
    return f"**Unknown content block (`{btype}`)**\n\n```json\n{raw}\n```"


def render_attachments(message: dict) -> str:
    """Render the attachments array (text-extracted content from file uploads)."""
    atts = message.get("attachments") or []
    if not atts:
        return ""
    sections = ["**Attachments**", ""]
    for i, a in enumerate(atts, 1):
        if not isinstance(a, dict):
            continue
        name = a.get("file_name") or f"attachment {i}"
        ftype = a.get("file_type") or "unknown"
        size = a.get("file_size")
        size_str = f", {size} bytes" if isinstance(size, int) else ""
        sections.append(f"_Attachment {i}: `{name}` ({ftype}{size_str})_")
        extracted = a.get("extracted_content")
        if extracted:
            # Use a fenced code block to make it clear this is captured content.
            sections.append("")
            sections.append("```")
            sections.append(extracted.rstrip())
            sections.append("```")
        sections.append("")
    return "\n".join(sections).rstrip()


def render_files(message: dict) -> str:
    """Render the files array (file uploads -- only filenames, bytes not in export)."""
    files = message.get("files") or []
    if not files:
        return ""
    sections = ["**Files** _(file bytes not included in Claude export)_", ""]
    for i, f in enumerate(files, 1):
        if not isinstance(f, dict):
            continue
        name = f.get("file_name") or f"file {i}"
        uid = f.get("file_uuid") or "no-uuid"
        sections.append(f"- `{name}` ({uid})")
    return "\n".join(sections)


def render_message(message: dict, role_override: str | None = None) -> str:
    """Render a single message (human or assistant) as a markdown section.

    A message becomes:

      ## Human  (or ## Assistant)
      _2026-03-19 20:09:09 UTC_

      <content blocks rendered in order>

      <attachments, if any>

      <files, if any>
    """
    sender = role_override or message.get("sender") or "unknown"
    role_label = {"human": "Human", "assistant": "Assistant"}.get(sender, sender.title())
    created = parse_iso(message.get("created_at"))
    ts = ""
    if created:
        ts = f"_{created.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_"

    parts = [f"## {role_label}"]
    if ts:
        parts.append(ts)
    parts.append("")

    content = message.get("content") or []
    if content:
        rendered_blocks = []
        for c in content:
            r = render_content_block(c).rstrip()
            if r:
                rendered_blocks.append(r)
        if rendered_blocks:
            parts.append("\n\n".join(rendered_blocks))
    else:
        # Fall back to plain text field if content array is empty
        text = (message.get("text") or "").strip()
        if text:
            parts.append(text)

    att = render_attachments(message)
    if att:
        parts.append("")
        parts.append(att)

    files = render_files(message)
    if files:
        parts.append("")
        parts.append(files)

    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Conversation rendering
# ---------------------------------------------------------------------------

def render_conversation(conv: dict) -> tuple[dict, str, str]:
    """Render one conversation. Returns (frontmatter_dict, body, date_string)."""
    title = conv.get("name") or "Untitled conversation"
    uuid = conv.get("uuid") or ""
    summary = conv.get("summary") or ""

    created = parse_iso(conv.get("created_at"))
    updated = parse_iso(conv.get("updated_at"))

    messages = conv.get("chat_messages") or []
    last_msg_time = None
    for m in messages:
        t = parse_iso(m.get("created_at"))
        if t and (last_msg_time is None or t > last_msg_time):
            last_msg_time = t

    active, inactive = find_active_branch(messages)

    # Audit pass: count thinking blocks, tool use, attachments, files
    has_thinking = False
    thinking_count = 0
    has_tool_use = False
    tool_use_count = 0
    has_attachments = False
    has_files = False
    for m in messages:
        for c in m.get("content") or []:
            if isinstance(c, dict):
                t = c.get("type")
                if t == "thinking":
                    has_thinking = True
                    thinking_count += 1
                elif t == "tool_use":
                    has_tool_use = True
                    tool_use_count += 1
        if m.get("attachments"):
            has_attachments = True
        if m.get("files"):
            has_files = True

    fm = {
        "title": title,
        "source": "Claude export",
        "conversation_id": uuid,
        "created": iso_str(created),
        "updated": iso_str(updated),
        "last_message_time": iso_str(last_msg_time),
        "active_message_count": len(active),
        "total_message_count": len(messages),
        "has_thinking_blocks": has_thinking,
        "thinking_block_count": thinking_count,
        "has_tool_use": has_tool_use,
        "tool_use_count": tool_use_count,
        "has_attachments": has_attachments,
        "has_files": has_files,
    }

    body_parts = [f"# {title}", ""]
    if summary:
        body_parts.append("> **Conversation summary**")
        # Indent each line of the summary as a blockquote so it renders cleanly.
        for line in summary.split("\n"):
            body_parts.append(f"> {line}" if line.strip() else ">")
        body_parts.append("")

    for m in active:
        body_parts.append(render_message(m))

    if inactive:
        body_parts.append("---")
        body_parts.append("")
        body_parts.append("## Inactive branches")
        body_parts.append("")
        body_parts.append(
            "_The following alternative responses were superseded by the active "
            "branch above. They are preserved here for completeness._"
        )
        body_parts.append("")
        # Order branch points by where they appear in the active chain
        active_uuids = [m.get("uuid", "") for m in active]
        ordered_parents = sorted(
            inactive.keys(),
            key=lambda u: active_uuids.index(u) if u in active_uuids else len(active_uuids)
        )
        for parent_uuid in ordered_parents:
            branches = inactive[parent_uuid]
            for bi, branch in enumerate(branches, 1):
                body_parts.append(
                    f"### Branch from message `{short_uuid(parent_uuid)}` (alternate {bi})"
                )
                body_parts.append("")
                for m in branch:
                    body_parts.append(render_message(m))

    body = "\n".join(body_parts).rstrip() + "\n"

    # Filename date prefers the conversation's created_at, falls back to first
    # message timestamp, falls back to "unknown".
    dstr = date_str(created) if created else date_str(last_msg_time)
    return fm, body, dstr


# ---------------------------------------------------------------------------
# Project metadata rendering
# ---------------------------------------------------------------------------

def render_project_metadata(proj: dict) -> tuple[dict, str]:
    """Render a single project metadata file as frontmatter + body."""
    title = proj.get("name") or "Untitled project"
    uuid = proj.get("uuid") or ""
    description = proj.get("description") or ""
    prompt = proj.get("prompt_template") or ""
    created = parse_iso(proj.get("created_at"))
    updated = parse_iso(proj.get("updated_at"))
    is_private = bool(proj.get("is_private"))
    is_starter = bool(proj.get("is_starter_project"))
    creator = proj.get("creator") or {}
    creator_name = creator.get("full_name") if isinstance(creator, dict) else ""
    docs = proj.get("docs") or []

    fm = {
        "title": title,
        "source": "Claude export (project metadata)",
        "project_id": uuid,
        "created": iso_str(created),
        "updated": iso_str(updated),
        "is_private": is_private,
        "is_starter_project": is_starter,
        "creator": creator_name or "",
        "doc_count": len(docs),
    }

    parts = [f"# {title}", ""]
    if description:
        parts.append("## Description")
        parts.append("")
        parts.append(description)
        parts.append("")
    if prompt:
        parts.append("## Prompt template")
        parts.append("")
        parts.append("```")
        parts.append(prompt)
        parts.append("```")
        parts.append("")
    if docs:
        parts.append("## Project documents")
        parts.append("")
        for d in docs:
            if isinstance(d, dict):
                name = d.get("file_name") or d.get("name") or "untitled"
                parts.append(f"- {name}")
            else:
                parts.append(f"- {d}")
        parts.append("")
    else:
        parts.append("_(no project documents in this export)_")
        parts.append("")

    body = "\n".join(parts).rstrip() + "\n"
    return fm, body


# ---------------------------------------------------------------------------
# Memories rendering
# ---------------------------------------------------------------------------

def render_conversations_memory(memory_text: str) -> tuple[dict, str]:
    """Render the cross-conversation memory as a single .md file."""
    fm = {
        "title": "Cross-conversation memory",
        "source": "Claude export (memory)",
    }
    body = "# Cross-conversation memory\n\n" + (memory_text or "").rstrip() + "\n"
    return fm, body


def render_project_memory(project_id: str, memory_text: str,
                          project_name: str | None) -> tuple[dict, str]:
    """Render a single project memory entry as a .md file."""
    title = f"Project memory: {project_name or project_id}"
    fm = {
        "title": title,
        "source": "Claude export (project memory)",
        "project_id": project_id,
    }
    body = f"# {title}\n\n" + (memory_text or "").rstrip() + "\n"
    return fm, body


# ---------------------------------------------------------------------------
# Users rendering
# ---------------------------------------------------------------------------

def render_users(users: list) -> tuple[dict, str]:
    """Render the users.json file as a readable .md."""
    fm = {
        "title": "Account info",
        "source": "Claude export (account)",
    }
    parts = ["# Account info", ""]
    if isinstance(users, list):
        for i, u in enumerate(users, 1):
            if not isinstance(u, dict):
                continue
            parts.append(f"## User {i}")
            parts.append("")
            for k in ("uuid", "full_name", "email_address", "verified_phone_number"):
                if k in u:
                    parts.append(f"- **{k}**: {u[k]}")
            parts.append("")
    parts.append("```json")
    try:
        parts.append(json.dumps(users, indent=2, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        parts.append(str(users))
    parts.append("```")
    body = "\n".join(parts).rstrip() + "\n"
    return fm, body


# ---------------------------------------------------------------------------
# Top-level export conversion
# ---------------------------------------------------------------------------

def write_md(path: Path, fm: dict, body: str) -> None:
    """Write frontmatter + body to a Markdown file (UTF-8, no BOM)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = to_yaml_frontmatter(fm) + body
    path.write_text(text, encoding="utf-8")


def _looks_like_manifest(data: object) -> bool:
    """Return True if a parsed JSON object looks like a project manifest.

    A manifest has top-level keys `project_uuid` (string) and `conversations`
    (list of dicts with at least `uuid`). We use this duck-typed check so we
    can scan a single projects/ directory and tell manifests apart from
    project metadata files.
    """
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("project_uuid"), str):
        return False
    convs = data.get("conversations")
    if not isinstance(convs, list):
        return False
    # Need at least one entry with a uuid field; empty list is also fine.
    if not convs:
        return True
    first = convs[0]
    return isinstance(first, dict) and "uuid" in first


def _looks_like_project_metadata(data: object) -> bool:
    """Return True if parsed JSON looks like a project metadata file.

    Project metadata has top-level `uuid` + `name`, distinct from manifests
    which have `project_uuid` + `conversations`.
    """
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("uuid"), str) and "name" in data


def find_existing_project_folder(parent: Path, project_id: str) -> Path | None:
    """Look for an existing folder under `parent` whose first .md file's
    frontmatter has matching project_id. Used to preserve user-renamed
    folders across re-runs (sticky-folder behavior, mirrors the ChatGPT side).

    Skips .nlm.md sidecars (which have frontmatter stripped by the
    NotebookLM sidecar pass) and looks for the canonical .md file.
    """
    if not project_id or not parent.is_dir():
        return None
    needle = f'project_id: "{project_id}"'
    for child in sorted(parent.iterdir()):
        if not child.is_dir():
            continue
        # Find the first .md that ISN'T an .nlm.md sidecar. The sidecars
        # have their frontmatter stripped, so they will never contain the
        # needle. Reading them and giving up early was a real bug.
        canonical_mds = sorted(
            md for md in child.glob("*.md")
            if not md.name.endswith(".nlm.md")
        )
        if not canonical_mds:
            continue
        md = canonical_mds[0]
        try:
            with md.open(encoding="utf-8") as f:
                head = f.read(2048)
        except OSError:
            continue
        if needle in head:
            return child
    return None


def convert_export(export_dir: Path, out_dir: Path) -> dict:
    """Convert a Claude export folder to Markdown under out_dir.

    Returns a stats dict including grouping diagnostics.
    """
    stats = {
        "conversations": 0,
        "conversations_grouped": 0,
        "conversations_ungrouped": 0,
        "projects": 0,
        "manifests_loaded": 0,
        "manifest_stale_entries": 0,
        "manifest_title_mismatches": 0,
        "manifest_uuid_conflicts": 0,
        "manifest_name_fallbacks": 0,
        "project_memories": 0,
        "conversations_memory": 0,
        "users": 0,
        "errors": 0,
    }

    # ---- Pass 1: scan projects/ for manifests AND project metadata -------
    # We build two structures:
    #   project_name_by_id : project_uuid -> human name (from metadata files)
    #   conversation_to_project : conversation_uuid -> project_uuid (from manifests)
    #   manifest_title_by_conv : conversation_uuid -> manifest's recorded title
    # The split between manifests and metadata is by file content, not name.
    projects_dir = export_dir / "projects"
    project_name_by_id: dict[str, str] = {}
    conversation_to_project: dict[str, str] = {}
    manifest_title_by_conv: dict[str, str] = {}
    project_metadata_files: list[tuple[Path, dict]] = []
    manifest_uuids_by_project: dict[str, set[str]] = {}
    # Names supplied by manifests, used as fallback when the corresponding
    # project metadata file is absent from the export. Claude's data export
    # does not always include metadata for every project (a known gap), so
    # the manifest's `project_name` field acts as a secondary source.
    manifest_project_name: dict[str, str] = {}

    if projects_dir.is_dir():
        for jp in sorted(projects_dir.glob("*.json")):
            try:
                with jp.open(encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  [warn] failed to read {jp.name}: {e}")
                stats["errors"] += 1
                continue

            if _looks_like_manifest(data):
                pid = data.get("project_uuid") or ""
                stats["manifests_loaded"] += 1
                # Record the manifest's project_name for use as a fallback
                # when the project metadata file is missing from the export.
                # Metadata files (when present) remain authoritative; this
                # only fills gaps.
                manifest_name = data.get("project_name") or ""
                if pid and manifest_name:
                    manifest_project_name[pid] = manifest_name
                seen_in_this_manifest = manifest_uuids_by_project.setdefault(pid, set())
                for entry in data.get("conversations") or []:
                    if not isinstance(entry, dict):
                        continue
                    cuid = entry.get("uuid")
                    title = entry.get("title") or ""
                    if not cuid:
                        continue
                    seen_in_this_manifest.add(cuid)
                    # Detect cross-manifest conflicts: a conversation can only
                    # belong to one project. If we see the same UUID claimed
                    # by two different projects, both manifests are wrong.
                    if cuid in conversation_to_project and conversation_to_project[cuid] != pid:
                        stats["manifest_uuid_conflicts"] += 1
                        print(f"  [warn] conversation {cuid[:8]} claimed by "
                              f"both projects {conversation_to_project[cuid][:8]} "
                              f"and {pid[:8]}; keeping first")
                        continue
                    conversation_to_project[cuid] = pid
                    manifest_title_by_conv[cuid] = title
            elif _looks_like_project_metadata(data):
                project_metadata_files.append((jp, data))
                pid = data.get("uuid") or ""
                project_name_by_id[pid] = data.get("name") or ""

    # ---- Pass 1b: fill in missing project names from manifest fallback ---
    # For any project_uuid that appears in a manifest but has no metadata
    # file (or has an empty metadata name), use the manifest's project_name.
    # This handles Claude exports that omit metadata for some projects.
    for pid, mname in manifest_project_name.items():
        if not project_name_by_id.get(pid):
            project_name_by_id[pid] = mname
            stats["manifest_name_fallbacks"] += 1

    # ---- Pass 2: render conversations, routing into project subfolders ---
    conv_path = export_dir / "conversations.json"
    conv_uuids_in_export: set[str] = set()
    if conv_path.is_file():
        try:
            with conv_path.open(encoding="utf-8") as f:
                conversations = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [warn] failed to read conversations.json: {e}")
            conversations = []
        if isinstance(conversations, list):
            conv_uuids_in_export = {c.get("uuid", "") for c in conversations
                                    if isinstance(c, dict) and c.get("uuid")}

            # Pre-discover existing project folders ONCE before the loop.
            # Doing this per-conversation would create a race: the first
            # conversation creates a default-named folder, and subsequent
            # conversations might find that folder before finding the
            # user-renamed folder, splitting writes between two folders.
            conversations_root = out_dir / "conversations"
            existing_project_folders: dict[str, Path] = {}
            project_ids_in_use = set(conversation_to_project.values())
            for pid in project_ids_in_use:
                existing = find_existing_project_folder(conversations_root, pid)
                if existing is not None:
                    existing_project_folders[pid] = existing

            # Track filenames per output directory so collisions get suffixed
            # only within the directory they collide in.
            seen_filenames_per_dir: dict[Path, set[str]] = {}
            for conv in conversations:
                try:
                    fm, body, dstr = render_conversation(conv)
                except Exception as e:  # noqa: BLE001
                    stats["errors"] += 1
                    print(f"  [warn] conversation failed: {e}")
                    continue

                cuid = fm.get("conversation_id", "")
                project_id = conversation_to_project.get(cuid, "")
                target_dir = conversations_root

                if project_id:
                    project_name = project_name_by_id.get(project_id) or "untitled"
                    # Use pre-discovered folder if present; otherwise compute
                    # the default name. We do not call find_existing_... again
                    # inside the loop -- see comment above.
                    if project_id in existing_project_folders:
                        target_dir = existing_project_folders[project_id]
                    else:
                        folder_name = (
                            f"project_{short_uuid(project_id)}__{slugify(project_name)}"
                        )
                        target_dir = conversations_root / folder_name
                        # Cache the folder we just decided on so the rest of
                        # the loop reuses it.
                        existing_project_folders[project_id] = target_dir
                    fm["project_id"] = project_id
                    fm["project_name"] = project_name
                    stats["conversations_grouped"] += 1
                    # Cross-check the manifest title against the actual title.
                    manifest_title = manifest_title_by_conv.get(cuid, "")
                    if manifest_title and manifest_title != fm.get("title"):
                        stats["manifest_title_mismatches"] += 1
                else:
                    stats["conversations_ungrouped"] += 1

                slug = slugify(fm["title"])
                base = f"{dstr}__{slug}"
                fname = base + ".md"
                seen = seen_filenames_per_dir.setdefault(target_dir, set())
                if fname in seen:
                    suffix = short_uuid(cuid)
                    fname = f"{base}__{suffix}.md"
                seen.add(fname)
                write_md(target_dir / fname, fm, body)
                stats["conversations"] += 1

    # ---- Pass 3: detect stale manifest entries ---------------------------
    # A manifest entry is "stale" if its UUID isn't in conversations.json.
    # Most likely cause: the conversation was deleted between manifest
    # generation and export. Worth flagging so the user can refresh.
    if conv_uuids_in_export:
        for cuid in conversation_to_project:
            if cuid not in conv_uuids_in_export:
                stats["manifest_stale_entries"] += 1

    # ---- Pass 4: render project metadata as sidecar .md files ------------
    for jp, proj in project_metadata_files:
        try:
            fm, body = render_project_metadata(proj)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            print(f"  [warn] project metadata failed ({jp.name}): {e}")
            continue
        uid = proj.get("uuid") or jp.stem
        slug = slugify(proj.get("name") or "untitled")
        # Annotate with conversation count from the matching manifest
        # if we have one. Useful at-a-glance signal.
        manifest_count = len(manifest_uuids_by_project.get(uid, set()))
        if manifest_count:
            fm["manifest_conversation_count"] = manifest_count
        fname = f"{short_uuid(uid)}__{slug}.md"
        write_md(out_dir / "projects" / fname, fm, body)
        stats["projects"] += 1

    # ---- Memories --------------------------------------------------------
    mem_path = export_dir / "memories.json"
    if mem_path.is_file():
        try:
            with mem_path.open(encoding="utf-8") as f:
                memories = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [warn] failed to read memories.json: {e}")
            memories = []
        # memories.json is an array; we expect one entry per account.
        if isinstance(memories, list):
            for entry in memories:
                if not isinstance(entry, dict):
                    continue
                conv_mem = entry.get("conversations_memory")
                if conv_mem:
                    try:
                        fm, body = render_conversations_memory(conv_mem)
                    except Exception as e:  # noqa: BLE001
                        stats["errors"] += 1
                        print(f"  [warn] conversations_memory failed: {e}")
                    else:
                        write_md(out_dir / "memories" / "conversations_memory.md",
                                 fm, body)
                        stats["conversations_memory"] += 1
                proj_mems = entry.get("project_memories") or {}
                if isinstance(proj_mems, dict):
                    for pid, ptext in proj_mems.items():
                        try:
                            fm, body = render_project_memory(
                                pid, ptext, project_name_by_id.get(pid)
                            )
                        except Exception as e:  # noqa: BLE001
                            stats["errors"] += 1
                            print(f"  [warn] project memory failed ({pid}): {e}")
                            continue
                        slug = slugify(project_name_by_id.get(pid) or "untitled")
                        fname = f"project_{short_uuid(pid)}__{slug}.md"
                        write_md(out_dir / "memories" / fname, fm, body)
                        stats["project_memories"] += 1

    # ---- Users -----------------------------------------------------------
    users_path = export_dir / "users.json"
    if users_path.is_file():
        try:
            with users_path.open(encoding="utf-8") as f:
                users = json.load(f)
            fm, body = render_users(users)
            write_md(out_dir / "users.md", fm, body)
            stats["users"] += 1
        except (json.JSONDecodeError, OSError, Exception) as e:  # noqa: BLE001
            stats["errors"] += 1
            print(f"  [warn] users.json failed: {e}")

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Convert a Claude data export folder to Markdown."
    )
    ap.add_argument("export", help="Path to the Claude export folder "
                                   "(contains conversations.json, projects/, etc.)")
    ap.add_argument("output", help="Path to the output folder")
    args = ap.parse_args()

    export = Path(args.export)
    out = Path(args.output)

    if not is_claude_export(export):
        print(f"ERROR: {export} does not look like a Claude export "
              "(needs conversations.json, users.json, and projects/).")
        return 1

    stats = convert_export(export, out)
    print()
    print("Done.")
    for k, v in stats.items():
        print(f"  {k:25s}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
