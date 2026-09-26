#!/usr/bin/env python3
"""
chatgpt_to_markdown.py

Convert a ChatGPT JSON export (conversations.json) into individual Markdown
files, one per conversation. Output is intended for upload to Google Drive
where it is searchable via the Claude Drive connector.

Design principles
-----------------
* Lossless. Every message in the export is preserved. The active conversation
  branch (root -> current_node) is rendered first, then any inactive branches
  (regenerations, abandoned forks) follow under a clearly labelled section so
  nothing is silently dropped.
* No summarisation. This is mechanical format conversion, not abstraction.
* Stable filenames. "<YYYY-MM-DD>__<slug>.md" so files sort chronologically
  and survive re-runs without churn.
* Zero dependencies. Standard library only.

Usage
-----
    python chatgpt_to_markdown.py path/to/conversations.json -o out_dir/
    python chatgpt_to_markdown.py conversations.json --limit 5   # smoke test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import chatgpt_assets  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROLE_HEADINGS = {
    "user":      "## User",
    "assistant": "## Assistant",
    "system":    "## System",
    "tool":      "## Tool",
}


def slugify(text: str, max_length: int = 60) -> str:
    """Filesystem-safe slug. Lower-cased, ASCII-ish, hyphen-separated."""
    if not text:
        return "untitled"
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_length] or "untitled"


def fmt_ts(ts) -> str:
    """ISO-8601 UTC string for a Unix timestamp; '' if missing/invalid."""
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def date_only(ts) -> str:
    if ts is None:
        return "0000-00-00"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "0000-00-00"


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------

def extract_text(message: dict, sink=None) -> str:
    """Return the message text, joining multi-part content with newlines.

    A part carrying `text` is used as-is; that covers `audio_transcription`,
    so spoken content has always come through. A part without text names an
    asset instead, and `sink` is what turns that name into a link. Without a
    sink the part is still named rather than silently dropped.
    """
    if not message:
        return ""
    content = message.get("content") or {}
    parts = content.get("parts") or []
    out: list[str] = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            t = p.get("text")
            if t:
                out.append(t)
            else:
                out.append(chatgpt_assets.render_part(p, sink))
        else:
            out.append(str(p))

    # Uploaded attachments hang off message.metadata, not content.parts, so
    # nothing used to see them at all -- not even a placeholder.
    attach = chatgpt_assets.render_attachments(message, sink)
    if attach:
        out.append(attach)

    return "\n".join(out).strip()


def role_label(message: dict) -> str:
    if not message:
        return "unknown"
    author = message.get("author") or {}
    role = author.get("role", "unknown")
    name = author.get("name")
    return f"{role}:{name}" if (role == "tool" and name) else role


def render_node(node: dict, include_meta: bool = True, sink=None) -> str:
    """Render a single message node as a Markdown block, or '' if empty/skip."""
    msg = node.get("message")
    if not msg:
        return ""
    role = role_label(msg)
    text = extract_text(msg, sink)

    # ChatGPT seeds conversations with empty system stubs; drop them silently.
    if not text and role.startswith("system"):
        return ""

    # Thinking-model reasoning step nodes: empty assistant entries that the
    # model emitted as it reasoned, but whose content OpenAI does not include
    # in exports. Detect them so the caller can collapse runs of them into a
    # single marker rather than rendering empty "## Assistant" headers.
    if not text and role.startswith("assistant"):
        return "__REASONING_STEP__"

    base_role = role.split(":", 1)[0]
    heading = ROLE_HEADINGS.get(base_role, f"## {base_role.capitalize()}")
    if ":" in role:
        heading = f"{heading} ({role.split(':', 1)[1]})"

    bits = [heading]
    if include_meta:
        ts = fmt_ts(msg.get("create_time"))
        if ts:
            bits.append(f"*{ts}*")
    if text:
        bits.append("")
        bits.append(text)
    return "\n".join(bits)


# ---------------------------------------------------------------------------
# Conversation tree traversal
# ---------------------------------------------------------------------------

def active_path(mapping: dict, current_node_id: str | None) -> list[str]:
    """List of node IDs from root to current_node, in order."""
    if not current_node_id or current_node_id not in mapping:
        return []
    path: list[str] = []
    nid: str | None = current_node_id
    seen: set[str] = set()
    while nid is not None and nid not in seen:
        seen.add(nid)
        path.append(nid)
        nid = mapping[nid].get("parent")
        if nid is not None and nid not in mapping:
            break
    return list(reversed(path))


def _collapse_reasoning_markers(blocks: list[str]) -> tuple[list[str], int]:
    """Replace runs of __REASONING_STEP__ markers with a single italicized
    line indicating how many were collapsed. Returns (collapsed_blocks, count)."""
    out: list[str] = []
    i = 0
    total_collapsed = 0
    n = len(blocks)
    while i < n:
        if blocks[i] == "__REASONING_STEP__":
            run = 0
            while i < n and blocks[i] == "__REASONING_STEP__":
                run += 1
                i += 1
            if run == 1:
                out.append("*[1 reasoning step]*")
            else:
                out.append(f"*[{run} reasoning steps]*")
            total_collapsed += run
        else:
            out.append(blocks[i])
            i += 1
    return out, total_collapsed


def _is_voice_conversation(mapping: dict) -> bool:
    """Heuristic: any message contains a voice-mode asset pointer stub."""
    voice_markers = (
        "[real_time_user_audio_video_asset_pointer content omitted]",
        "[audio_asset_pointer content omitted]",
        "[audio_transcription content omitted]",
    )
    for node in mapping.values():
        msg = node.get("message") if isinstance(node, dict) else None
        if not msg:
            continue
        text = extract_text(msg)
        if any(m in text for m in voice_markers):
            return True
    return False


def _latest_message_time(mapping: dict) -> str:
    """ISO timestamp of the latest create_time among messages with content."""
    latest: float | None = None
    for node in mapping.values():
        msg = node.get("message") if isinstance(node, dict) else None
        if not msg:
            continue
        ts = msg.get("create_time")
        if ts is None:
            continue
        try:
            tsf = float(ts)
        except (TypeError, ValueError):
            continue
        if latest is None or tsf > latest:
            latest = tsf
    return fmt_ts(latest) if latest is not None else ""


def render_conversation(conv: dict, sink=None) -> tuple[dict, str, str]:
    """Return (frontmatter_dict, body_str, date_string).

    `sink` is an optional `chatgpt_assets.AssetSink`. Given one, asset
    pointers resolve to links and the caller must call `sink.flush(md_path,
    body)` once the output path is known -- the media folder is named after
    the Markdown file, which is not decided until after rendering.
    """
    title = conv.get("title") or "Untitled conversation"
    mapping = conv.get("mapping") or {}
    current = conv.get("current_node")
    path = active_path(mapping, current)

    rendered: list[str] = []
    rendered_ids: set[str] = set()
    for nid in path:
        block = render_node(mapping[nid], sink=sink)
        if block:
            rendered.append(block)
            rendered_ids.add(nid)

    # Anything in the tree not on the active path: keep it but mark it.
    leftovers: list[str] = []
    for nid, node in mapping.items():
        if nid in rendered_ids:
            continue
        block = render_node(node, sink=sink)
        if block:
            leftovers.append(block)

    # Replace runs of empty assistant nodes (thinking-model reasoning steps)
    # with a single marker line so the reader sees the model paused to think
    # without being confronted with three or four empty headers.
    rendered, active_collapsed = _collapse_reasoning_markers(rendered)
    leftovers, leftover_collapsed = _collapse_reasoning_markers(leftovers)
    reasoning_step_count = active_collapsed + leftover_collapsed

    body_parts: list[str] = [f"# {title}", ""]
    body_parts.extend(rendered)
    if leftovers:
        body_parts += [
            "",
            "---",
            "",
            "## Inactive branches",
            "",
            "_The messages below are alternate branches preserved from the export "
            "(typically regenerations). They are not part of the active conversation._",
            "",
        ]
        body_parts.extend(leftovers)

    body = "\n\n".join(p for p in body_parts if p is not None)

    msg_count = sum(1 for nid in path if mapping[nid].get("message"))
    fm = {
        "title": title,
        "source": "ChatGPT export",
        "conversation_id": conv.get("conversation_id") or conv.get("id") or "",
        "created": fmt_ts(conv.get("create_time")),
        # `updated` reflects any change to the conversation record (rename,
        # archive, share-link generation, project move) and may be later
        # than the actual last message. `last_message_time` is the timestamp
        # of the actual most-recent message body and is what you want when
        # asking "when did this conversation last get new content?"
        "updated": fmt_ts(conv.get("update_time")),
        "last_message_time": _latest_message_time(mapping),
        "active_message_count": msg_count,
        "total_node_count": len(mapping),
        # Older conversations (mostly pre-mid-2024) have no model_slug in the
        # source JSON. Use a sentinel so the field is always present rather
        # than absent; downstream tools can rely on the schema.
        "model_slug": conv.get("default_model_slug") or "<unknown>",
        # Project / Custom GPT membership. Empty string when the conversation
        # is a regular chat with no template.
        "conversation_template_id": conv.get("conversation_template_id") or "",
        "gizmo_id": conv.get("gizmo_id") or "",
        # Useful filtering hints surfaced from the message tree.
        "has_reasoning_steps": reasoning_step_count > 0,
        "reasoning_step_count": reasoning_step_count,
        "is_voice": _is_voice_conversation(mapping),
    }
    return fm, body, date_only(conv.get("create_time"))


def subdir_for_template(template_id: str | None) -> str:
    """Map a conversation_template_id to a subdirectory name.

    ChatGPT exports identify Project membership and Custom GPT usage through
    the conversation_template_id field:

      - empty / None       -> regular conversation, no template (returns "")
      - starts with "g-p-" -> ChatGPT Project (returns "project_<id>")
      - other non-empty    -> Custom GPT or other template (returns "gpt_<id>")

    The export does NOT include human-readable project or GPT names, only
    these IDs. Folders can be renamed by hand after conversion, and the
    rename will survive re-runs (see pick_subdir).
    """
    if not template_id:
        return ""
    safe = re.sub(r"[^\w\-]", "_", template_id)
    if template_id.startswith("g-p-"):
        return f"project_{safe}"
    return f"gpt_{safe}"


def existing_folder_for_template(parent: Path, template_id: str) -> str:
    """Search subfolders of `parent` for one that already holds conversations
    with this template_id. Returns the folder name if found, else ''.

    The check peeks at the first non-sidecar .md file in each subfolder and
    looks for `conversation_template_id: "<id>"` in the frontmatter. This is
    what makes user-renamed folders sticky across re-runs.

    Skips .nlm.md sidecars, which have their frontmatter stripped by the
    NotebookLM sidecar pass and so never contain the needle.
    """
    if not template_id or not parent.is_dir():
        return ""
    needle = f'conversation_template_id: "{template_id}"'
    for child in sorted(parent.iterdir()):
        if not child.is_dir():
            continue
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
            return child.name
    return ""


def pick_subdir(parent: Path, template_id: str | None) -> str:
    """Return the subdirectory name to use for a conversation with this
    template_id. Reuses existing (possibly user-renamed) folders so that
    re-runs do not create duplicate default-named folders next to renamed
    ones; falls back to the default name when no existing folder matches.
    """
    if not template_id:
        return ""
    existing = existing_folder_for_template(parent, template_id)
    return existing or subdir_for_template(template_id)


# ---------------------------------------------------------------------------
# Aux JSON rendering (user.json, user_settings.json, etc.)
# ---------------------------------------------------------------------------

def render_aux_json(path: Path) -> tuple[dict, str]:
    """Render a ChatGPT export auxiliary JSON file as Markdown.

    Top-level dict keys become ## headings; nested structures render as
    bullet lists with bold keys; lists become numbered ## items. The
    original JSON is preserved verbatim in a code block at the end of the
    document so the file remains lossless.
    """
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Pretty title from the filename: "user_settings.json" -> "User settings"
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    title = stem[:1].upper() + stem[1:] if stem else path.name

    fm = {
        "source":      "ChatGPT export auxiliary file",
        "source_file": path.name,
    }

    body: list[str] = [
        f"# {title}",
        "",
        f"_Rendered from `{path.name}` in your ChatGPT export. The original "
        f"JSON is preserved at the end of this document._",
        "",
    ]

    if isinstance(data, dict):
        if data:
            body.extend(_render_aux_dict(data, depth=2))
        else:
            body.append("_(empty object)_")
    elif isinstance(data, list):
        body.append(f"_List of {len(data)} item(s)._")
        body.append("")
        for i, item in enumerate(data, 1):
            body.append(f"## Item {i}")
            body.append("")
            body.extend(_render_aux_value(item, indent=0))
            body.append("")
    else:
        body.append(str(data))

    # Original JSON for byte-fidelity preservation.
    body.extend([
        "",
        "## Original JSON",
        "",
        "```json",
        json.dumps(data, indent=2, ensure_ascii=False),
        "```",
    ])

    return fm, "\n".join(body)


def _render_aux_dict(d: dict, depth: int) -> list[str]:
    """Render a dict with each key as a heading at the given depth (capped
    at h6). Falls back to bullet rendering once heading depth exceeds 4."""
    if depth > 4:
        return _render_aux_value(d, indent=0)

    h = "#" * min(depth, 6)
    lines: list[str] = []
    for key, value in d.items():
        lines.append(f"{h} {key}")
        lines.append("")
        if isinstance(value, dict) and value:
            lines.extend(_render_aux_dict(value, depth + 1))
        else:
            lines.extend(_render_aux_value(value, indent=0))
            lines.append("")
    return lines


def _render_aux_value(value, indent: int) -> list[str]:
    """Render an arbitrary JSON value as Markdown lines."""
    prefix = "  " * indent

    if value is None:
        return [f"{prefix}_(null)_"]
    if isinstance(value, bool):
        return [f"{prefix}{'true' if value else 'false'}"]
    if isinstance(value, (int, float)):
        return [f"{prefix}{value}"]
    if isinstance(value, str):
        if not value:
            return [f"{prefix}_(empty)_"]
        if "\n" in value:
            # Multi-line: render as separate lines so paragraphs survive.
            return [f"{prefix}{ln}" for ln in value.split("\n")]
        return [f"{prefix}{value}"]

    if isinstance(value, list):
        if not value:
            return [f"{prefix}_(empty list)_"]
        # List of scalars: short bullet list.
        if all(isinstance(v, (str, int, float, bool, type(None))) for v in value):
            return [f"{prefix}- {_aux_fmt_scalar(v)}" for v in value]
        # List of complex items: bulleted with nested rendering.
        lines: list[str] = []
        for item in value:
            sub = _render_aux_value(item, indent + 1)
            if sub:
                lines.append(f"{prefix}- " + sub[0].lstrip())
                lines.extend(sub[1:])
            else:
                lines.append(f"{prefix}- _(empty)_")
        return lines

    if isinstance(value, dict):
        if not value:
            return [f"{prefix}_(empty)_"]
        lines = []
        for k, v in value.items():
            sub = _render_aux_value(v, indent + 1)
            if len(sub) == 1 and sub[0].strip():
                lines.append(f"{prefix}- **{k}:** {sub[0].strip()}")
            else:
                lines.append(f"{prefix}- **{k}:**")
                lines.extend(sub)
        return lines

    return [f"{prefix}{value}"]


def _aux_fmt_scalar(v) -> str:
    if v is None:
        return "_(null)_"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def to_yaml_frontmatter(d: dict) -> str:
    """Tiny dependency-free YAML emitter for flat string/number dicts."""
    lines = ["---"]
    for k, v in d.items():
        if v == "" or v is None:
            continue
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            s = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}: "{s}"')
    lines.append("---")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Convert a ChatGPT conversations.json export into Markdown files."
    )
    ap.add_argument("input", help="Path to conversations.json")
    ap.add_argument("-o", "--output", default="chatgpt_md",
                    help="Output directory (default: ./chatgpt_md)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process only the first N conversations (0 = all)")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Asset files sit beside conversations.json, so the export root is that
    # file's folder. Indexed once, before the loop.
    asset_index = chatgpt_assets.AssetIndex(in_path.parent)
    if asset_index.files_scanned:
        print(f"Asset index: {len(asset_index.by_id):,} id(s) from "
              f"{asset_index.files_scanned:,} file(s)")

    with in_path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Some exports wrap conversations in a top-level dict.
    if isinstance(data, dict):
        data = data.get("conversations") or [data]

    written = 0
    skipped = 0
    linked = 0
    missing = 0
    for i, conv in enumerate(data):
        if args.limit and written >= args.limit:
            break
        sink = chatgpt_assets.AssetSink(asset_index)
        try:
            fm, body, dstr = render_conversation(conv, sink=sink)
        except Exception as e:  # noqa: BLE001 — keep going through the export
            print(f"[skip] conversation {i}: {e}", file=sys.stderr)
            skipped += 1
            continue

        slug = slugify(fm["title"])
        # Group into a per-project / per-GPT subfolder when applicable.
        # pick_subdir reuses existing (possibly user-renamed) folders.
        subdir = pick_subdir(out_dir, fm.get("conversation_template_id", ""))
        target_dir = out_dir / subdir if subdir else out_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        out_file = target_dir / f"{dstr}__{slug}.md"
        n = 2
        while out_file.exists():
            out_file = target_dir / f"{dstr}__{slug}-{n}.md"
            n += 1

        body = sink.flush(out_file, body)
        if sink.resolved:
            fm["assets_linked"] = sink.resolved
        if sink.unresolved:
            fm["assets_missing"] = sink.unresolved
        linked += sink.resolved
        missing += sink.unresolved
        out_file.write_text(
            to_yaml_frontmatter(fm) + "\n\n" + body + "\n",
            encoding="utf-8",
        )
        written += 1

    print(f"Wrote {written} markdown file(s) to {out_dir}", end="")
    if skipped:
        print(f" ({skipped} skipped — see stderr)")
    else:
        print()
    if linked or missing:
        print(f"Assets: {linked:,} linked, {missing:,} referenced but not "
              f"present in the export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
