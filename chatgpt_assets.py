#!/usr/bin/env python3
"""
chatgpt_assets.py

Resolve a ChatGPT export's asset pointers to the files sitting beside it.

THE PROBLEM

A ChatGPT export stores images, audio and uploads as loose files in the export
folder, and refers to them from inside conversations by pointer. The converter
used to discard the pointer and write "[image_asset_pointer content omitted]",
so an export carrying 1,424 asset files produced Markdown referring to none of
them.

WHAT THE POINTERS ACTUALLY LOOK LIKE

Measured against a real export (`docs/findings/`), not assumed. Two schemes,
which is the fact a single-regex resolver gets wrong:

    file-service://file-47Ompsoh1mqHQ9MVjG7ygH1c     images, uploads  (hyphen)
    sediment://file_00000000eae051f6948c352f06f33a39 audio, voice     (underscore)

A resolver matching only `file-` silently misses every audio and voice-mode
asset. The two id shapes differ as well: the `file-` form is mixed-case
alphanumeric, the `file_` form is lowercase hex.

Filenames on disk embed the id, in two shapes:

    file-1EuiALVZTgMsxudEAVjafJ-1000007970.jpg
    246ad1b13b9fce3#file_00000000457071fbaf2186bc87fbf2ef#p_4.jpg-p_4.jpg

So resolution is one folder scan building an id-to-path index, not a search per
pointer.

POINTERS NEST

`real_time_user_audio_video_asset_pointer` carries `audio_asset_pointer`,
`frames_asset_pointers` (a list) and `video_container_asset_pointer` inside
itself. Reading a top-level `asset_pointer` key finds nothing in those. This
module walks the whole part recursively and collects every pointer-shaped
string it finds, at any depth, under any key.

WHAT CANNOT BE RESOLVED, AND WHY THAT IS NOT A BUG

**ChatGPT does not export the bytes of files you uploaded.** The inspection
found two `.pdf` files on disk against attachment entries naming several, and
every unmatched sample was an attachment id. The export carries an
attachment's name, size and MIME type; it does not carry the attachment.

Nothing here can recover those. What it does instead is name them: an
unresolved reference becomes a marker carrying whatever the export knows, so
the reader learns that a file was there and what it was called. Silence would
be the worse answer, and was the old behaviour.

EXTENSIONS

114 files in the measured export have no extension at all, and an extension is
not cosmetic: without one, Obsidian and NotebookLM will not render the image.

The obvious source turns out not to work. A part's `content_type` names the
part -- literally the string `image_asset_pointer` -- not the media type, so
there is no MIME type to read. Attachments do carry `mime_type`, and that is
used where present; everything else is identified by its first bytes. Found by
testing, after the first version confidently produced `.bin`.
"""

from __future__ import annotations

import mimetypes
import re
import shutil
from pathlib import Path

# A pointer value, in either scheme. The id is captured.
POINTER_RE = re.compile(
    r"(?:file-service|sediment)://(file[-_][A-Za-z0-9]+)", re.IGNORECASE)

# An id embedded anywhere in a filename. Bounded on the right by a separator
# the export actually uses (`-`, `#`, `.`) or end of string, so that
# `file-ABC-name.jpg` yields `file-ABC` rather than swallowing the name.
FILENAME_ID_RE = re.compile(r"(file_[0-9a-f]{8,}|file-[A-Za-z0-9]{10,})")

# Files that are the export itself rather than its assets.
NON_ASSET_SUFFIXES = {".json"}

# The token the renderer writes in place of a media folder name, because the
# output filename is not known until after the body has been rendered. The
# sink substitutes it in `flush`.
MEDIA_TOKEN = "\x00MEDIA\x00"


def pointer_ids(value) -> list[str]:
    """Every asset id referenced anywhere inside `value`, at any depth.

    Walks dicts and lists rather than reading known keys, because
    `real_time_user_audio_video_asset_pointer` nests its pointers and the set
    of nesting keys is not stable across export versions.
    """
    found: list[str] = []

    def walk(v) -> None:
        if isinstance(v, str):
            m = POINTER_RE.search(v)
            if m:
                found.append(m.group(1))
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    # Dedupe, keeping order: a part may name the same asset twice.
    seen = set()
    return [i for i in found if not (i in seen or seen.add(i))]


def attachment_ids(value) -> list[str]:
    """Every uploaded-attachment id referenced anywhere inside `value`.

    Attachments live on `message.metadata.attachments` and their ids are bare
    (`file-5n5yAEwAeemzD4K0KistfDy9`), not pointer URLs, so `pointer_ids`
    does not see them. Most are not on disk -- ChatGPT exports the reference,
    not the file -- but the ones that are must travel with their conversation
    when an export is split, or they would be left behind.
    """
    found: list[str] = []

    def walk(v) -> None:
        if isinstance(v, dict):
            atts = v.get("attachments")
            if isinstance(atts, list):
                for a in atts:
                    if isinstance(a, dict) and isinstance(a.get("id"), str):
                        found.append(a["id"])
            for item in v.values():
                walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    seen = set()
    return [i for i in found if not (i in seen or seen.add(i))]


class AssetIndex:
    """Every asset file in an export, indexed by the id in its filename."""

    def __init__(self, export_root: Path):
        self.root = Path(export_root)
        self.by_id: dict[str, Path] = {}
        self.files_scanned = 0
        self.files_without_id = 0
        self._build()

    def _build(self) -> None:
        if not self.root.is_dir():
            return
        for f in sorted(self.root.rglob("*")):
            if not f.is_file() or f.suffix.lower() in NON_ASSET_SUFFIXES:
                continue
            self.files_scanned += 1
            ids = FILENAME_ID_RE.findall(f.name)
            if not ids:
                self.files_without_id += 1
                continue
            for i in ids:
                # First file wins. The export does not duplicate ids in
                # practice; if it ever does, taking the first is stable
                # across runs because the scan is sorted.
                self.by_id.setdefault(i, f)

    def resolve(self, asset_id: str) -> Path | None:
        return self.by_id.get(asset_id)


# First bytes -> extension, for the formats this export actually contains.
# Checked in order; WEBP and WAV share the RIFF header and are told apart by
# the form type at offset 8.
_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"%PDF-", ".pdf"),
    (b"ID3", ".mp3"),
    (b"OggS", ".ogg"),
]


def sniff_extension(path: Path) -> str | None:
    """Extension from a file's first bytes, or None if unrecognised."""
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head[:4] == b"RIFF" and len(head) >= 12:
        form = head[8:12]
        if form == b"WEBP":
            return ".webp"
        if form == b"WAVE":
            return ".wav"
        if form == b"AVI ":
            return ".avi"
    for magic, ext in _MAGIC:
        if head.startswith(magic):
            return ext
    if head[4:8] == b"ftyp":
        return ".mp4"
    return None


def _extension_for(path: Path, content_type: str | None) -> str:
    """The extension to give a copied asset.

    Order matters. The source filename wins where it has one. A real MIME type
    comes second -- attachments carry `mime_type`, though most attachments are
    not on disk to be copied. Byte sniffing is what actually resolves the
    extensionless files, because an asset part's `content_type` is the name of
    the part, not a media type.
    """
    if path.suffix and len(path.suffix) <= 6:
        return path.suffix
    if content_type and "/" in content_type:
        guess = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guess:
            return guess
    return sniff_extension(path) or ".bin"


class AssetSink:
    """Collects the assets a conversation references, then places them.

    Two phases because the output filename is not known while the body is
    being rendered: the media folder is named after the Markdown file, and
    that name can gain a disambiguating suffix. So rendering writes
    `MEDIA_TOKEN/<name>` and `flush` rewrites it once the path is settled.
    """

    def __init__(self, index: AssetIndex | None):
        self.index = index
        self.pending: dict[str, Path] = {}   # output filename -> source path
        self.resolved = 0
        self.unresolved = 0

    def link(self, asset_id: str, content_type: str | None = None) -> str | None:
        """A relative link for `asset_id`, or None if the file is not present."""
        src = self.index.resolve(asset_id) if self.index else None
        if src is None:
            self.unresolved += 1
            return None
        name = f"{asset_id}{_extension_for(src, content_type)}"
        self.pending[name] = src
        self.resolved += 1
        return f"{MEDIA_TOKEN}/{name}"

    def flush(self, md_path: Path, body: str) -> str:
        """Copy the collected assets beside `md_path` and fix up the body."""
        if not self.pending:
            return body.replace(f"{MEDIA_TOKEN}/", "")
        media_dir = md_path.parent / f"{md_path.stem}_media"
        media_dir.mkdir(parents=True, exist_ok=True)
        for name, src in self.pending.items():
            dest = media_dir / name
            # Re-copy only when the size differs, so a re-run does not churn
            # every asset through Drive sync for no reason.
            try:
                if dest.exists() and dest.stat().st_size == src.stat().st_size:
                    continue
            except OSError:
                pass
            try:
                shutil.copy2(src, dest)
            except OSError as e:
                print(f"  [warn] could not copy asset {name}: {e}")
        return body.replace(MEDIA_TOKEN, media_dir.name)


def render_part(part: dict, sink: AssetSink | None) -> str:
    """Markdown for a multimodal content part that carries no text."""
    ctype = part.get("content_type") or "non-text"
    ids = pointer_ids(part)

    if not ids:
        return f"[{ctype}: no asset reference in the export]"

    out: list[str] = []
    for asset_id in ids:
        link = sink.link(asset_id, part.get("content_type")) if sink else None
        if link is None:
            # Named rather than silent: the reader learns a file was here.
            out.append(f"[{ctype} `{asset_id}` — not included in the export]")
        elif str(part.get("content_type", "")).startswith("image"):
            out.append(f"![image]({link})")
        else:
            out.append(f"[{ctype.replace('_', ' ')}]({link})")
    return "\n".join(out)


def render_attachments(message: dict, sink: AssetSink | None) -> str:
    """Markdown listing a message's uploaded attachments.

    These live on `message.metadata.attachments`, not in `content.parts`, so
    the converter never saw them at all. Mostly they cannot be resolved --
    ChatGPT exports the reference, not the file -- but the name is real
    information and worth carrying.
    """
    meta = message.get("metadata") or {}
    attachments = meta.get("attachments") or []
    if not isinstance(attachments, list) or not attachments:
        return ""

    lines: list[str] = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        name = att.get("name") or att.get("id") or "unnamed attachment"
        mime = att.get("mime_type") or att.get("mimeType") or ""
        aid = att.get("id") or ""
        link = sink.link(aid, mime) if (sink and aid) else None
        if link:
            lines.append(f"- [{name}]({link})")
        else:
            detail = f" ({mime})" if mime else ""
            lines.append(f"- {name}{detail} — not included in the export")
    if not lines:
        return ""
    return "**Attachments:**\n" + "\n".join(lines)
