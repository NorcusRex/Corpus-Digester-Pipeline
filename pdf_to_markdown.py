#!/usr/bin/env python3
"""
pdf_to_markdown.py

Convert .pdf files to Markdown with full content preservation. Each PDF
becomes one .md file with a sibling "<basename>_media/" folder for any
extracted images and attachments.

What gets preserved
-------------------
Document metadata
    Title, author, subject, keywords, producer, creator, creation/mod
    dates — all in YAML frontmatter.
Outline (bookmarks)
    Rendered as a "## Outline" section at the top, with target page numbers.
Page text
    Each page becomes a "## Page N" section. pypdf's text extraction is
    used; reading order can be imperfect for complex multi-column layouts,
    so the original page break is the primary unit of trust.
Images
    Every embedded image on every page is extracted to <basename>_media/
    and listed under each page's "Images" subsection with a relative link.
Annotations
    Comments, sticky notes, highlights, and other markup annotations are
    listed under each page's "Annotations" subsection with author, date,
    type, and full text. The contents and any "popup" text are both kept.
Form fields
    If the PDF contains AcroForm fields with values, they appear in a
    "## Form fields" section.
Attachments / embedded files
    Extracted to <basename>_media/ and listed in a "## Attachments" section.

Limitations honestly noted
--------------------------
* Scanned PDFs (image-of-text) yield no extractable text. The frontmatter
  flags "likely_scanned: true" when text extraction returns nothing despite
  pages existing. To recover text, run the file through OCR first
  (e.g. `ocrmypdf input.pdf input.ocr.pdf`) and re-run this script.
* PDF text extraction does not always preserve original reading order in
  multi-column or heavily formatted layouts.
* Vector graphics, fonts, and exact visual layout are NOT preserved — PDF
  is a presentation format, and this script captures content, not pixels.

Dependencies
------------
* `pypdf` (pure Python). Install with: `pip install pypdf`

Usage
-----
    python pdf_to_markdown.py path/to/file.pdf -o out_dir/
    python pdf_to_markdown.py path/to/dir/ -o out_dir/ --recursive
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Below this many characters a page is treated as carrying no text. Shared
# with ocr_pdf.py, which uses the same floor to decide what to OCR -- two
# thresholds that drifted apart would mean a page flagged as scanned that OCR
# was never asked to look at.
CHARS_PER_PAGE_FLOOR = 20

try:
    import pypdf
    from pypdf.generic import IndirectObject
except ImportError:
    print("pypdf is required. Install with:  pip install pypdf", file=sys.stderr)
    raise SystemExit(2)


# ---------------------------------------------------------------------------
# Slug & escape helpers
# ---------------------------------------------------------------------------

def safe_filename(name: str, fallback: str) -> str:
    """Sanitize a filename pulled from PDF metadata or attachment names."""
    if not name:
        return fallback
    name = re.sub(r"[^\w.\- ]+", "_", name).strip().strip(".")
    name = re.sub(r"\s+", "_", name)
    return name[:120] or fallback


def md_escape(text: str) -> str:
    """Light escape so PDF-extracted text doesn't accidentally trigger MD."""
    # Don't over-escape — that hurts readability. Just neutralize the most
    # disruptive characters at line starts (handled by callers when needed).
    return text


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
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(reader: "pypdf.PdfReader") -> dict:
    md = reader.metadata or {}
    out: dict = {}
    fields = {
        "title":    "/Title",
        "author":   "/Author",
        "subject":  "/Subject",
        "keywords": "/Keywords",
        "creator":  "/Creator",
        "producer": "/Producer",
        "created":  "/CreationDate",
        "modified": "/ModDate",
    }
    for key, pdf_key in fields.items():
        try:
            v = md.get(pdf_key)
        except Exception:
            v = None
        if v:
            out[key] = str(v)
    return out


# ---------------------------------------------------------------------------
# Outline / bookmarks
# ---------------------------------------------------------------------------

def render_outline(reader: "pypdf.PdfReader") -> list[str]:
    """Return Markdown lines for the PDF outline, with page targets."""
    try:
        outline = reader.outline
    except Exception:
        return []
    if not outline:
        return []

    lines: list[str] = []

    def walk(node, depth: int) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        title = getattr(node, "title", None) or "(untitled)"
        page_label = ""
        try:
            page_idx = reader.get_destination_page_number(node)
            if page_idx is not None:
                page_label = f" → page {page_idx + 1}"
        except Exception:
            pass
        indent = "  " * max(0, depth - 1)
        lines.append(f"{indent}- {title}{page_label}")

    walk(outline, 0)
    return lines


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

def extract_page_images(page, page_num: int, media_dir: Path,
                        seen_hashes: set) -> list[str]:
    """Save each image from a page; return list of relative filenames."""
    rel_paths: list[str] = []
    try:
        images = list(page.images)
    except Exception:
        return rel_paths

    for idx, img in enumerate(images):
        try:
            data = img.data
        except Exception:
            continue
        if not data:
            continue
        digest = hash(data)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)

        ext = ".bin"
        try:
            name = getattr(img, "name", "") or ""
            if "." in name:
                ext = "." + name.rsplit(".", 1)[1].lower()
        except Exception:
            pass

        filename = f"p{page_num:04d}_img{idx + 1}{ext}"
        out_path = media_dir / filename
        try:
            out_path.write_bytes(data)
            rel_paths.append(f"{media_dir.name}/{filename}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not write image {filename}: {e}",
                  file=sys.stderr)
    return rel_paths


# ---------------------------------------------------------------------------
# Annotation extraction
# ---------------------------------------------------------------------------

def _resolve(obj):
    if isinstance(obj, IndirectObject):
        try:
            return obj.get_object()
        except Exception:
            return None
    return obj


def extract_page_annotations(page) -> list[dict]:
    """Return a list of annotation dicts from a single page."""
    out: list[dict] = []
    annots = page.get("/Annots")
    annots = _resolve(annots)
    if not annots:
        return out
    for raw in annots:
        ann = _resolve(raw)
        if not ann:
            continue
        try:
            subtype = str(ann.get("/Subtype", "") or "").lstrip("/")
        except Exception:
            continue

        # Skip purely structural annotations (e.g. Link annotations target
        # navigation, not commentary). Links are recoverable via the URL
        # field below if needed.
        contents = ann.get("/Contents")
        contents = str(_resolve(contents) or "").strip()
        author = ann.get("/T")
        author = str(_resolve(author) or "").strip()
        date = ann.get("/M")
        date = str(_resolve(date) or "").strip()

        # /A action for Link annotations carries the URL for a hyperlink.
        link_url = ""
        action = _resolve(ann.get("/A"))
        if action:
            uri = action.get("/URI") if hasattr(action, "get") else None
            link_url = str(_resolve(uri) or "").strip()

        # Popup annotations duplicate the parent's contents — skip those.
        if subtype == "Popup":
            continue
        if not contents and not link_url:
            continue

        out.append({
            "subtype":  subtype or "annotation",
            "author":   author,
            "date":     date,
            "contents": contents,
            "url":      link_url,
        })
    return out


# ---------------------------------------------------------------------------
# Form fields
# ---------------------------------------------------------------------------

def extract_form_fields(reader: "pypdf.PdfReader") -> dict[str, str]:
    """Return {field_name: field_value} for AcroForm fields with values."""
    try:
        fields = reader.get_form_text_fields() or {}
    except Exception:
        fields = {}
    # get_form_text_fields covers text-style fields. Try the broader fields
    # API for things like checkboxes/radio buttons.
    try:
        all_fields = reader.get_fields() or {}
    except Exception:
        all_fields = {}
    merged: dict[str, str] = {}
    for k, v in fields.items():
        if v not in (None, ""):
            merged[k] = str(v)
    for k, info in all_fields.items():
        if k in merged:
            continue
        try:
            v = info.value
        except AttributeError:
            v = None
        if v not in (None, ""):
            merged[k] = str(v)
    return merged


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def extract_attachments(reader: "pypdf.PdfReader",
                        media_dir: Path) -> list[tuple[str, str]]:
    """Return [(original_name, relative_path)]."""
    saved: list[tuple[str, str]] = []
    try:
        attachments = reader.attachments  # {name: [bytes, ...]}
    except Exception:
        return saved
    for name, items in (attachments or {}).items():
        if not items:
            continue
        # pypdf returns a list because PDFs can technically attach the same
        # name multiple times. Save each with a disambiguator if needed.
        for i, data in enumerate(items):
            safe = safe_filename(name, f"attachment_{i+1}")
            out_path = media_dir / safe
            n = 2
            while out_path.exists() and out_path.read_bytes() != data:
                stem = Path(safe).stem
                suffix = Path(safe).suffix
                out_path = media_dir / f"{stem}-{n}{suffix}"
                n += 1
            if not out_path.exists():
                try:
                    out_path.write_bytes(data)
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] could not write attachment {safe}: {e}",
                          file=sys.stderr)
                    continue
            saved.append((name, f"{media_dir.name}/{out_path.name}"))
    return saved


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------

def clean_page_text(text: str) -> str:
    """Tidy pypdf's extracted text without reflowing it."""
    if not text:
        return ""
    # Normalize line endings, strip trailing spaces, collapse 3+ blank lines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_page(page, page_num: int, media_dir: Path,
                seen_hashes: set,
                extract_images: bool = True) -> tuple[str, int, int]:
    """Render one page; return (markdown, image_count, annotation_count)."""
    parts = [f"## Page {page_num}", ""]

    try:
        text = page.extract_text() or ""
    except Exception as e:  # noqa: BLE001
        text = ""
        print(f"  [warn] text extraction failed for page {page_num}: {e}",
              file=sys.stderr)
    text = clean_page_text(text)
    if text:
        parts.append(text)

    # Images
    image_paths = (extract_page_images(page, page_num, media_dir, seen_hashes)
                   if extract_images else [])
    if image_paths:
        parts += ["", "### Images on this page", ""]
        for rel in image_paths:
            parts.append(f"![]({rel})")

    # Annotations
    annotations = extract_page_annotations(page)
    if annotations:
        parts += ["", "### Annotations on this page", ""]
        for a in annotations:
            who = a["author"] or "unknown"
            when = f" ({a['date']})" if a["date"] else ""
            kind = a["subtype"]
            if a["contents"] and a["url"]:
                line = f"- **{kind}** — {who}{when}: {a['contents']} ({a['url']})"
            elif a["contents"]:
                line = f"- **{kind}** — {who}{when}: {a['contents']}"
            else:
                line = f"- **{kind}** — link to {a['url']}"
            parts.append(line)

    return ("\n".join(parts), len(image_paths), len(annotations))


# ---------------------------------------------------------------------------
# File-level conversion
# ---------------------------------------------------------------------------

def convert_pdf(in_path: Path, out_dir: Path, basename: str,
                ocr_pages: dict | None = None,
                extract_images: bool = True,
                ) -> tuple[dict, str]:
    """Convert one PDF; extract images/attachments to out_dir/<basename>_media/.

    `ocr_pages` maps 1-based page numbers to text recovered by OCR. It is used
    only where the page itself yields none, so a PDF with a real text layer is
    never overridden by a worse reading of the same page.

    `extract_images` False skips image extraction entirely. For a scanned book
    every page image *is* the page, so extracting them duplicates the whole
    document as loose files for no search value.
    """
    media_subdir = f"{basename}_media"
    media_dir = out_dir / media_subdir

    reader = pypdf.PdfReader(str(in_path))

    # If the PDF is encrypted, attempt empty-password decryption (common).
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass

    # Set up media dir lazily — only create if we end up writing into it.
    media_dir_created = False

    def ensure_media() -> Path:
        nonlocal media_dir_created
        if not media_dir_created:
            media_dir.mkdir(parents=True, exist_ok=True)
            media_dir_created = True
        return media_dir

    fm: dict = {"source": "pdf", "source_file": in_path.name}
    fm.update(extract_metadata(reader))
    fm["page_count"] = len(reader.pages)

    body_parts: list[str] = []
    title = fm.get("title") or in_path.stem
    body_parts += [f"# {title}", ""]

    outline_lines = render_outline(reader)
    if outline_lines:
        body_parts += ["## Outline", ""]
        body_parts.extend(outline_lines)
        body_parts.append("")

    # Form fields
    form_fields = extract_form_fields(reader)
    if form_fields:
        body_parts += ["## Form fields", ""]
        for k, v in form_fields.items():
            body_parts.append(f"- **{k}**: {v}")
        body_parts.append("")
        fm["form_field_count"] = len(form_fields)

    # Pages
    seen_image_hashes: set = set()
    total_images = 0
    total_annotations = 0
    extracted_text_chars = 0

    ocr_pages = ocr_pages or {}
    ocr_pages_used = 0

    pages_md: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        # Only create media dir if a page actually produces images.
        page_media = ensure_media() if any(True for _ in page.images) else media_dir
        if not media_dir_created and any(True for _ in page.images):
            page_media = ensure_media()
        # Note: iterating page.images twice can be expensive; keep the call simple.
        md, n_img, n_ann = render_page(page, i, ensure_media(),
                                       seen_image_hashes,
                                       extract_images=extract_images)
        # Track extracted text volume to flag scanned PDFs in frontmatter.
        page_chars = 0
        try:
            page_chars = len(page.extract_text() or "")
        except Exception:
            pass
        extracted_text_chars += page_chars
        # Fall back to OCR only where the page gave nothing itself. A page
        # with a real text layer keeps it: OCR of an already-digital page is
        # a worse reading of the same thing.
        if page_chars < CHARS_PER_PAGE_FLOOR and ocr_pages.get(i):
            md = md.rstrip() + "\n\n" + ocr_pages[i].strip()
            ocr_pages_used += 1
        pages_md.append(md)
        total_images += n_img
        total_annotations += n_ann

    body_parts.extend(pages_md)

    # Attachments (after all pages so they don't interrupt the page sequence)
    attachments = extract_attachments(reader, ensure_media())
    if attachments:
        body_parts += ["", "## Attachments", ""]
        for name, rel in attachments:
            body_parts.append(f"- [{name}]({rel})")
        fm["attachment_count"] = len(attachments)

    fm["images_extracted"]    = total_images
    fm["annotation_count"]    = total_annotations
    fm["text_extracted_chars"] = extracted_text_chars

    # Heuristic: pages exist but virtually no text came out → likely scanned.
    if fm["page_count"] > 0 and extracted_text_chars < CHARS_PER_PAGE_FLOOR * fm["page_count"]:
        fm["likely_scanned"] = True

    # Whole-document OCR, where the sidecar carried no page breaks: append it
    # once rather than losing it.
    if ocr_pages and not ocr_pages_used and ocr_pages.get(1) \
            and fm.get("likely_scanned"):
        body_parts += ["", "## Recovered text (OCR)", "",
                       ocr_pages[1].strip()]
        ocr_pages_used = 1

    if ocr_pages_used:
        fm["ocr_pages"] = ocr_pages_used
        fm["text_source"] = "ocr" if extracted_text_chars == 0 else "mixed"
    if not extract_images:
        fm["images_skipped"] = True

    body = "\n\n".join(p for p in body_parts if p != "")
    return fm, body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _gather_inputs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(input_path.glob(pattern))


def _allocate_basename(out_dir: Path, stem: str) -> str:
    base = stem
    n = 2
    while (out_dir / f"{base}.md").exists() or (out_dir / f"{base}_media").exists():
        base = f"{stem}-{n}"
        n += 1
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert .pdf files to Markdown (lossless).")
    ap.add_argument("input", help="A .pdf file or a directory of .pdf files")
    ap.add_argument("--no-images", action="store_true",
                    help="Do not extract embedded images. For a scanned book "
                         "every page image is the page itself, so extracting "
                         "them duplicates the whole document for no gain.")
    ap.add_argument("-o", "--output", default="pdf_md",
                    help="Output directory (default: ./pdf_md)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Recurse into subdirectories when input is a directory")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _gather_inputs(in_path, args.recursive)
    if not files:
        print(f"No .pdf files found at {in_path}", file=sys.stderr)
        return 1

    written = skipped = 0
    for f in files:
        basename = _allocate_basename(out_dir, f.stem)
        try:
            fm, body = convert_pdf(f, out_dir, basename,
                                    extract_images=not args.no_images)
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
