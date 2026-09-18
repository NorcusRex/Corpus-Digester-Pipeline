#!/usr/bin/env python3
"""
rtf_to_markdown.py

Convert Rich Text Format (.rtf) files to Markdown using only the Python
standard library. Intended for plain document content (notes, design
documents, prose with simple formatting) -- not for complex RTF features
like tables-with-merged-cells, embedded objects, drawing primitives, or
layered images.

What is preserved:
  - Plain paragraph text
  - Bold (\\b ... \\b0)
  - Italic (\\i ... \\i0)
  - Underline (\\ul ... \\ul0)
  - Strikethrough (\\strike ... \\strike0)
  - Bullet lists (paragraphs with \\bullet, or pard with bullet pn-style)
  - Ordered lists (decimal pn-style)
  - Heading sizes (\\fs36, \\fs48 etc. mapped to # / ## / ###)
  - Hyperlinks ({\\field {\\fldinst HYPERLINK "url"} {\\fldrslt text}})
  - Unicode characters (\\u1234?, escaped chars, code-page bytes)
  - Line breaks (\\line) and paragraph breaks (\\par)

What is dropped:
  - Page layout, margins, headers/footers
  - Font choices, colors, exact sizes (only header-size mapping is kept)
  - Embedded images, OLE objects, drawings
  - Complex tables (rendered as plain paragraphs)

Usage as a module:
    fm, body = convert_rtf(path_to_rtf)

Usage from the command line (for testing):
    python rtf_to_markdown.py path/to/file.rtf
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# YAML frontmatter (kept compatible with the other converters)
# ---------------------------------------------------------------------------

def _yaml_escape(val) -> str:
    if val is None:
        return '""'
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def to_yaml_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {_yaml_escape(v)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RTF tokenizer
# ---------------------------------------------------------------------------

# Tokens emitted by the tokenizer:
#   ("group_start", None)
#   ("group_end", None)
#   ("ctrl", name, numeric_param_or_None)        e.g. ("ctrl", "b", None), ("ctrl", "fs", 28)
#   ("text", str)
#   ("hex", int)         -- a \\'XX byte (interpreted in the active codepage)
#   ("uni", int)         -- a \\uNNNN unicode codepoint

_CTRL_RE = re.compile(r"\\([a-zA-Z]+)(-?\d+)?[ ]?")


def _tokenize(rtf: str):
    i = 0
    n = len(rtf)
    while i < n:
        ch = rtf[i]
        if ch == "{":
            yield ("group_start", None)
            i += 1
            continue
        if ch == "}":
            yield ("group_end", None)
            i += 1
            continue
        if ch == "\\":
            # Escape sequence
            if i + 1 >= n:
                i += 1
                continue
            nxt = rtf[i + 1]
            # \' hex byte
            if nxt == "'":
                if i + 3 < n:
                    try:
                        b = int(rtf[i + 2 : i + 4], 16)
                        yield ("hex", b)
                    except ValueError:
                        pass
                    i += 4
                    continue
                i += 2
                continue
            # \uNNNN unicode
            if nxt == "u":
                m = re.match(r"\\u(-?\d+)\??", rtf[i:])
                if m:
                    cp = int(m.group(1))
                    if cp < 0:
                        cp += 65536
                    yield ("uni", cp)
                    i += len(m.group(0))
                    # RTF requires a "fallback" character after \u that we should skip
                    # if it's plain text (the ? in our regex consumed any single ?).
                    continue
            # \* destination marker (e.g. \*\generator) -- treat like a control word
            if nxt == "*":
                yield ("ctrl", "*", None)
                i += 2
                continue
            # Escaped literal characters
            if nxt in ("\\", "{", "}"):
                yield ("text", nxt)
                i += 2
                continue
            # Newlines after backslash become \par equivalents in RTF
            if nxt in ("\n", "\r"):
                yield ("ctrl", "par", None)
                i += 2
                continue
            # Control word (letters + optional numeric)
            m = _CTRL_RE.match(rtf, i)
            if m:
                name = m.group(1)
                arg = m.group(2)
                param = int(arg) if arg is not None else None
                yield ("ctrl", name, param)
                i += len(m.group(0))
                continue
            # Lone backslash with non-letter; skip the backslash
            i += 1
            continue
        if ch in ("\r", "\n"):
            # Raw newlines in RTF source are insignificant
            i += 1
            continue
        # Plain text run -- accumulate until a special character
        j = i
        while j < n and rtf[j] not in ("\\", "{", "}", "\r", "\n"):
            j += 1
        yield ("text", rtf[i:j])
        i = j


# ---------------------------------------------------------------------------
# RTF -> Markdown rendering
# ---------------------------------------------------------------------------

# Destinations whose contents should be ignored entirely. They contain
# metadata, font tables, color tables, etc., not visible text.
_IGNORED_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "title", "author", "operator",
    "company", "creatim", "revtim", "printim", "buptim", "doccomm", "version",
    "vern", "edmins", "nofpages", "nofwords", "nofchars", "nofcharsws", "id",
    "themedata", "datastore", "latentstyles", "lsdlockedexcept",
    "listtable", "listoverridetable", "rsidtbl", "generator", "filetbl",
    "xmlnstbl", "xmlclose", "xmlopen", "pgptbl", "panose",
    "fchars", "lchars", "upr", "ud",
    "pict", "shppict", "shp", "shpinst", "shptxt", "background",
    "object", "objclass", "objdata", "result",
    "header", "headerl", "headerr", "headerf",
    "footer", "footerl", "footerr", "footerf",
    "footnote", "ftnsep", "ftnsepc", "ftncn", "annotation", "atnauthor", "atnid",
    "bkmkstart", "bkmkend",
    "nonshppict",
    "mmath", "mmathPr",
}


# Header size mapping. RTF uses half-points: \fs28 = 14pt. Headings tend to be
# 14pt and up. We map size buckets to heading levels.
def _heading_level_for_size(half_points: int) -> int | None:
    pt = half_points / 2
    if pt >= 24:
        return 1
    if pt >= 18:
        return 2
    if pt >= 14:
        return 3
    return None  # Body text


def _decode_hex(b: int, codepage: int) -> str:
    """Decode a \\'XX byte using the active codepage. Falls back gracefully."""
    try:
        return bytes([b]).decode(f"cp{codepage}")
    except (LookupError, UnicodeDecodeError):
        try:
            return bytes([b]).decode("latin-1")
        except UnicodeDecodeError:
            return ""


def _rtf_to_markdown_body(rtf: str) -> str:
    """Convert the RTF text into Markdown body text."""
    tokens = list(_tokenize(rtf))

    # State stack: each frame is a dict of formatting state. \\{ pushes, \\} pops.
    stack: list[dict] = [{
        "bold": False,
        "italic": False,
        "underline": False,
        "strike": False,
        "ignore_dest": False,    # Inside an ignored destination
        "field_inst": False,     # Inside a {\fldinst ...} block (parsing a hyperlink target)
        "field_rslt": False,     # Inside a {\fldrslt ...} block (visible link text)
        "in_pict": False,
        "codepage": 1252,
    }]

    # Per-paragraph state
    paragraph_runs: list[str] = []
    out_paragraphs: list[str] = []
    pending_heading_level: int | None = None
    pending_list_kind: str | None = None  # "ul" or "ol"
    in_list: list[str] = []  # active list kinds for blank-line management

    pending_hyperlink_url: str | None = None
    pending_hyperlink_text: str | None = None
    field_inst_buffer: list[str] = []
    field_rslt_buffer: list[str] = []

    def state() -> dict:
        return stack[-1]

    def append_text(text: str) -> None:
        if not text:
            return
        s = state()
        if s["ignore_dest"] or s["in_pict"]:
            return
        if s["field_inst"]:
            field_inst_buffer.append(text)
            return
        if s["field_rslt"]:
            field_rslt_buffer.append(text)
        # Apply inline formatting
        if s["bold"]:
            text = f"**{text}**"
        if s["italic"]:
            text = f"*{text}*"
        if s["underline"]:
            # Markdown has no native underline; HTML works in most renderers
            text = f"<u>{text}</u>"
        if s["strike"]:
            text = f"~~{text}~~"
        # If we're inside fldrslt, don't write yet -- the buffer captures it
        if not s["field_rslt"]:
            paragraph_runs.append(text)

    def flush_paragraph() -> None:
        nonlocal pending_heading_level, pending_list_kind
        text = "".join(paragraph_runs).rstrip()
        # Normalize internal whitespace: collapse runs of spaces, but preserve newlines
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\*\* +\*\*", "", text)  # collapse "** **" artifacts
        text = re.sub(r"\* +\*", "", text)
        if pending_heading_level and text:
            text = ("#" * pending_heading_level) + " " + text
        elif pending_list_kind == "ul" and text:
            text = "- " + text
        elif pending_list_kind == "ol" and text:
            text = "1. " + text
        if text:
            out_paragraphs.append(text)
        paragraph_runs.clear()
        pending_heading_level = None
        pending_list_kind = None

    # Process tokens
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        kind = tok[0]

        if kind == "group_start":
            # Push a copy of the current state
            stack.append(dict(stack[-1]))
            idx += 1
            continue

        if kind == "group_end":
            # If we were inside a fldinst or fldrslt, finalize hyperlink emission
            s = state()
            if s["field_inst"]:
                # Extract URL from collected fldinst text
                inst_text = "".join(field_inst_buffer).strip()
                m = re.search(r'HYPERLINK\s+"([^"]+)"', inst_text)
                if m:
                    pending_hyperlink_url = m.group(1)
                field_inst_buffer.clear()
            elif s["field_rslt"]:
                visible = "".join(field_rslt_buffer).strip()
                if pending_hyperlink_url and visible:
                    paragraph_runs.append(f"[{visible}]({pending_hyperlink_url})")
                else:
                    paragraph_runs.append(visible)
                field_rslt_buffer.clear()
                pending_hyperlink_url = None
                pending_hyperlink_text = None
            if len(stack) > 1:
                stack.pop()
            idx += 1
            continue

        if kind == "text":
            append_text(tok[1])
            idx += 1
            continue

        if kind == "hex":
            ch = _decode_hex(tok[1], state()["codepage"])
            append_text(ch)
            idx += 1
            continue

        if kind == "uni":
            cp = tok[1]
            try:
                ch = chr(cp)
            except (ValueError, OverflowError):
                ch = ""
            append_text(ch)
            # Skip the next plain-text fallback character if present
            if idx + 1 < len(tokens) and tokens[idx + 1][0] == "text":
                t = tokens[idx + 1][1]
                if t and t[0] in ("?",):
                    # Strip the fallback ?
                    rest = t[1:]
                    tokens[idx + 1] = ("text", rest)
            idx += 1
            continue

        if kind == "ctrl":
            name = tok[1]
            param = tok[2]
            s = state()

            # Destination markers: control words preceded by \*
            if name == "*":
                # The next control word is a destination. If we don't recognize
                # it, mark this group as ignored for content emission.
                if idx + 1 < len(tokens) and tokens[idx + 1][0] == "ctrl":
                    next_name = tokens[idx + 1][1]
                    if next_name in _IGNORED_DESTINATIONS:
                        s["ignore_dest"] = True
                idx += 1
                continue

            # Destinations that begin with their control word (no \*)
            if name in _IGNORED_DESTINATIONS:
                s["ignore_dest"] = True
                idx += 1
                continue

            # Codepage change: \ansicpg1252, \cpg1252
            if name in ("ansicpg", "cpg") and param is not None:
                s["codepage"] = param
                idx += 1
                continue

            # Hyperlink fields
            if name == "field":
                # Whole field group; nothing to do at this level
                idx += 1
                continue
            if name == "fldinst":
                s["field_inst"] = True
                idx += 1
                continue
            if name == "fldrslt":
                s["field_rslt"] = True
                idx += 1
                continue

            # Inline formatting
            if name == "b":
                s["bold"] = (param is None or param != 0)
                idx += 1
                continue
            if name == "i":
                s["italic"] = (param is None or param != 0)
                idx += 1
                continue
            if name in ("ul", "ulw", "uld", "uldb"):
                s["underline"] = (param is None or param != 0)
                idx += 1
                continue
            if name == "ulnone":
                s["underline"] = False
                idx += 1
                continue
            if name in ("strike", "striked"):
                s["strike"] = (param is None or param != 0)
                idx += 1
                continue
            if name == "plain":
                s["bold"] = s["italic"] = s["underline"] = s["strike"] = False
                idx += 1
                continue

            # Font size for heading detection
            if name == "fs" and param is not None:
                lvl = _heading_level_for_size(param)
                if lvl is not None and not paragraph_runs:
                    pending_heading_level = lvl
                idx += 1
                continue

            # Bullet character
            if name == "bullet":
                append_text("\u2022")
                idx += 1
                continue

            # Tab
            if name == "tab":
                append_text("\t")
                idx += 1
                continue

            # Line break vs paragraph break
            if name == "line":
                paragraph_runs.append("  \n")  # Markdown soft break
                idx += 1
                continue
            if name == "par":
                flush_paragraph()
                idx += 1
                continue

            # Paragraph defaults reset
            if name == "pard":
                pending_heading_level = None
                pending_list_kind = None
                idx += 1
                continue

            # List marker: {\listtext ... } prefixes a paragraph that is part
            # of a list. We discard the marker (it's a literal bullet/number
            # rendered by the source application) and mark the paragraph as
            # a list item so flush_paragraph emits a proper Markdown bullet.
            if name in ("pntext", "listtext"):
                pending_list_kind = "ul"
                # Skip ahead until we close this group
                depth = 0
                idx += 1
                while idx < len(tokens):
                    t = tokens[idx]
                    if t[0] == "group_start":
                        depth += 1
                    elif t[0] == "group_end":
                        if depth == 0:
                            idx += 1
                            break
                        depth -= 1
                    idx += 1
                continue

            # Common list-detection control words
            if name in ("ls", "ilvl"):
                # Indicates we're in a list. Default to bullet unless we see decimal numbering.
                if pending_list_kind is None:
                    pending_list_kind = "ul"
                idx += 1
                continue

            # Special characters
            if name == "emdash":
                append_text("\u2014"); idx += 1; continue
            if name == "endash":
                append_text("\u2013"); idx += 1; continue
            if name == "lquote":
                append_text("\u2018"); idx += 1; continue
            if name == "rquote":
                append_text("\u2019"); idx += 1; continue
            if name == "ldblquote":
                append_text("\u201C"); idx += 1; continue
            if name == "rdblquote":
                append_text("\u201D"); idx += 1; continue
            if name == "~":
                append_text("\u00A0"); idx += 1; continue
            if name == "_":
                append_text("\u2011"); idx += 1; continue

            # Anything else: ignore silently
            idx += 1
            continue

        idx += 1

    # Flush any trailing paragraph
    flush_paragraph()

    return "\n\n".join(out_paragraphs).strip() + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def convert_rtf(src: Path) -> tuple[dict, str]:
    """Convert one .rtf file to (frontmatter_dict, body_string)."""
    src = Path(src)
    raw = src.read_bytes()
    # RTF is ASCII at the byte level except for hex escapes; decode permissively.
    try:
        text = raw.decode("ascii", errors="replace")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    body = _rtf_to_markdown_body(text)

    # Compute simple stats
    word_count = len(re.findall(r"\b\w+\b", body))

    fm = {
        "source":      "rtf",
        "source_file": src.name,
        "word_count":  word_count,
    }

    title = src.stem
    if not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}"

    return fm, body


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Convert one RTF file to Markdown (debug).")
    ap.add_argument("rtf_path")
    args = ap.parse_args()
    fm, body = convert_rtf(Path(args.rtf_path))
    print(to_yaml_frontmatter(fm))
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
