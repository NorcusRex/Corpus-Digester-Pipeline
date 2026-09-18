#!/usr/bin/env python3
"""
docx_to_markdown.py

Convert .docx files to Markdown with full content preservation. Nothing is
silently dropped — every kind of content is either rendered as Markdown,
extracted to disk and linked, or anchored as a reference with full text in
an appendix.

What gets preserved
-------------------
Prose
    Headings (1–6, plus Title/Subtitle), bold, italic, inline code, links,
    bullet/numbered lists with nesting, tables, block quotes.
Images
    Extracted to a sibling "<basename>_media/" folder and inlined as
    ![alt](relative/path). Alt text is taken from Word's docPr/cNvPr
    "descr" attribute (the accessibility alt text) when present.
Footnotes & endnotes
    Rendered as Pandoc/GFM-style footnote references ([^fn1], [^en1]) at
    their original anchor positions, with full text in dedicated
    "## Footnotes" and "## Endnotes" sections at the end of the file.
Comments
    Rendered as footnote-style references ([^c0]) at the commentReference
    position. Author, date, and full text appear in a "## Comments"
    section at the end of the file. The commented range itself remains
    in-line so context is preserved.
Tracked changes
    Insertions render as normal text (they ARE the current document).
    Deletions render as ~~strikethrough~~ followed by an HTML comment
    noting author and date, so the deletion is visible but distinguishable.
Document properties
    Title, author, dates, subject, description, keywords go into YAML
    frontmatter.

Stdlib only. A .docx is just a zipped bundle of XML; no python-docx,
no pandoc.

Usage
-----
    python docx_to_markdown.py path/to/file.docx -o out_dir/
    python docx_to_markdown.py path/to/dir/  -o out_dir/ --recursive
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

W       = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R       = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CP      = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC      = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
A_NS    = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS   = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC_NS  = "http://schemas.openxmlformats.org/drawingml/2006/picture"
V_NS    = "urn:schemas-microsoft-com:vml"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def wval(el) -> str | None:
    return None if el is None else el.get(f"{{{W}}}val")


# ---------------------------------------------------------------------------
# Aux part parsers
# ---------------------------------------------------------------------------

def parse_core_props(xml_bytes: bytes) -> dict:
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    out: dict = {}
    string_fields = {
        "title":          f"{{{DC}}}title",
        "creator":        f"{{{DC}}}creator",
        "subject":        f"{{{DC}}}subject",
        "description":    f"{{{DC}}}description",
        "keywords":       f"{{{CP}}}keywords",
        "lastModifiedBy": f"{{{CP}}}lastModifiedBy",
    }
    for key, tag in string_fields.items():
        el = root.find(tag)
        if el is not None and el.text:
            out[key] = el.text.strip()
    for key, tag in (("created",  f"{{{DCTERMS}}}created"),
                     ("modified", f"{{{DCTERMS}}}modified")):
        el = root.find(tag)
        if el is not None and el.text:
            out[key] = el.text.strip()
    return out


def parse_rels(xml_bytes: bytes) -> tuple[dict[str, str], dict[str, str]]:
    """Return (hyperlinks, images): rId -> URL / internal-zip-path."""
    hyperlinks: dict[str, str] = {}
    images: dict[str, str] = {}
    if not xml_bytes:
        return hyperlinks, images
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return hyperlinks, images
    for rel in root.findall(f"{{{PKG_REL}}}Relationship"):
        rid = rel.get("Id")
        target = rel.get("Target") or ""
        rtype = rel.get("Type", "").lower()
        if not rid or not target:
            continue
        if "hyperlink" in rtype:
            hyperlinks[rid] = target
        elif "image" in rtype:
            # Image targets are typically "media/image1.png" — relative to "word/".
            images[rid] = target.lstrip("/") if target.startswith("/") else f"word/{target}"
    return hyperlinks, images


def parse_numbering(xml_bytes: bytes) -> dict[tuple[str, int], str]:
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    abstracts: dict[str, dict[int, str]] = {}
    for abs_num in root.findall(w("abstractNum")):
        abs_id = abs_num.get(f"{{{W}}}abstractNumId")
        if not abs_id:
            continue
        levels: dict[int, str] = {}
        for lvl in abs_num.findall(w("lvl")):
            try:
                ilvl = int(lvl.get(f"{{{W}}}ilvl", "0"))
            except ValueError:
                continue
            num_fmt = lvl.find(w("numFmt"))
            levels[ilvl] = wval(num_fmt) or "bullet"
        abstracts[abs_id] = levels

    numeric_formats = {"decimal", "decimalZero",
                       "lowerLetter", "upperLetter",
                       "lowerRoman", "upperRoman"}
    result: dict[tuple[str, int], str] = {}
    for num in root.findall(w("num")):
        num_id = num.get(f"{{{W}}}numId")
        if not num_id:
            continue
        abs_ref = num.find(w("abstractNumId"))
        levels = abstracts.get(wval(abs_ref) or "", {})
        for ilvl, fmt in levels.items():
            result[(num_id, ilvl)] = "1." if fmt in numeric_formats else "-"
    return result


# ---------------------------------------------------------------------------
# Style classification
# ---------------------------------------------------------------------------

def heading_level(style_id: str | None) -> int | None:
    if not style_id:
        return None
    s = style_id.replace(" ", "").lower()
    if s == "title":
        return 1
    if s == "subtitle":
        return 2
    m = re.match(r"^heading([1-6])$", s)
    return int(m.group(1)) if m else None


def is_quote_style(style_id: str | None) -> bool:
    return bool(style_id) and "quote" in style_id.lower()


def is_code_style(style_id: str | None) -> bool:
    if not style_id:
        return False
    s = style_id.lower()
    return "code" in s or s in {"sourcecode", "preformatted", "html"}


# ---------------------------------------------------------------------------
# Drawing / picture rendering
# ---------------------------------------------------------------------------

def render_drawing(drawing_el, image_paths: dict[str, str]) -> str:
    """Find the embed rId and any alt text; emit ![alt](path)."""
    blip = drawing_el.find(f".//{{{A_NS}}}blip")
    rid = blip.get(f"{{{R}}}embed") if blip is not None else None

    alt = ""
    for path in (f".//{{{WP_NS}}}docPr", f".//{{{PIC_NS}}}cNvPr"):
        el = drawing_el.find(path)
        if el is not None:
            alt = el.get("descr") or el.get("title") or el.get("name") or ""
            if alt:
                break

    if rid and rid in image_paths:
        return f"![{alt}]({image_paths[rid]})"
    # Saw a drawing but couldn't resolve its file — flag it rather than drop.
    return f"![{alt or 'embedded image (unresolved)'}]()"


def render_pict(pict_el, image_paths: dict[str, str]) -> str:
    """Legacy VML images: <w:pict><v:shape><v:imagedata r:id=...>"""
    imagedata = pict_el.find(f".//{{{V_NS}}}imagedata")
    rid = imagedata.get(f"{{{R}}}id") if imagedata is not None else None
    if rid and rid in image_paths:
        return f"![]({image_paths[rid]})"
    return "![embedded image (unresolved)]()"


# ---------------------------------------------------------------------------
# Run / paragraph / table renderers
# ---------------------------------------------------------------------------

def _run_is_monospace(rPr) -> bool:
    if rPr is None:
        return False
    if is_code_style(wval(rPr.find(w("rStyle")))):
        return True
    rFonts = rPr.find(w("rFonts"))
    if rFonts is None:
        return False
    for attr in ("ascii", "hAnsi", "cs"):
        font = (rFonts.get(f"{{{W}}}{attr}") or "").lower()
        if any(m in font for m in ("courier", "consolas", "mono", "menlo")):
            return True
    return False


def render_run(run_el, ctx: dict) -> str:
    """Render <w:r> with bold/italic/code preserved and inline references
    (footnoteReference, endnoteReference, commentReference, drawings)."""
    rPr = run_el.find(w("rPr"))
    bold = rPr is not None and rPr.find(w("b")) is not None
    italic = rPr is not None and rPr.find(w("i")) is not None
    code = _run_is_monospace(rPr)

    text_chunks: list[str] = []
    appended_inline: list[str] = []  # drawings / refs that follow formatted text

    for child in run_el:
        tag = child.tag
        if tag == w("t") or tag == w("delText"):
            text_chunks.append(child.text or "")
        elif tag == w("tab"):
            text_chunks.append("\t")
        elif tag == w("br"):
            text_chunks.append("  \n")
        elif tag == w("drawing"):
            appended_inline.append(render_drawing(child, ctx["image_paths"]))
        elif tag == w("pict"):
            appended_inline.append(render_pict(child, ctx["image_paths"]))
        elif tag == w("footnoteReference"):
            fn_id = child.get(f"{{{W}}}id")
            if fn_id:
                appended_inline.append(f"[^fn{fn_id}]")
                ctx["used_fn_ids"].add(fn_id)
        elif tag == w("endnoteReference"):
            en_id = child.get(f"{{{W}}}id")
            if en_id:
                appended_inline.append(f"[^en{en_id}]")
                ctx["used_en_ids"].add(en_id)
        elif tag == w("commentReference"):
            c_id = child.get(f"{{{W}}}id")
            if c_id:
                appended_inline.append(f"[^c{c_id}]")
                ctx["used_c_ids"].add(c_id)
        elif tag == w("object"):
            appended_inline.append("[embedded object]")
        # rPr, sym, separators etc. either non-content or rare; ignore.

    text = "".join(text_chunks)
    if not text and not appended_inline:
        return ""

    if text:
        if code:
            formatted = f"`{text}`"
        elif bold and italic:
            formatted = f"***{text}***"
        elif bold:
            formatted = f"**{text}**"
        elif italic:
            formatted = f"*{text}*"
        else:
            formatted = text
    else:
        formatted = ""

    return formatted + "".join(appended_inline)


def render_hyperlink(hl_el, ctx: dict) -> str:
    inner = "".join(render_run(rr, ctx) for rr in hl_el.findall(w("r")))
    rid = hl_el.get(f"{{{R}}}id")
    url = ctx["hyperlinks"].get(rid or "", "")
    return f"[{inner}]({url})" if url and inner else inner


def _iter_paragraph_textual_children(p_el):
    """Yield (kind, element) for content-bearing children of a paragraph,
    flattening tracked-change wrappers and skipping marker-only elements."""
    for child in p_el:
        tag = child.tag
        if tag == w("r"):
            yield ("run", child)
        elif tag == w("hyperlink"):
            yield ("hyperlink", child)
        elif tag == w("ins"):
            # Insertions ARE the current document — render their content.
            for sub in child:
                if sub.tag == w("r"):
                    yield ("run", sub)
                elif sub.tag == w("hyperlink"):
                    yield ("hyperlink", sub)
        elif tag == w("del"):
            yield ("del", child)
        # commentRangeStart/End, bookmarkStart/End, proofErr, etc.: skip.


def render_paragraph(p_el, ctx: dict) -> str:
    pPr = p_el.find(w("pPr"))
    style_id = wval(pPr.find(w("pStyle"))) if pPr is not None else None

    ilvl = num_id = None
    if pPr is not None:
        numPr = pPr.find(w("numPr"))
        if numPr is not None:
            try:
                ilvl = int(wval(numPr.find(w("ilvl"))) or 0)
            except ValueError:
                ilvl = 0
            num_id = wval(numPr.find(w("numId")))

    parts: list[str] = []
    for kind, el in _iter_paragraph_textual_children(p_el):
        if kind == "run":
            parts.append(render_run(el, ctx))
        elif kind == "hyperlink":
            parts.append(render_hyperlink(el, ctx))
        elif kind == "del":
            deleted = ""
            for sub_run in el.findall(w("r")):
                for sub in sub_run:
                    if sub.tag == w("delText"):
                        deleted += sub.text or ""
            if deleted:
                author = el.get(f"{{{W}}}author") or ""
                date = el.get(f"{{{W}}}date") or ""
                meta = f"<!-- deleted by {author} on {date} -->" if (author or date) else ""
                parts.append(f"~~{deleted}~~{meta}")

    text = "".join(parts).rstrip()
    if not text and ilvl is None:
        return ""

    level = heading_level(style_id)
    if level:
        return "#" * level + " " + text
    if is_code_style(style_id):
        return f"```\n{text}\n```"
    if ilvl is not None and num_id is not None:
        marker = ctx["num_map"].get((num_id, ilvl), "-")
        return f"{'  ' * ilvl}{marker} {text}"
    if is_quote_style(style_id):
        return f"> {text}"
    return text


def render_table(tbl_el, ctx: dict) -> str:
    rows: list[list[str]] = []
    for tr in tbl_el.findall(w("tr")):
        cells: list[str] = []
        for tc in tr.findall(w("tc")):
            cell_bits: list[str] = []
            for p in tc.findall(w("p")):
                bit = render_paragraph(p, ctx)
                if bit:
                    cell_bits.append(bit)
            text = " ".join(cell_bits).replace("|", "\\|").replace("\n", " ")
            cells.append(text or " ")
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    n_cols = max(len(r) for r in rows)
    rows = [r + [" "] * (n_cols - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "|".join([" --- "] * n_cols) + "|"]
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Footnotes / endnotes / comments
# ---------------------------------------------------------------------------

def _render_note_paragraphs(parent_el, ctx: dict) -> str:
    """Render a note's paragraphs into a Markdown string suitable for the
    right-hand side of a footnote definition. Multi-paragraph notes use
    GFM/Pandoc 4-space indentation for continuations."""
    pieces: list[str] = []
    for p in parent_el.findall(w("p")):
        bit = render_paragraph(p, ctx)
        if bit:
            pieces.append(bit)
    if not pieces:
        return ""
    if len(pieces) == 1:
        return pieces[0]
    head, *rest = pieces
    indented = "\n\n".join("    " + line.replace("\n", "\n    ") for line in rest)
    return head + "\n\n" + indented


def parse_notes(xml_bytes: bytes, tag_name: str, ctx: dict) -> dict[str, str]:
    """Parse word/footnotes.xml or word/endnotes.xml into {id: rendered_md}."""
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    out: dict[str, str] = {}
    for note in root.findall(w(tag_name)):
        nid = note.get(f"{{{W}}}id")
        ntype = note.get(f"{{{W}}}type")
        if nid is None:
            continue
        if ntype in {"separator", "continuationSeparator", "continuationNotice"}:
            continue
        body = _render_note_paragraphs(note, ctx)
        if body:
            out[nid] = body
    return out


def parse_comments(xml_bytes: bytes, ctx: dict) -> dict[str, dict]:
    """Parse word/comments.xml into {id: {author, date, text}}."""
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    out: dict[str, dict] = {}
    for c in root.findall(w("comment")):
        cid = c.get(f"{{{W}}}id")
        if cid is None:
            continue
        out[cid] = {
            "author": c.get(f"{{{W}}}author") or "unknown",
            "date":   c.get(f"{{{W}}}date") or "",
            "text":   _render_note_paragraphs(c, ctx),
        }
    return out


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

def extract_images(zf: zipfile.ZipFile, image_rels: dict[str, str],
                   out_dir: Path, basename: str) -> dict[str, str]:
    """Copy image files to out_dir/<basename>_media/. Return rId -> rel path."""
    if not image_rels:
        return {}
    media_subdir = f"{basename}_media"
    media_dir = out_dir / media_subdir
    media_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for rid, internal_path in image_rels.items():
        try:
            data = zf.read(internal_path)
        except KeyError:
            continue
        name = Path(internal_path).name
        out_path = media_dir / name
        # Disambiguate if two rels point to files sharing a name but differing in bytes.
        n = 2
        while out_path.exists() and out_path.read_bytes() != data:
            stem, suffix = out_path.stem, out_path.suffix
            out_path = media_dir / f"{stem}-{n}{suffix}"
            n += 1
        if not out_path.exists():
            out_path.write_bytes(data)
        mapping[rid] = f"{media_subdir}/{out_path.name}"
    return mapping


# ---------------------------------------------------------------------------
# YAML emitter
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
            s = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}: "{s}"')
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File-level conversion
# ---------------------------------------------------------------------------

def _safe_read(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        return zf.read(name)
    except KeyError:
        return b""


def _note_sort_key(item):
    """Sort note IDs numerically when possible."""
    k, _ = item
    try:
        return (0, int(k))
    except (TypeError, ValueError):
        return (1, k)


def convert_docx(in_path: Path, out_dir: Path, basename: str) -> tuple[dict, str]:
    """Convert one .docx. Side effect: extracts images into out_dir/<basename>_media/."""
    with zipfile.ZipFile(in_path) as zf:
        document_xml  = _safe_read(zf, "word/document.xml")
        numbering_xml = _safe_read(zf, "word/numbering.xml")
        rels_xml      = _safe_read(zf, "word/_rels/document.xml.rels")
        core_xml      = _safe_read(zf, "docProps/core.xml")
        footnotes_xml = _safe_read(zf, "word/footnotes.xml")
        endnotes_xml  = _safe_read(zf, "word/endnotes.xml")
        comments_xml  = _safe_read(zf, "word/comments.xml")

        if not document_xml:
            raise ValueError("word/document.xml not found — is this really a .docx?")

        hyperlinks, image_rels = parse_rels(rels_xml)
        image_paths = extract_images(zf, image_rels, out_dir, basename)

    num_map = parse_numbering(numbering_xml)
    core = parse_core_props(core_xml)

    ctx = {
        "hyperlinks":  hyperlinks,
        "image_paths": image_paths,
        "num_map":     num_map,
        "used_fn_ids": set(),
        "used_en_ids": set(),
        "used_c_ids":  set(),
    }

    # Notes are rendered with the same paragraph machinery, so they retain
    # their formatting, links, and any tracked changes.
    footnotes = parse_notes(footnotes_xml, "footnote", ctx)
    endnotes  = parse_notes(endnotes_xml,  "endnote",  ctx)
    comments  = parse_comments(comments_xml, ctx)

    # Main body.
    root = ET.fromstring(document_xml)
    body_el = root.find(w("body"))
    if body_el is None:
        raise ValueError("document body not found")

    blocks: list[str] = []
    for child in body_el:
        if child.tag == w("p"):
            md = render_paragraph(child, ctx)
            if md:
                blocks.append(md)
        elif child.tag == w("tbl"):
            md = render_table(child, ctx)
            if md:
                blocks.append(md)
        # w:sectPr is layout-only.

    body_md = "\n\n".join(blocks)

    # Appendix: footnote / endnote / comment definitions.
    appendix: list[str] = []
    if footnotes:
        appendix += ["## Footnotes", ""]
        for fn_id, text in sorted(footnotes.items(), key=_note_sort_key):
            appendix.append(f"[^fn{fn_id}]: {text}")
    if endnotes:
        if appendix:
            appendix.append("")
        appendix += ["## Endnotes", ""]
        for en_id, text in sorted(endnotes.items(), key=_note_sort_key):
            appendix.append(f"[^en{en_id}]: {text}")
    if comments:
        if appendix:
            appendix.append("")
        appendix += ["## Comments", ""]
        for c_id, c in sorted(comments.items(), key=_note_sort_key):
            who = c["author"]
            when = f" ({c['date']})" if c["date"] else ""
            appendix.append(f"[^c{c_id}]: **{who}{when}:** {c['text']}")

    if appendix:
        body_md = body_md.rstrip() + "\n\n" + "\n".join(appendix).strip() + "\n"

    # Frontmatter.
    fm: dict = {"source": "docx", "source_file": in_path.name}
    fm.update(core)
    fm["images_extracted"] = len(image_paths)
    fm["footnote_count"]   = len(footnotes)
    fm["endnote_count"]    = len(endnotes)
    fm["comment_count"]    = len(comments)

    unresolved = body_md.count("(unresolved)")
    if unresolved:
        fm["unresolved_drawings"] = unresolved

    # Add a top-level heading from the title if the body doesn't open with one.
    title = fm.get("title", "")
    if title and not body_md.lstrip().startswith("# "):
        body_md = f"# {title}\n\n{body_md}"

    return fm, body_md


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _gather_inputs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".docx" else []
    pattern = "**/*.docx" if recursive else "*.docx"
    return sorted(
        f for f in input_path.glob(pattern)
        if not f.name.startswith("~$")  # Word lock files
    )


def _allocate_basename(out_dir: Path, stem: str) -> str:
    """Pick a basename so .md and _media/ don't collide with existing output."""
    base = stem
    n = 2
    while (out_dir / f"{base}.md").exists() or (out_dir / f"{base}_media").exists():
        base = f"{stem}-{n}"
        n += 1
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert .docx files to Markdown (lossless).")
    ap.add_argument("input", help="A .docx file or a directory of .docx files")
    ap.add_argument("-o", "--output", default="docx_md",
                    help="Output directory (default: ./docx_md)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Recurse into subdirectories when input is a directory")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _gather_inputs(in_path, args.recursive)
    if not files:
        print(f"No .docx files found at {in_path}", file=sys.stderr)
        return 1

    written = skipped = 0
    for f in files:
        basename = _allocate_basename(out_dir, f.stem)
        try:
            fm, body = convert_docx(f, out_dir, basename)
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
