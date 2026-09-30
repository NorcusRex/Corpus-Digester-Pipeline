#!/usr/bin/env python3
"""
inspect_chatgpt_assets.py

Report how a ChatGPT export refers to its images, audio and uploads, so the
converter can be taught to resolve those references instead of discarding them.

Why this exists
---------------
`chatgpt_to_markdown.extract_text` takes the `text` field of a multimodal
content part and, finding none, writes "[<content_type> content omitted]" and
throws the rest of the part away -- including the pointer naming the file. The
export does carry the link between a conversation and its assets; the converter
drops it. Teaching it to resolve the pointer needs the pointer's actual shape,
and that has changed across ChatGPT export versions.

READ-ONLY, and it prints no message text
----------------------------------------
Nothing is written, moved or modified. The output is deliberately limited to:

  * which content types appear, and how often
  * which keys those parts carry
  * a few example pointer strings, truncated
  * the shape of filenames sitting in the export folder
  * whether a pointer can be matched to a file on disk, and by what rule

Conversation content is never printed. Sample pointers are identifiers, not
prose. Inspect the output before sharing it if the export is sensitive.

Usage
-----
    python inspect_chatgpt_assets.py "I:\\path\\to\\ChatGPT-export-folder"
    python inspect_chatgpt_assets.py <folder> --samples 8
    python inspect_chatgpt_assets.py <folder> --report assets.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Keys that hold a reference to an asset rather than prose.
POINTER_KEYS = (
    "asset_pointer", "audio_asset_pointer", "image_url", "file_id",
    "id", "name", "file_name", "video_container_asset_pointer",
    "frames_asset_pointers", "file_token_size",
)

# Keys we never print the value of, because they hold conversation content.
CONTENT_KEYS = {"text", "parts", "transcript", "title", "prompt", "content"}

# A pointer such as "file-service://file-ABC123" or "sediment://file_0000xyz".
POINTER_ID_RE = re.compile(r"(file[-_][A-Za-z0-9]+)")


def truncate(value: object, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def walk_parts(conv: dict):
    """Yield every non-string content part in a conversation."""
    mapping = conv.get("mapping") or {}
    nodes = mapping.values() if isinstance(mapping, dict) else []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if isinstance(part, dict):
                yield part
        # Attachments live on the message metadata, not in parts.
        meta = message.get("metadata")
        if isinstance(meta, dict):
            for att in meta.get("attachments") or []:
                if isinstance(att, dict):
                    yield {"_source": "metadata.attachments", **att}


def load_conversations(export_root: Path):
    """Yield conversations from every conversations*.json in the folder."""
    for path in sorted(export_root.glob("conversations*.json")):
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  [warn] could not read {path.name}: {e}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            data = data.get("conversations") or [data]
        if not isinstance(data, list):
            continue
        for conv in data:
            if isinstance(conv, dict):
                yield path.name, conv


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report how a ChatGPT export references its assets. "
                    "Read-only; prints no conversation text.")
    ap.add_argument("export_root", help="Folder holding conversations*.json")
    ap.add_argument("--samples", type=int, default=5,
                    help="Example pointer strings to show per content type")
    ap.add_argument("--report", default=None,
                    help="Also write the output to this file")
    args = ap.parse_args()

    root = Path(args.export_root).resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    if not any(root.glob("conversations*.json")):
        print(f"ERROR: no conversations*.json in {root}", file=sys.stderr)
        return 2

    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text)
        lines.append(text)

    say("ChatGPT export asset inspection")
    say(f"Folder: {root}")
    say()

    # ---- Files on disk ----------------------------------------------------
    on_disk = [p for p in root.rglob("*")
               if p.is_file() and p.suffix.lower() != ".json"]
    by_ext = Counter(p.suffix.lower() or "(no extension)" for p in on_disk)
    say(f"Non-JSON files in the export folder: {len(on_disk):,}")
    for ext, n in by_ext.most_common(15):
        say(f"  {ext:<16} {n:>7,}")
    say()

    say("Example filenames (shape only, first 10):")
    for p in on_disk[:10]:
        say(f"  {p.relative_to(root).as_posix()}")
    say()

    # Index the ids embedded in filenames, which is how a pointer is resolved.
    ids_on_disk: dict[str, Path] = {}
    for p in on_disk:
        for match in POINTER_ID_RE.findall(p.name):
            ids_on_disk.setdefault(match, p)
    say(f"Filenames carrying a file-id: {len(ids_on_disk):,}")
    say()

    # ---- Content parts ----------------------------------------------------
    type_counts: Counter = Counter()
    keys_by_type: dict[str, Counter] = defaultdict(Counter)
    samples_by_type: dict[str, list[str]] = defaultdict(list)
    pointer_key_counts: Counter = Counter()
    resolvable = 0
    unresolvable = 0
    unresolved_samples: list[str] = []
    conv_count = 0

    for _file, conv in load_conversations(root):
        conv_count += 1
        for part in walk_parts(conv):
            ctype = str(part.get("content_type")
                        or part.get("_source")
                        or "(no content_type)")
            type_counts[ctype] += 1
            for key in part:
                keys_by_type[ctype][key] += 1

            for key in POINTER_KEYS:
                if key not in part or key in CONTENT_KEYS:
                    continue
                value = part[key]
                if not isinstance(value, (str, int)):
                    continue
                pointer_key_counts[f"{ctype}.{key}"] += 1
                if len(samples_by_type[ctype]) < args.samples:
                    samples_by_type[ctype].append(f"{key} = {truncate(value)}")
                found = POINTER_ID_RE.findall(str(value))
                if found:
                    if any(f in ids_on_disk for f in found):
                        resolvable += 1
                    else:
                        unresolvable += 1
                        if len(unresolved_samples) < args.samples:
                            unresolved_samples.append(
                                f"{ctype}.{key} = {truncate(value)}")

    say(f"Conversations scanned: {conv_count:,}")
    say()
    say("Content types found in message parts:")
    for ctype, n in type_counts.most_common():
        say(f"  {ctype:<46} {n:>7,}")
    say()

    say("Keys carried by each content type:")
    for ctype, _n in type_counts.most_common():
        keys = ", ".join(k for k, _ in keys_by_type[ctype].most_common())
        say(f"  {ctype}")
        say(f"    {keys}")
    say()

    say("Example pointer values (identifiers, not prose):")
    for ctype, examples in samples_by_type.items():
        if not examples:
            continue
        say(f"  {ctype}")
        for example in examples:
            say(f"    {example}")
    say()

    say("Pointer-to-file matching, by embedded file-id:")
    say(f"  pointers matching a file on disk : {resolvable:,}")
    say(f"  pointers with no matching file   : {unresolvable:,}")
    if unresolved_samples:
        say("  examples that did not match:")
        for example in unresolved_samples:
            say(f"    {example}")
    say()
    say("A high match count means the converter can resolve pointers by the")
    say("file-id embedded in the filename. A low one means the mapping works")
    say("some other way, and these samples will show how.")

    if args.report:
        try:
            Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"\nWritten to {args.report}")
        except OSError as e:
            print(f"\n[warn] could not write report: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
