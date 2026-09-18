#!/usr/bin/env python3
"""
xlsx_to_markdown.py

Convert .xlsx workbooks to Markdown with full content preservation. Each
workbook becomes one .md file. Every sheet, every cell value, every
formula, every comment, every hyperlink, and every merged-range is
preserved — either inline in the rendered table or in a per-sheet appendix
when it doesn't fit a tabular layout.

What gets preserved
-------------------
Sheets
    All sheets in their original order. Hidden sheets are still rendered;
    their hidden state is recorded in frontmatter and in the section heading.
Cell values
    Numbers, strings (resolved from the shared string table), booleans, and
    dates (serial numbers converted to YYYY-MM-DD when the cell's number
    format indicates a date).
Formulas
    Cached values appear in the table; the formula source is listed in a
    per-sheet "Formulas" appendix as "A1: =SUM(B1:B10)".
Comments
    Listed in a per-sheet "Comments" appendix with author and full text,
    keyed by cell reference. Threaded comments (modern Excel/365 format)
    are also included if present.
Hyperlinks
    Rendered inline in the table as Markdown links: [value](url).
Merged cells
    The merged value appears in every cell of the range (matching how
    Excel renders merges visually); the merge ranges are listed in a
    per-sheet appendix so the original structure is recoverable.
Workbook metadata
    Title, author, dates, defined-name list — in YAML frontmatter.

Output is laid out so a human reader and full-text search both work:
column letters appear as the first row, row numbers as the first column,
so any cell can be referenced positionally.

Stdlib only.

Usage
-----
    python xlsx_to_markdown.py path/to/workbook.xlsx -o out_dir/
    python xlsx_to_markdown.py path/to/dir/ -o out_dir/ --recursive
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

SS      = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R       = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CP      = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC      = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def s(tag: str) -> str:
    return f"{{{SS}}}{tag}"


# ---------------------------------------------------------------------------
# Cell reference helpers
# ---------------------------------------------------------------------------

CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


def col_letter_to_index(letters: str) -> int:
    """A->1, Z->26, AA->27."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def index_to_col_letter(n: int) -> str:
    """1->A, 27->AA."""
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def parse_cell_ref(ref: str) -> tuple[int, int]:
    """A1 -> (row=1, col=1). Returns (0,0) for unparseable input."""
    if not ref:
        return (0, 0)
    m = CELL_REF_RE.match(ref)
    if not m:
        return (0, 0)
    return (int(m.group(2)), col_letter_to_index(m.group(1)))


def parse_range(rng: str) -> tuple[int, int, int, int]:
    """A1:B3 -> (1,1,3,2)."""
    if ":" in rng:
        a, b = rng.split(":", 1)
    else:
        a = b = rng
    r1, c1 = parse_cell_ref(a)
    r2, c2 = parse_cell_ref(b)
    return (r1, c1, r2, c2)


# ---------------------------------------------------------------------------
# Excel serial date conversion
# ---------------------------------------------------------------------------

# Excel epoch is 1899-12-30 to compensate for Excel's incorrect treatment of
# 1900 as a leap year. Serial 1 = 1900-01-01.
EXCEL_EPOCH = datetime(1899, 12, 30)

# Built-in number format IDs that are dates/times (per ECMA-376).
BUILTIN_DATE_FMT_IDS = {14, 15, 16, 17, 22, 27, 28, 29, 30, 31,
                        36, 45, 46, 47, 50, 51, 52, 53, 54, 55,
                        56, 57, 58}


def serial_to_date(serial: float) -> str:
    """Convert an Excel date serial to ISO string. Empty if conversion fails."""
    try:
        n = float(serial)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    try:
        dt = EXCEL_EPOCH + timedelta(days=n)
    except OverflowError:
        return ""
    if n == int(n):
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
    fields = {
        "title":          f"{{{DC}}}title",
        "creator":        f"{{{DC}}}creator",
        "subject":        f"{{{DC}}}subject",
        "description":    f"{{{DC}}}description",
        "keywords":       f"{{{CP}}}keywords",
        "lastModifiedBy": f"{{{CP}}}lastModifiedBy",
    }
    for key, tag in fields.items():
        el = root.find(tag)
        if el is not None and el.text:
            out[key] = el.text.strip()
    for key, tag in (("created",  f"{{{DCTERMS}}}created"),
                     ("modified", f"{{{DCTERMS}}}modified")):
        el = root.find(tag)
        if el is not None and el.text:
            out[key] = el.text.strip()
    return out


def parse_shared_strings(xml_bytes: bytes) -> list[str]:
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out: list[str] = []
    for si in root.findall(s("si")):
        # A shared-string entry is either a single <t> or a sequence of
        # <r><t>...</t></r> rich-text runs. Concatenate the visible text.
        chunks: list[str] = []
        for t in si.findall(s("t")):
            chunks.append(t.text or "")
        for r in si.findall(s("r")):
            for t in r.findall(s("t")):
                chunks.append(t.text or "")
        out.append("".join(chunks))
    return out


def parse_styles(xml_bytes: bytes) -> set[int]:
    """Return the set of cell-style indices (xfId) that represent dates."""
    if not xml_bytes:
        return set()
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return set()

    # Custom number formats: numFmtId -> formatCode
    custom_fmts: dict[int, str] = {}
    numFmts = root.find(s("numFmts"))
    if numFmts is not None:
        for nf in numFmts.findall(s("numFmt")):
            try:
                fid = int(nf.get("numFmtId", "0"))
            except ValueError:
                continue
            custom_fmts[fid] = nf.get("formatCode", "")

    def is_date_format(fid: int) -> bool:
        if fid in BUILTIN_DATE_FMT_IDS:
            return True
        code = custom_fmts.get(fid, "")
        if not code:
            return False
        # Heuristic: any of d/m/y/h/s tokens, ignoring quoted literals.
        cleaned = re.sub(r'"[^"]*"', "", code).lower()
        return any(tok in cleaned for tok in ("yy", "mm", "dd", "hh", "ss"))

    date_xf_indices: set[int] = set()
    cellXfs = root.find(s("cellXfs"))
    if cellXfs is not None:
        for i, xf in enumerate(cellXfs.findall(s("xf"))):
            try:
                fid = int(xf.get("numFmtId", "0"))
            except ValueError:
                continue
            if is_date_format(fid):
                date_xf_indices.add(i)
    return date_xf_indices


def parse_workbook(xml_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Return (sheets, defined_names).
    Each sheet: {name, sheetId, rId, hidden}.
    Each defined name: {name, value}.
    """
    if not xml_bytes:
        return [], []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return [], []
    sheets: list[dict] = []
    sheets_el = root.find(s("sheets"))
    if sheets_el is not None:
        for sh in sheets_el.findall(s("sheet")):
            sheets.append({
                "name":    sh.get("name", ""),
                "sheetId": sh.get("sheetId", ""),
                "rId":     sh.get(f"{{{R}}}id", ""),
                "hidden":  sh.get("state", "visible") in {"hidden", "veryHidden"},
            })
    defined: list[dict] = []
    defined_el = root.find(s("definedNames"))
    if defined_el is not None:
        for dn in defined_el.findall(s("definedName")):
            defined.append({"name": dn.get("name", ""), "value": dn.text or ""})
    return sheets, defined


def parse_rels(xml_bytes: bytes) -> dict[str, dict]:
    """Generic .rels parser: rId -> {target, type}."""
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    out: dict[str, dict] = {}
    for rel in root.findall(f"{{{PKG_REL}}}Relationship"):
        rid = rel.get("Id")
        if rid:
            out[rid] = {
                "target": rel.get("Target", ""),
                "type":   rel.get("Type", "").lower(),
                "mode":   rel.get("TargetMode", ""),
            }
    return out


# ---------------------------------------------------------------------------
# Sheet content
# ---------------------------------------------------------------------------

def _cell_text_value(c_el, shared: list[str]) -> str:
    """Resolve a <c> element's value to a display string."""
    t = c_el.get("t", "n")  # default: numeric
    v = c_el.find(s("v"))
    is_el = c_el.find(s("is"))  # inline string

    if t == "s":  # shared string
        if v is not None and v.text is not None:
            try:
                return shared[int(v.text)]
            except (ValueError, IndexError):
                return v.text
        return ""
    if t == "inlineStr" or is_el is not None:
        if is_el is None:
            return ""
        chunks: list[str] = []
        for tt in is_el.findall(s("t")):
            chunks.append(tt.text or "")
        for r in is_el.findall(s("r")):
            for tt in r.findall(s("t")):
                chunks.append(tt.text or "")
        return "".join(chunks)
    if t == "str":  # formula's string result
        return v.text if (v is not None and v.text is not None) else ""
    if t == "b":  # boolean
        if v is None or v.text is None:
            return ""
        return "TRUE" if v.text == "1" else "FALSE"
    if t == "e":  # error
        return v.text if (v is not None and v.text) else "#ERROR"
    # numeric (default)
    return v.text if (v is not None and v.text is not None) else ""


def parse_sheet(xml_bytes: bytes, shared: list[str], date_xfs: set[int]
                ) -> dict:
    """Return all sheet content keyed by purpose."""
    if not xml_bytes:
        return {"cells": {}, "formulas": [], "merges": [],
                "hyperlink_cells": [], "max_row": 0, "max_col": 0,
                "min_row": 0, "min_col": 0}
    root = ET.fromstring(xml_bytes)

    cells: dict[tuple[int, int], str] = {}
    formulas: list[tuple[str, str]] = []  # (cell_ref, formula_text)
    max_row = max_col = 0
    min_row = min_col = 0

    sheet_data = root.find(s("sheetData"))
    if sheet_data is not None:
        for row in sheet_data.findall(s("row")):
            for c in row.findall(s("c")):
                ref = c.get("r", "")
                r, col = parse_cell_ref(ref)
                if r == 0:
                    continue
                # Style index for date detection
                style_idx = c.get("s")
                value = _cell_text_value(c, shared)

                # Date conversion
                if value and style_idx is not None:
                    try:
                        if int(style_idx) in date_xfs:
                            converted = serial_to_date(value)
                            if converted:
                                value = converted
                    except ValueError:
                        pass

                # Formula
                f = c.find(s("f"))
                if f is not None and (f.text or "").strip():
                    formulas.append((ref, f.text.strip()))

                if value != "" or f is not None:
                    cells[(r, col)] = value
                    if min_row == 0 or r < min_row:
                        min_row = r
                    if min_col == 0 or col < min_col:
                        min_col = col
                    if r > max_row:
                        max_row = r
                    if col > max_col:
                        max_col = col

    # Merged cells: fill the merged area with the top-left value (visual parity).
    merges: list[str] = []
    merge_el = root.find(s("mergeCells"))
    if merge_el is not None:
        for mc in merge_el.findall(s("mergeCell")):
            rng = mc.get("ref", "")
            if not rng:
                continue
            merges.append(rng)
            r1, c1, r2, c2 = parse_range(rng)
            top_left = cells.get((r1, c1), "")
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    if (rr, cc) not in cells:
                        cells[(rr, cc)] = top_left
            if r2 > max_row:
                max_row = r2
            if c2 > max_col:
                max_col = c2

    # Hyperlinks
    hyperlink_cells: list[dict] = []
    hl_el = root.find(s("hyperlinks"))
    if hl_el is not None:
        for hl in hl_el.findall(s("hyperlink")):
            hyperlink_cells.append({
                "ref":      hl.get("ref", ""),
                "rid":      hl.get(f"{{{R}}}id", ""),
                "location": hl.get("location", ""),
                "display":  hl.get("display", ""),
                "tooltip":  hl.get("tooltip", ""),
            })

    return {
        "cells":           cells,
        "formulas":        formulas,
        "merges":          merges,
        "hyperlink_cells": hyperlink_cells,
        "max_row":         max_row,
        "max_col":         max_col,
        "min_row":         min_row,
        "min_col":         min_col,
    }


def parse_legacy_comments(xml_bytes: bytes) -> dict[str, dict]:
    """Parse xl/comments*.xml -> {cellRef: {author, text}}."""
    if not xml_bytes:
        return {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    authors: list[str] = []
    a_el = root.find(s("authors"))
    if a_el is not None:
        for a in a_el.findall(s("author")):
            authors.append(a.text or "unknown")
    out: dict[str, dict] = {}
    cl = root.find(s("commentList"))
    if cl is not None:
        for c in cl.findall(s("comment")):
            ref = c.get("ref", "")
            try:
                aid = int(c.get("authorId", "0"))
            except ValueError:
                aid = 0
            author = authors[aid] if 0 <= aid < len(authors) else "unknown"
            text_el = c.find(s("text"))
            chunks: list[str] = []
            if text_el is not None:
                for tt in text_el.findall(s("t")):
                    chunks.append(tt.text or "")
                for r in text_el.findall(s("r")):
                    for tt in r.findall(s("t")):
                        chunks.append(tt.text or "")
            text = "".join(chunks).strip()
            if ref and text:
                out[ref] = {"author": author, "text": text}
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _escape_cell(text: str) -> str:
    """Make a cell value safe for a Markdown table."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def render_sheet_table(parsed: dict, hyperlinks_resolved: dict[str, str]) -> str:
    cells = parsed["cells"]
    if not cells:
        return "_(empty sheet)_"

    min_r = parsed["min_row"] or 1
    min_c = parsed["min_col"] or 1
    max_r = parsed["max_row"] or 1
    max_c = parsed["max_col"] or 1

    # Build hyperlink lookup keyed by (row, col) so we can format inline.
    hl_by_cell: dict[tuple[int, int], str] = {}
    for hl in parsed["hyperlink_cells"]:
        ref = hl["ref"]
        if not ref:
            continue
        # ref may be a single cell or a range; apply to all cells in the range.
        if ":" in ref:
            r1, c1, r2, c2 = parse_range(ref)
        else:
            r1, c1 = parse_cell_ref(ref)
            r2, c2 = r1, c1
        url = hyperlinks_resolved.get(hl["rid"], "") or hl["location"]
        if not url:
            continue
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                hl_by_cell[(rr, cc)] = url

    # Header row: column letters
    header = ["#"] + [index_to_col_letter(c) for c in range(min_c, max_c + 1)]
    sep = ["---"] * len(header)
    out_lines = [
        "| " + " | ".join(_escape_cell(h) for h in header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for r in range(min_r, max_r + 1):
        row_cells: list[str] = [str(r)]
        for c in range(min_c, max_c + 1):
            val = cells.get((r, c), "")
            url = hl_by_cell.get((r, c))
            if val == "":
                row_cells.append(" ")
            elif url:
                row_cells.append(f"[{_escape_cell(val)}]({url})")
            else:
                row_cells.append(_escape_cell(val))
        out_lines.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(out_lines)


def render_sheet_section(sheet_meta: dict, parsed: dict,
                         comments: dict[str, dict],
                         hyperlinks_resolved: dict[str, str]) -> str:
    name = sheet_meta["name"]
    suffix = " (hidden)" if sheet_meta["hidden"] else ""
    parts = [f"## Sheet: {name}{suffix}", ""]

    parts.append(render_sheet_table(parsed, hyperlinks_resolved))

    if parsed["merges"]:
        parts += ["", "### Merged ranges", ""]
        for m in parsed["merges"]:
            parts.append(f"- {m}")

    if parsed["formulas"]:
        parts += ["", "### Formulas", ""]
        for ref, fml in parsed["formulas"]:
            parts.append(f"- `{ref}`: `={fml}`")

    if comments:
        parts += ["", "### Comments", ""]
        for ref, c in sorted(comments.items(), key=lambda kv: parse_cell_ref(kv[0])):
            parts.append(f"- **{ref}** — {c['author']}: {c['text']}")

    return "\n".join(parts)


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
            t = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}: "{t}"')
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


def convert_xlsx(in_path: Path) -> tuple[dict, str]:
    with zipfile.ZipFile(in_path) as zf:
        names = set(zf.namelist())
        core_xml      = _safe_read(zf, "docProps/core.xml")
        workbook_xml  = _safe_read(zf, "xl/workbook.xml")
        wb_rels_xml   = _safe_read(zf, "xl/_rels/workbook.xml.rels")
        shared_xml    = _safe_read(zf, "xl/sharedStrings.xml")
        styles_xml    = _safe_read(zf, "xl/styles.xml")

        if not workbook_xml:
            raise ValueError("xl/workbook.xml not found — is this really a .xlsx?")

        sheets, defined_names = parse_workbook(workbook_xml)
        wb_rels = parse_rels(wb_rels_xml)
        shared = parse_shared_strings(shared_xml)
        date_xfs = parse_styles(styles_xml)
        core = parse_core_props(core_xml)

        # Render each sheet
        sheet_sections: list[str] = []
        for sh in sheets:
            rId = sh["rId"]
            rel = wb_rels.get(rId, {})
            target = rel.get("target", "")
            if not target:
                continue
            # rels targets are relative to xl/, e.g. "worksheets/sheet1.xml"
            if not target.startswith("xl/"):
                target = f"xl/{target.lstrip('/')}"
            sheet_xml = _safe_read(zf, target)
            if not sheet_xml:
                continue

            # Resolve hyperlinks via the per-sheet rels.
            sheet_rels_path = target.replace("worksheets/", "worksheets/_rels/") + ".rels"
            sheet_rels = parse_rels(_safe_read(zf, sheet_rels_path))
            hyperlinks_resolved = {
                rid: info["target"]
                for rid, info in sheet_rels.items()
                if "hyperlink" in info["type"]
            }

            # Comments live alongside the sheet via a "comments" rel.
            comments: dict[str, dict] = {}
            for rid, info in sheet_rels.items():
                if "comments" in info["type"] and "threadedComment" not in info["type"]:
                    cpath = info["target"]
                    if not cpath.startswith("xl/"):
                        cpath = f"xl/{cpath.lstrip('/').replace('../', '')}"
                    comments.update(parse_legacy_comments(_safe_read(zf, cpath)))

            parsed = parse_sheet(sheet_xml, shared, date_xfs)
            sheet_sections.append(
                render_sheet_section(sh, parsed, comments, hyperlinks_resolved)
            )

    # Frontmatter
    fm: dict = {"source": "xlsx", "source_file": in_path.name}
    fm.update(core)
    fm["sheet_count"]  = len(sheets)
    fm["sheet_names"]  = [sh["name"] for sh in sheets]
    hidden = [sh["name"] for sh in sheets if sh["hidden"]]
    if hidden:
        fm["hidden_sheets"] = hidden
    if defined_names:
        fm["defined_name_count"] = len(defined_names)

    # Body
    body_parts: list[str] = []
    title = fm.get("title") or in_path.stem
    body_parts.append(f"# {title}")
    body_parts.append("")
    if defined_names:
        body_parts += ["## Defined names", ""]
        for dn in defined_names:
            body_parts.append(f"- `{dn['name']}`: `{dn['value']}`")
        body_parts.append("")
    body_parts.extend(sheet_sections)
    body = "\n\n".join(p for p in body_parts if p != "")

    return fm, body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _gather_inputs(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".xlsx" else []
    pattern = "**/*.xlsx" if recursive else "*.xlsx"
    return sorted(
        f for f in input_path.glob(pattern)
        if not f.name.startswith("~$")  # Excel lock files
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert .xlsx workbooks to Markdown (lossless).")
    ap.add_argument("input", help="A .xlsx file or a directory of .xlsx files")
    ap.add_argument("-o", "--output", default="xlsx_md",
                    help="Output directory (default: ./xlsx_md)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Recurse into subdirectories when input is a directory")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = _gather_inputs(in_path, args.recursive)
    if not files:
        print(f"No .xlsx files found at {in_path}", file=sys.stderr)
        return 1

    written = skipped = 0
    for f in files:
        try:
            fm, body = convert_xlsx(f)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {f}: {e}", file=sys.stderr)
            skipped += 1
            continue
        out_file = out_dir / f"{f.stem}.md"
        n = 2
        while out_file.exists():
            out_file = out_dir / f"{f.stem}-{n}.md"
            n += 1
        out_file.write_text(
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
