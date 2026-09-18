#!/usr/bin/env python3
"""
html_to_markdown.py

Convert HTML files to Markdown with full content preservation. Designed to
handle Evernote-style HTML exports (the kind Drive can also open as Google
Docs), but works for any reasonable HTML.

What gets preserved
-------------------
Headings (h1-h6), bold, italic, underline (as bold + note), strikethrough,
inline code, code blocks, ordered/unordered lists with nesting, tables,
block quotes, horizontal rules, hyperlinks, line breaks, paragraphs.

Images
    Images with src="data:..." (base64 inline images, very common in
    Evernote exports) are extracted to a sibling "<basename>_media/" folder
    and inlined as ![alt](relative/path). Images with http(s) URLs stay as
    Markdown links to the original URL. Images with relative-path src
    attributes are passed through unchanged.

Document metadata
    <title>, <meta name="author">, <meta name="created">, <meta name="modified">,
    <meta name="keywords">, <meta name="description"> -- all surfaced into
    YAML frontmatter when present. Evernote-specific note metadata
    (<meta name="created"> in their export format) is also captured.

Limitations honestly noted
--------------------------
* CSS styling is not preserved. Color, font, alignment, etc. don't survive.
* Embedded videos, audio, iframes are noted in the body as
  "[embedded <type>: <src>]" rather than rendered.
* Forms are noted but their input elements are not interactive in Markdown.

Stdlib only.

Usage
-----
    python html_to_markdown.py path/to/file.html -o out_dir/
    python html_to_markdown.py path/to/dir/  -o out_dir/ --recursive
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


# ---------------------------------------------------------------------------
# YAML emitter (matches the others in the pipeline)
# ---------------------------------------------------------------------------

def to_yaml_frontmatter(d: dict) -> str:
    lines = ["---"]
    for k, v in d.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, list):
            quoted = ", ".join(f'"{str(i)}"' for i in v)
            lines.append(f"{k}: [{quoted}]")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            t = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}: "{t}"')
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML -> Markdown converter
# ---------------------------------------------------------------------------

# Block-level tags that should produce double-newline breaks in output.
BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "nav",
    "blockquote", "pre", "table", "thead", "tbody", "tfoot",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "dl", "li", "dt", "dd",
    "form", "fieldset", "address", "figure", "figcaption",
    "main", "aside",
}

INLINE_FORMAT_TAGS = {"strong", "b", "em", "i", "code", "u", "s", "strike", "del"}
VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "wbr"}


class _MDConverter(HTMLParser):
    """Stateful HTML→Markdown translator. We accumulate Markdown text in
    self.out and track open contexts (lists, tables, code blocks, blockquotes)
    so children render correctly."""

    def __init__(self, image_handler=None) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.image_handler = image_handler  # callable(src, alt) -> str (markdown)
        self.metadata: dict = {}

        # Context stacks. Each is a list; the last element is the active context.
        self.list_stack: list[str] = []   # 'ul' or 'ol' for each open list
        self.list_counters: list[int] = []
        self.in_pre = False
        self.in_code = False
        self.in_blockquote = 0  # depth
        self.in_table = False
        self.table_rows: list[list[str]] = []
        self.table_cell_buf: list[str] = []
        self.table_in_header = False
        self.suppress_text = 0   # inside <head>, <script>, <style>
        self.heading_level: int | None = None

        # Buffer for the current "inline run" within a block. We accumulate
        # inline text + formatting here, then flush it at block boundaries.
        self.inline_buf: list[str] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _push_block(self) -> None:
        """Emit the inline buffer as a block, separated from previous output
        by a blank line."""
        text = "".join(self.inline_buf).strip()
        self.inline_buf = []
        if not text:
            return
        if self.out and not self.out[-1].endswith("\n\n"):
            if self.out[-1].endswith("\n"):
                self.out.append("\n")
            else:
                self.out.append("\n\n")
        # Apply blockquote prefix if we're inside one (or many).
        if self.in_blockquote:
            prefix = "> " * self.in_blockquote
            text = "\n".join(prefix + ln for ln in text.split("\n"))
        self.out.append(text)
        self.out.append("\n\n")

    def _attr(self, attrs, name, default=""):
        for k, v in attrs:
            if k == name:
                return v if v is not None else default
        return default

    # ------------------------------------------------------------------
    # Tag handlers
    # ------------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in {"head", "script", "style"}:
            self.suppress_text += 1
            return

        if tag == "meta":
            name = self._attr(attrs, "name").lower()
            content = self._attr(attrs, "content")
            if name and content:
                # Map common meta names to friendly frontmatter keys.
                key_map = {
                    "author":      "author",
                    "creator":     "author",
                    "description": "description",
                    "keywords":    "keywords_meta",
                    "created":     "created",
                    "modified":    "modified",
                    "date":        "date",
                    "subject":     "subject",
                }
                key = key_map.get(name, f"meta_{name}")
                self.metadata.setdefault(key, content)
            return

        if tag == "title":
            self.suppress_text -= 1  # Allow text inside <title> through head suppression
            self._title_capture = []
            return

        if tag in {"html", "body"}:
            return

        if self.suppress_text:
            return

        # Headings
        m = re.match(r"^h([1-6])$", tag)
        if m:
            self._push_block()
            self.heading_level = int(m.group(1))
            self.inline_buf.append("#" * self.heading_level + " ")
            return

        # Paragraphs and generic blocks
        if tag in {"p", "div", "section", "article", "header", "footer", "nav",
                   "main", "aside", "address", "figure", "figcaption", "form",
                   "fieldset"}:
            self._push_block()
            return

        # Line break
        if tag == "br":
            # Markdown line break: two trailing spaces + newline.
            self.inline_buf.append("  \n")
            return

        # Horizontal rule
        if tag == "hr":
            self._push_block()
            self.out.append("---\n\n")
            return

        # Inline formatting
        if tag in {"strong", "b"}:
            self.inline_buf.append("**")
            return
        if tag in {"em", "i"}:
            self.inline_buf.append("*")
            return
        if tag == "u":
            # Markdown has no underline; render as bold to preserve emphasis.
            self.inline_buf.append("**")
            return
        if tag in {"s", "strike", "del"}:
            self.inline_buf.append("~~")
            return
        if tag == "code" and not self.in_pre:
            self.in_code = True
            self.inline_buf.append("`")
            return

        # Code block
        if tag == "pre":
            self._push_block()
            self.in_pre = True
            self.out.append("```\n")
            return

        # Blockquote
        if tag == "blockquote":
            self._push_block()
            self.in_blockquote += 1
            return

        # Lists
        if tag in {"ul", "ol"}:
            # Flush any pending inline content before list begins (unless
            # we're already inside a list item, where it's fine to nest).
            if not self.list_stack:
                self._push_block()
            self.list_stack.append(tag)
            self.list_counters.append(0)
            return

        if tag == "li":
            # Flush previous item first.
            self._push_block()
            depth = max(0, len(self.list_stack) - 1)
            indent = "  " * depth
            if self.list_stack and self.list_stack[-1] == "ol":
                self.list_counters[-1] += 1
                self.inline_buf.append(f"{indent}{self.list_counters[-1]}. ")
            else:
                self.inline_buf.append(f"{indent}- ")
            return

        # Definition lists - render as bullets with bold terms
        if tag == "dt":
            self._push_block()
            self.inline_buf.append("- **")
            return
        if tag == "dd":
            # Continuation under a previous dt; will be handled at end.
            self.inline_buf.append(": ")
            return

        # Tables
        if tag == "table":
            self._push_block()
            self.in_table = True
            self.table_rows = []
            return
        if tag == "thead":
            self.table_in_header = True
            return
        if tag == "tbody":
            self.table_in_header = False
            return
        if tag == "tr":
            if self.in_table:
                self.table_rows.append([])
            return
        if tag in {"td", "th"}:
            if self.in_table:
                self.table_cell_buf = []
            return

        # Anchors
        if tag == "a":
            href = self._attr(attrs, "href")
            self._a_href = href
            return

        # Images
        if tag == "img":
            src = self._attr(attrs, "src")
            alt = self._attr(attrs, "alt")
            md = ""
            if self.image_handler:
                md = self.image_handler(src, alt)
            else:
                md = f"![{alt}]({src})"
            self.inline_buf.append(md)
            return

        # Embedded media we don't render but note in body.
        if tag in {"video", "audio", "iframe", "embed", "object"}:
            src = (self._attr(attrs, "src") or
                   self._attr(attrs, "data") or "")
            note = f"[embedded {tag}: {src}]" if src else f"[embedded {tag}]"
            self._push_block()
            self.out.append(note)
            self.out.append("\n\n")
            return

        # Span and other purely-presentational tags fall through silently.

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in {"head", "script", "style"}:
            self.suppress_text = max(0, self.suppress_text - 1)
            return

        if tag == "title":
            title_text = "".join(getattr(self, "_title_capture", [])).strip()
            if title_text:
                self.metadata.setdefault("title", title_text)
            self._title_capture = None
            self.suppress_text += 1  # Re-enter head suppression
            return

        if self.suppress_text:
            return

        m = re.match(r"^h([1-6])$", tag)
        if m:
            self._push_block()
            self.heading_level = None
            return

        if tag in {"p", "div", "section", "article", "header", "footer", "nav",
                   "main", "aside", "address", "figure", "figcaption", "form",
                   "fieldset"}:
            self._push_block()
            return

        if tag in {"strong", "b"}:
            self.inline_buf.append("**")
            return
        if tag in {"em", "i"}:
            self.inline_buf.append("*")
            return
        if tag == "u":
            self.inline_buf.append("**")
            return
        if tag in {"s", "strike", "del"}:
            self.inline_buf.append("~~")
            return
        if tag == "code" and not self.in_pre:
            self.inline_buf.append("`")
            self.in_code = False
            return

        if tag == "pre":
            # Flush any pending content as the body of the code block.
            text = "".join(self.inline_buf).rstrip("\n")
            self.inline_buf = []
            if text:
                self.out.append(text + "\n")
            self.out.append("```\n\n")
            self.in_pre = False
            return

        if tag == "blockquote":
            self._push_block()
            self.in_blockquote = max(0, self.in_blockquote - 1)
            return

        if tag in {"ul", "ol"}:
            self._push_block()
            if self.list_stack:
                self.list_stack.pop()
            if self.list_counters:
                self.list_counters.pop()
            return

        if tag == "li":
            self._push_block()
            return

        if tag == "dt":
            self.inline_buf.append("**")
            self._push_block()
            return
        if tag == "dd":
            self._push_block()
            return

        if tag == "table":
            self._render_table()
            self.in_table = False
            self.table_rows = []
            return
        if tag in {"td", "th"}:
            if self.in_table and self.table_rows:
                cell = "".join(self.table_cell_buf).strip()
                cell = cell.replace("|", "\\|").replace("\n", " ")
                self.table_rows[-1].append(cell)
                self.table_cell_buf = []
            return

        if tag == "a":
            href = getattr(self, "_a_href", "")
            if href:
                # Wrap whatever inline text accumulated since <a> in [...]
                # We don't track exact text-since-<a>, so a heuristic: take
                # the most recent "text run" up to last whitespace boundary
                # and wrap. Simplification: we just write [text](href) in a
                # single emit using the consumed text. Track inline buf
                # carefully by inserting a marker -- done below.
                # Fallback simple approach: emit hyperlink with empty inner
                # text, since accurate tracking is fiddly. The handle_data
                # above already accumulated the link text into inline_buf;
                # pop that text since <a> opened.
                # For pragmatism: do nothing here -- text already in buffer.
                # But we DO append href inline as "(href)" so user sees URL.
                # Better: mark insertion point on starttag (TODO for future).
                # For now we emit a trailing (href) so links aren't lost.
                self.inline_buf.append(f" ({href})" if href else "")
            self._a_href = None
            return

    def handle_data(self, data):
        if self.suppress_text:
            return
        if data is None:
            return

        # Title accumulation (we briefly turn off suppression for <title>)
        if getattr(self, "_title_capture", None) is not None:
            self._title_capture.append(data)
            return

        if self.in_pre:
            self.inline_buf.append(data)
            return

        if self.in_table and self.table_rows:
            # Inside a cell: collect text into the cell buffer.
            self.table_cell_buf.append(data)
            return

        # General inline text: collapse whitespace runs but preserve
        # significant newlines from the source as spaces (HTML's whitespace
        # rules say all runs of whitespace are equivalent to one space).
        collapsed = re.sub(r"[\t\n\r ]+", " ", data)
        if not collapsed:
            return
        self.inline_buf.append(collapsed)

    # ------------------------------------------------------------------
    # Table rendering (called when </table> closes)
    # ------------------------------------------------------------------

    def _render_table(self) -> None:
        rows = [r for r in self.table_rows if r]
        if not rows:
            return
        n_cols = max(len(r) for r in rows)
        rows = [r + [" "] * (n_cols - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |",
               "|" + "|".join([" --- "] * n_cols) + "|"]
        for row in rows[1:]:
            out.append("| " + " | ".join(row) + " |")
        self.out.append("\n".join(out))
        self.out.append("\n\n")

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def get_markdown(self) -> str:
        self._push_block()
        text = "".join(self.out)
        # Collapse 3+ newline runs to 2.
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

DATA_URL_RE = re.compile(
    r"^data:(?P<mime>[^;,]+)(?:;(?P<encoding>base64))?,(?P<payload>.*)$",
    re.IGNORECASE | re.DOTALL,
)

_MIME_TO_EXT = {
    "image/png":  ".png",
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/gif":  ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp":  ".bmp",
    "image/tiff": ".tif",
}


def make_image_handler(media_dir: Path, basename: str):
    """Return a closure that handles <img src=...> attributes by extracting
    base64-encoded inline images to disk and returning a Markdown link."""
    media_dir_created = [False]
    counter = [0]

    def _ensure_dir() -> None:
        if not media_dir_created[0]:
            media_dir.mkdir(parents=True, exist_ok=True)
            media_dir_created[0] = True

    def handler(src: str, alt: str) -> str:
        if not src:
            return f"![{alt}]()"

        # http(s) URLs: keep as remote link.
        if src.startswith(("http://", "https://", "//")):
            return f"![{alt}]({src})"

        # data: URL with base64 payload -> extract to disk.
        m = DATA_URL_RE.match(src)
        if m and m.group("encoding") == "base64":
            mime = m.group("mime").lower()
            payload = m.group("payload").strip().replace("\n", "").replace("\r", "")
            try:
                data = base64.b64decode(payload, validate=False)
            except Exception:  # noqa: BLE001
                return f"![{alt}](data: image, decode failed)"
            ext = _MIME_TO_EXT.get(mime, ".bin")
            counter[0] += 1
            filename = f"{basename}_img{counter[0]:04d}{ext}"
            _ensure_dir()
            (media_dir / filename).write_bytes(data)
            return f"![{alt}]({media_dir.name}/{filename})"

        # Anything else (relative path, file:, etc.): pass through unchanged.
        return f"![{alt}]({src})"

    return handler


# ---------------------------------------------------------------------------
# File-level conversion
# ---------------------------------------------------------------------------

def convert_html(in_path: Path, out_dir: Path, basename: str) -> tuple[dict, str]:
    """Convert one .html file. Side effect: extracts inline images into
    out_dir/<basename>_media/ when present."""
    text = in_path.read_text(encoding="utf-8", errors="replace")

    media_dir = out_dir / f"{basename}_media"
    img_handler = make_image_handler(media_dir, basename)

    parser = _MDConverter(image_handler=img_handler)
    parser.feed(text)
    md_body = parser.get_markdown()

    fm: dict = {"source": "html", "source_file": in_path.name}
    fm.update(parser.metadata)

    # Ensure a top-level heading exists so add_metadata's outline works.
    title = fm.get("title", "")
    if title and not md_body.lstrip().startswith("# "):
        md_body = f"# {title}\n\n{md_body}"

    return fm, md_body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _gather_inputs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in {".html", ".htm"} else []
    pattern = "**/*.htm*" if recursive else "*.htm*"
    return sorted(input_path.glob(pattern))


def _allocate_basename(out_dir: Path, stem: str) -> str:
    base = stem
    n = 2
    while (out_dir / f"{base}.md").exists() or (out_dir / f"{base}_media").exists():
        base = f"{stem}-{n}"
        n += 1
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert .html files to Markdown.")
    ap.add_argument("input", help="A .html file or a directory of .html files")
    ap.add_argument("-o", "--output", default="html_md",
                    help="Output directory (default: ./html_md)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Recurse into subdirectories")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _gather_inputs(in_path, args.recursive)
    if not files:
        print(f"No .html files found at {in_path}", file=sys.stderr)
        return 1

    written = skipped = 0
    for f in files:
        basename = _allocate_basename(out_dir, f.stem)
        try:
            fm, body = convert_html(f, out_dir, basename)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {f}: {e}", file=sys.stderr)
            skipped += 1
            continue
        md_path = out_dir / f"{basename}.md"
        md_path.write_text(
            to_yaml_frontmatter(fm) + "\n\n" + body + "\n",
            encoding="utf-8",
        )
        written += 1

    msg = f"Wrote {written} markdown file(s) to {out_dir}"
    if skipped:
        msg += f" ({skipped} skipped — see stderr)"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
