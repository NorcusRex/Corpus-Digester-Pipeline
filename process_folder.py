#!/usr/bin/env python3
"""
process_folder.py

Walk a source folder tree, convert every supported file to Markdown, and
mirror the directory structure in an output folder. Run the metadata pass
over all generated Markdown at the end.

Source extension      Output
--------------------  --------------------------------------------------
.docx                 <stem>.md   (+ <stem>_media/ for extracted images)
.xlsx                 <stem>.md
.pdf                  <stem>.md   (+ <stem>_media/ for images & attachments)
conversations.json    <stem>/     (one .md per conversation inside)
.json (other)         skipped (not a recognized export shape)
.md                   copied as-is
.txt                  wrapped with frontmatter, saved as <stem>.md
anything else         <name.ext>.md sidecar recording the original

Lock files (~$foo.docx) and dotfiles are skipped silently, as is anything
inside a dot-folder (.obsidian/ and friends) at any depth.

Nothing in the source is dropped without a record. A file that cannot be
converted gets a small Markdown sidecar in the output naming the original and
its path relative to the corpus root, so `2-Digested` stays a complete view of
`1-Raw` without duplicating bulk. Media files and export auxiliaries continue
to be copied through as before.

Usage
-----
    python process_folder.py SOURCE_DIR OUTPUT_DIR
    python process_folder.py SOURCE_DIR OUTPUT_DIR --no-metadata
    python process_folder.py SOURCE_DIR OUTPUT_DIR --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

# Sister scripts must sit in the same directory as this orchestrator.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import docx_to_markdown        # noqa: E402
import xlsx_to_markdown        # noqa: E402
import chatgpt_to_markdown     # noqa: E402
import claude_to_markdown      # noqa: E402
import rtf_to_markdown         # noqa: E402
import html_to_markdown        # noqa: E402
import add_metadata            # noqa: E402

# Optional: project-name renamer. Only used if the user has placed both
# rename_chatgpt_projects.py and project_names.tsv next to this script.
try:
    import rename_chatgpt_projects   # noqa: E402
    HAVE_RENAMER = True
except ImportError:
    HAVE_RENAMER = False

# pdf_to_markdown raises SystemExit at import time if pypdf is missing.
# Catch that so the orchestrator can still process the other formats.
try:
    import pdf_to_markdown     # noqa: E402
    HAVE_PDF = True
    _pdf_error: str | None = None
except SystemExit as e:
    HAVE_PDF = False
    _pdf_error = str(e) or "pypdf not installed"
except ImportError as e:
    HAVE_PDF = False
    _pdf_error = str(e)


SKIP_FILE_PREFIXES = ("~$", ".")  # Office lock files, dotfiles

# Files we copy through unchanged so nothing is silently dropped. These
# extensions are content the user clearly cares about (images, audio, video)
# but that we don't have a converter for.
MEDIA_EXTS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff", ".tif",
    # Audio
    ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".opus",
    # Video
    ".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v",
    # Source / project files for graphic editors. We can't render them but the
    # bytes are the user's design content and should be preserved.
    ".xcf", ".psd", ".ai", ".sketch", ".afdesign", ".afphoto",
}

# Files that appear in ChatGPT exports alongside conversations.json. They
# carry account metadata or alternate views of the same data; we copy them
# through so the export remains complete.
CHATGPT_AUX_FILENAMES: set[str] = {
    "user.json", "user_settings.json", "export_manifest.json",
    "shared_conversations.json", "message_feedback.json",
    "model_comparisons.json", "chat.html",
}


# ---------------------------------------------------------------------------
# ChatGPT export detection
# ---------------------------------------------------------------------------

def find_chatgpt_export_roots(src_root: Path) -> set[Path]:
    """Return resolved paths of directories that look like ChatGPT exports.

    A folder qualifies if it contains both `user.json` and at least one
    `conversations*.json` file.
    """
    roots: set[Path] = set()
    try:
        for user_json in src_root.rglob("user.json"):
            if not user_json.is_file():
                continue
            parent = user_json.parent
            if any(parent.glob("conversations*.json")):
                try:
                    roots.add(parent.resolve())
                except OSError:
                    continue
    except OSError:
        pass
    return roots


def find_claude_export_roots(src_root: Path) -> set[Path]:
    """Return resolved paths of directories that look like Claude data exports.

    A folder qualifies if `claude_to_markdown.is_claude_export` says so:
    must contain `conversations.json`, `users.json`, and a `projects/`
    subfolder. Distinct from ChatGPT exports, which use `user.json` (singular)
    and live in chunked files.
    """
    roots: set[Path] = set()
    try:
        for users_json in src_root.rglob("users.json"):
            if not users_json.is_file():
                continue
            parent = users_json.parent
            if claude_to_markdown.is_claude_export(parent):
                try:
                    roots.add(parent.resolve())
                except OSError:
                    continue
    except OSError:
        pass
    return roots


def _is_inside(path: Path, roots: set[Path]) -> bool:
    """True if `path` lives inside any directory in `roots`."""
    if not roots:
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Console + log file tee
# ---------------------------------------------------------------------------

class _Tee:
    """Forward writes to multiple streams. Used to mirror stdout/stderr to
    both the console and a timestamped log file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:  # noqa: BLE001
                pass
        return len(data)

    def flush(self) -> None:
        for s in self.streams:
            try:
                s.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_chatgpt_export(path: Path) -> bool:
    """Heuristic: does this JSON look like a ChatGPT conversations.json?"""
    if path.name.lower() == "conversations.json":
        return True
    try:
        with path.open(encoding="utf-8") as f:
            head = f.read(4096)
    except (OSError, UnicodeDecodeError):
        return False
    # The export's distinctive shape: list of objects each carrying a
    # "mapping" tree and a "current_node".
    return '"mapping"' in head and '"current_node"' in head


def claim_output_path(path: Path, allocated: set) -> Path:
    """Reserve an output path within the current run.

    Existing files from PRIOR runs at this path will be silently overwritten
    when written -- that's the desired re-run behavior, where an updated
    source replaces its old converted output rather than accumulating.

    Within a single run, if two source files would produce the same output
    path (e.g. notes.docx and notes.pdf in the same folder both wanting
    notes.md), the second one gets a -2/-3/... suffix.
    """
    if path not in allocated:
        allocated.add(path)
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 2
    while True:
        candidate = parent / f"{stem}-{n}{suffix}"
        if candidate not in allocated:
            allocated.add(candidate)
            return candidate
        n += 1


def _handle_chatgpt_aux(src: Path, out_dir: Path, allocated: set,
                        stats: Counter) -> str:
    """Convert a ChatGPT aux file: JSON renders to .md, others copy as-is."""
    if src.suffix.lower() == ".json":
        try:
            fm, body = chatgpt_to_markdown.render_aux_json(src)
            md_path = claim_output_path(out_dir / f"{src.stem}.md", allocated)
            write_md(md_path, fm, body, chatgpt_to_markdown.to_yaml_frontmatter)
            stats["chatgpt_aux"] += 1
            return "chatgpt_aux (rendered)"
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not render {src.name}, copying instead: {e}",
                  file=sys.stderr)
            return _copy_through(src, out_dir, allocated, stats, "chatgpt_aux")
    # Non-JSON aux files (chat.html etc.) just copy through.
    return _copy_through(src, out_dir, allocated, stats, "chatgpt_aux")


def write_md(path: Path, fm: dict, body: str, fm_emitter) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm_emitter(fm) + "\n\n" + body + "\n", encoding="utf-8")


def _copy_through(src: Path, dest_dir: Path, allocated: set,
                  stats: Counter, kind: str) -> str:
    """Copy a file as-is to dest_dir. Used for media files, ChatGPT export
    aux files, and other content the pipeline preserves rather than converts.
    Returns a kind label for logging."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = claim_output_path(dest_dir / src.name, allocated)
    try:
        shutil.copy2(src, out_path)
    except OSError as e:
        print(f"  [warn] could not copy {src}: {e}", file=sys.stderr)
        stats["errors"] += 1
        return f"error: {e}"
    stats[kind] += 1
    return f"{kind} (copied)"


def _corpus_relative(src: Path, src_root: Path, corpus_root: Path | None) -> str:
    """Path to `src` relative to the corpus root, with forward slashes.

    The same string resolves on every mirror -- under I:\\RPG\\_Design\\Loom
    locally and under drive:RPG/_Design/Loom on Drive -- because the reader
    supplies the root, which it already knows. An absolute Windows path would
    be meaningless the moment the corpus is pushed.
    """
    for base in (corpus_root, src_root):
        if base is None:
            continue
        try:
            return src.relative_to(base).as_posix()
        except ValueError:
            continue
    return src.name


def write_unconvertible_sidecar(src: Path, out_dir: Path, allocated: set,
                                stats: Counter, src_root: Path,
                                corpus_root: Path | None) -> str:
    """Write a Markdown sidecar standing in for a file we cannot convert.

    The sidecar records the original's name, type, size and corpus-relative
    path. That makes the file findable from `2-Digested` without copying its
    bytes: a reader who needs the original follows `source_path` into `1-Raw`.

    Media files and export auxiliary files do NOT come here -- they are copied
    through, which is the right treatment for content we can preserve cheaply.
    """
    source_path = _corpus_relative(src, src_root, corpus_root)
    try:
        size = src.stat().st_size
        mtime = datetime.fromtimestamp(src.stat().st_mtime).astimezone()
        date_str = mtime.isoformat(timespec="minutes")
    except OSError:
        size = 0
        date_str = datetime.now().astimezone().isoformat(timespec="minutes")

    ext = src.suffix.lower() or "(none)"
    fm = {
        "title":       src.name,
        "date":        date_str,
        "source":      "unconverted file (sidecar)",
        "source_file": src.name,
        "source_path": source_path,
        "file_type":   ext,
        "size_bytes":  size,
    }
    # Same source identity the converted files carry, so a renamed original is
    # recognisable here too.
    add_metadata.stamp_source_identity(fm, src)
    body = (
        f"# {src.name}\n\n"
        f"This file could not be converted to Markdown. The original stays in "
        f"the raw tree; this sidecar records its identity so it is findable "
        f"from the digested tree.\n\n"
        f"- **Original name:** {src.name}\n"
        f"- **File type:** {ext}\n"
        f"- **Size:** {size:,} bytes\n"
        f"- **Path from corpus root:** `{source_path}`\n"
    )
    # Keep the extension in the sidecar name so notes.zip and notes.docx
    # cannot collide, and so the original is obvious from the filename.
    md_path = claim_output_path(out_dir / f"{src.name}.md", allocated)
    write_md(md_path, fm, body, docx_to_markdown.to_yaml_frontmatter)
    stats["sidecar"] += 1
    return "sidecar (unconvertible)"


def wrap_plaintext(src: Path) -> tuple[dict, str]:
    """Wrap a .txt file with minimal frontmatter for downstream metadata."""
    text = src.read_text(encoding="utf-8", errors="replace")
    fm = {
        "source":      "txt",
        "source_file": src.name,
    }
    body = f"# {src.stem}\n\n{text}".rstrip() + "\n"
    return fm, body


# ---------------------------------------------------------------------------
# Per-file dispatch
# ---------------------------------------------------------------------------

def process_file(src: Path, src_root: Path, out_root: Path,
                 stats: Counter, dry_run: bool,
                 allocated: set, chatgpt_roots: set,
                 claude_roots: set,
                 corpus_root: Path | None = None) -> str:
    """Process one file. Return a one-word kind for logging."""
    if any(src.name.startswith(p) for p in SKIP_FILE_PREFIXES):
        stats["skipped_lock_or_hidden"] += 1
        return "skipped"

    rel_parent = src.parent.relative_to(src_root)

    # Tooling, editor state, generated listings and build output are not corpus
    # content. The list is shared with the self-check so the two agree; when
    # they did not, a file under `_Tools/` was ignored by one and given a
    # sidecar by the other.
    if add_metadata.is_utility_path(src, src_root):
        stats["skipped_utility"] += 1
        return "skipped (utility)"

    out_dir = out_root / rel_parent
    suffix = src.suffix.lower()
    stem = src.stem

    inside_cgpt = _is_inside(src, chatgpt_roots)
    inside_claude = _is_inside(src, claude_roots)

    # Files inside a Claude export are handled wholesale by convert_export
    # at the end of the run, not file-by-file. Skip them here so we don't
    # double-process or misclassify them.
    if inside_claude:
        stats["claude_content"] += 1
        return "claude_content (handled by export pass)"

    if dry_run:
        # Just classify without writing anything.
        if suffix == ".docx":               stats["docx"] += 1; return "docx"
        if suffix == ".xlsx":               stats["xlsx"] += 1; return "xlsx"
        if suffix == ".pdf":
            if not HAVE_PDF:
                stats["skipped_no_pypdf"] += 1
                return "skipped"
            stats["pdf"] += 1; return "pdf"
        if suffix in {".html", ".htm"}:
            stats["html"] += 1; return "html"
        if suffix == ".rtf":
            stats["rtf"] += 1; return "rtf"
        if suffix == ".json" and is_chatgpt_export(src):
            stats["chatgpt"] += 1; return "chatgpt"
        if suffix == ".md":                 stats["md"] += 1; return "md"
        if suffix == ".txt":                stats["txt"] += 1; return "txt"
        if suffix in MEDIA_EXTS:            stats["media"] += 1; return "media"
        if src.name.lower() in CHATGPT_AUX_FILENAMES:
            stats["chatgpt_aux"] += 1; return "chatgpt_aux"
        if inside_cgpt:                     stats["chatgpt_content"] += 1; return "chatgpt_content"
        stats["sidecar"] += 1
        return "sidecar"

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if suffix == ".docx":
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            basename = md_path.stem  # tracks the .md filename if disambiguated
            fm, body = docx_to_markdown.convert_docx(src, out_dir, basename)
            add_metadata.stamp_source_identity(fm, src)
            write_md(md_path, fm, body, docx_to_markdown.to_yaml_frontmatter)
            stats["docx"] += 1
            return "docx"

        if suffix == ".xlsx":
            fm, body = xlsx_to_markdown.convert_xlsx(src)
            add_metadata.stamp_source_identity(fm, src)
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            write_md(md_path, fm, body, xlsx_to_markdown.to_yaml_frontmatter)
            stats["xlsx"] += 1
            return "xlsx"

        if suffix == ".pdf":
            if not HAVE_PDF:
                stats["skipped_no_pypdf"] += 1
                return "skipped (no pypdf)"
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            basename = md_path.stem
            fm, body = pdf_to_markdown.convert_pdf(src, out_dir, basename)
            add_metadata.stamp_source_identity(fm, src)
            write_md(md_path, fm, body, pdf_to_markdown.to_yaml_frontmatter)
            stats["pdf"] += 1
            return "pdf"

        if suffix in {".html", ".htm"}:
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            basename = md_path.stem
            fm, body = html_to_markdown.convert_html(src, out_dir, basename)
            add_metadata.stamp_source_identity(fm, src)
            write_md(md_path, fm, body, html_to_markdown.to_yaml_frontmatter)
            stats["html"] += 1
            return "html"

        if suffix == ".rtf":
            fm, body = rtf_to_markdown.convert_rtf(src)
            add_metadata.stamp_source_identity(fm, src)
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            write_md(md_path, fm, body, rtf_to_markdown.to_yaml_frontmatter)
            stats["rtf"] += 1
            return "rtf"

        if suffix == ".json":
            if not is_chatgpt_export(src):
                # Unrecognized JSON: render aux JSONs as Markdown, preserve
                # any other JSON that sits inside a ChatGPT export folder.
                if src.name.lower() in CHATGPT_AUX_FILENAMES:
                    return _handle_chatgpt_aux(src, out_dir, allocated, stats)
                if inside_cgpt:
                    return _copy_through(src, out_dir, allocated, stats, "chatgpt_content")
                return write_unconvertible_sidecar(src, out_dir, allocated,
                                                   stats, src_root, corpus_root)

            # Chunked exports (conversations-000.json, conversations-001.json,
            # ...) all merge into a single 'conversations' folder so projects
            # spanning multiple chunks stay together.
            chunk_match = re.match(r"^(conversations)-\d+$", stem)
            export_subdir_name = chunk_match.group(1) if chunk_match else stem

            sub_out = out_dir / export_subdir_name
            sub_out.mkdir(parents=True, exist_ok=True)
            with src.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("conversations") or [data]
            count = 0
            for conv in data:
                try:
                    fm, body, dstr = chatgpt_to_markdown.render_conversation(conv)
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] one conversation failed: {e}", file=sys.stderr)
                    continue
                slug = chatgpt_to_markdown.slugify(fm["title"])
                # Group into a per-project / per-GPT subfolder when applicable.
                # pick_subdir reuses existing (possibly user-renamed) folders
                # so renames survive re-runs.
                subdir = chatgpt_to_markdown.pick_subdir(
                    sub_out, fm.get("conversation_template_id", "")
                )
                target_dir = sub_out / subdir if subdir else sub_out
                target_dir.mkdir(parents=True, exist_ok=True)
                out_file = claim_output_path(target_dir / f"{dstr}__{slug}.md", allocated)
                write_md(out_file, fm, body, chatgpt_to_markdown.to_yaml_frontmatter)
                count += 1
            stats["chatgpt"] += 1
            stats["chatgpt_conversations"] += count
            return f"chatgpt ({count} conversations)"

        if suffix == ".md":
            out_path = claim_output_path(out_dir / src.name, allocated)
            out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            stats["md"] += 1
            return "md (copied)"

        if suffix == ".txt":
            fm, body = wrap_plaintext(src)
            add_metadata.stamp_source_identity(fm, src)
            md_path = claim_output_path(out_dir / f"{stem}.md", allocated)
            write_md(md_path, fm, body, docx_to_markdown.to_yaml_frontmatter)
            stats["txt"] += 1
            return "txt"

        # Fall-through: file isn't directly convertible. Preserve where
        # appropriate so the lossless principle holds.
        if suffix in MEDIA_EXTS:
            return _copy_through(src, out_dir, allocated, stats, "media")

        if src.name.lower() in CHATGPT_AUX_FILENAMES:
            return _handle_chatgpt_aux(src, out_dir, allocated, stats)

        if inside_cgpt:
            # Includes the no-extension `file-XXX` references that ChatGPT
            # exports use for uploaded user content.
            return _copy_through(src, out_dir, allocated, stats, "chatgpt_content")

        # Nothing is dropped. Anything left writes a sidecar recording what it
        # was and where it lives, so the digested tree accounts for every file
        # in the raw tree.
        return write_unconvertible_sidecar(src, out_dir, allocated, stats,
                                           src_root, corpus_root)

    except Exception as e:  # noqa: BLE001
        stats["errors"] += 1
        print(f"  [error] {src}: {e}", file=sys.stderr)
        if "--debug" in sys.argv:
            traceback.print_exc()
        return f"error: {e}"


def walk_files(src_root: Path):
    """Yield every regular file under src_root, sorted for stable output."""
    for p in sorted(src_root.rglob("*")):
        if p.is_file():
            yield p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Walk a folder tree and convert every supported file to Markdown."
    )
    ap.add_argument("input", help="Source directory")
    ap.add_argument("output", help="Destination directory (will mirror source structure)")
    ap.add_argument("--corpus-root", default=None,
                    help="Corpus root, the folder holding 1-Raw/2-Digested/"
                         "3-Reporting/4-Canon. Sidecars record source paths "
                         "relative to it so they resolve on every mirror. "
                         "Default: the parent of INPUT.")
    ap.add_argument("--dictionary", default=None,
                    help="Word list used to veto keyword rejections. A system "
                         "word list is used if one is found.")
    ap.add_argument("--lexicon", action="append", default=None,
                    help="Directory of word lists and glossaries (repeatable). "
                         "Used to veto keyword rejections.")
    ap.add_argument("--report-artifacts", default=None,
                    help="Write every rejected keyword and the test that "
                         "rejected it to this Markdown file.")
    ap.add_argument("--no-dictionary", action="store_true",
                    help="Do not look for a system word list.")
    ap.add_argument("--subject", action="append", default=None,
                    help="Speaker label naming the subject in speaker-labelled "
                         "documents (repeatable). Used by provenance-weighted "
                         "keyword extraction.")
    ap.add_argument("--no-metadata", action="store_true",
                    help="Skip the keyword-and-index metadata pass at the end")
    ap.add_argument("--keywords", type=int, default=None,
                    help="Override keyword count per file. Default: scale "
                         "with document length (8 for short, up to 40 for "
                         "very long).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be processed; do not write anything")
    ap.add_argument("--debug", action="store_true",
                    help="Print full traceback for any per-file error")
    ap.add_argument("--no-log", action="store_true",
                    help="Skip writing a log file")
    ap.add_argument("--log-dir", default=None,
                    help="Directory to write the log file (default: OUTPUT_DIR)")
    ap.add_argument("--clean", action="store_true",
                    help="Delete the contents of OUTPUT_DIR before running. "
                         "Use when you want a guaranteed-fresh build.")
    ap.add_argument("--no-rename", action="store_true",
                    help="Skip the ChatGPT-project folder rename step. "
                         "Otherwise, project_names.tsv next to this script "
                         "is applied automatically if present.")
    ap.add_argument("--rename-tsv", default=None,
                    help="Path to the project-name TSV file (default: "
                         "project_names.tsv next to process_folder.py)")
    ap.add_argument("--no-nlm", action="store_true",
                    help="Skip emission of NotebookLM-friendly .nlm.md sidecars. "
                         "By default, every .md gets a frontmatter-stripped "
                         "<name>.nlm.md sibling for upload to NotebookLM.")
    args = ap.parse_args()

    src_root = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    # The pipeline is pointed at a tier (1-Raw), not at the corpus root, so the
    # root has to be supplied or inferred. The parent of the input tier is
    # right for the standard layout and is overridable for anything else.
    corpus_root = (Path(args.corpus_root).resolve()
                   if args.corpus_root else src_root.parent)
    subject_names = ({n.lower() for n in args.subject}
                     if args.subject else None)
    lexicon_dirs = list(args.lexicon or [])
    if not lexicon_dirs and (SCRIPT_DIR / "lexicon").is_dir():
        lexicon_dirs.append(SCRIPT_DIR / "lexicon")
    dict_file = args.dictionary
    if dict_file is None and not args.no_dictionary:
        found = add_metadata.find_system_dictionary()
        dict_file = str(found) if found else None
    dictionary, lex_files = add_metadata.load_lexicons(lexicon_dirs, dict_file)
    dictionary = dictionary or None

    if not src_root.is_dir():
        print(f"ERROR: input is not a directory: {src_root}", file=sys.stderr)
        return 1
    if out_root == src_root or src_root in out_root.parents:
        print("ERROR: output directory cannot be inside the input directory.",
              file=sys.stderr)
        return 1

    if args.clean and not args.dry_run and out_root.exists():
        import shutil
        # Print to console only; the log file doesn't exist yet.
        print(f"--clean: removing existing contents of {out_root}", file=sys.__stdout__)
        for child in out_root.iterdir():
            try:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError as e:
                print(f"  WARNING: could not remove {child}: {e}",
                      file=sys.__stderr__)

    if not args.dry_run:
        out_root.mkdir(parents=True, exist_ok=True)

    # Set up tee logging: every print to stdout/stderr also goes to a file.
    log_handle = None
    log_path: Path | None = None
    if not args.dry_run and not args.no_log:
        log_dir = out_root if args.log_dir is None else Path(args.log_dir).resolve()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"_pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
            log_handle = log_path.open("w", encoding="utf-8")
            sys.stdout = _Tee(sys.__stdout__, log_handle)
            sys.stderr = _Tee(sys.__stderr__, log_handle)
        except OSError as e:
            print(f"WARNING: could not open log file: {e}", file=sys.__stderr__)
            log_handle = None
            log_path = None

    files = list(walk_files(src_root))
    chatgpt_roots = find_chatgpt_export_roots(src_root)
    claude_roots = find_claude_export_roots(src_root)
    print(f"Source : {src_root}")
    print(f"Output : {out_root}")
    print(f"Corpus : {corpus_root}")
    print(f"Found  : {len(files)} files")
    if chatgpt_roots:
        print(f"ChatGPT exports detected: {len(chatgpt_roots)} folder(s)")
    if claude_roots:
        print(f"Claude exports detected: {len(claude_roots)} folder(s)")
    if not HAVE_PDF:
        print(f"Note   : pypdf unavailable ({_pdf_error}); .pdf files will be skipped.")
    if args.dry_run:
        print("Mode   : DRY RUN (nothing will be written)")
    print()

    stats: Counter = Counter()
    allocated: set = set()
    start = time.time()

    for i, f in enumerate(files, 1):
        rel = f.relative_to(src_root)
        kind = process_file(f, src_root, out_root, stats, args.dry_run,
                            allocated, chatgpt_roots, claude_roots,
                            corpus_root)
        print(f"[{i:>4}/{len(files)}] {kind:<26} {rel}")

    # ---- Claude export pass --------------------------------------------
    # Each detected Claude export root is converted as a unit. The output
    # mirrors the source path so multiple exports stay separate.
    if claude_roots:
        print()
        print(f"Converting {len(claude_roots)} Claude export(s)...")
        for export_root in sorted(claude_roots):
            try:
                rel = export_root.relative_to(src_root.resolve())
            except ValueError:
                rel = Path(export_root.name)
            export_out = out_root / rel
            print(f"  Claude export: {rel}")
            if args.dry_run:
                print(f"    (dry run -- would convert to {export_out})")
                continue
            try:
                est = claude_to_markdown.convert_export(export_root, export_out)
            except Exception as e:  # noqa: BLE001
                print(f"    [warn] Claude export failed: {e}")
                stats["errors"] += 1
                continue
            stats["claude_exports"] += 1
            stats["claude_conversations"] += est.get("conversations", 0)
            stats["claude_projects"] += est.get("projects", 0)
            stats["claude_memories"] += (
                est.get("project_memories", 0)
                + est.get("conversations_memory", 0)
            )
            stats["claude_grouped"] += est.get("conversations_grouped", 0)
            stats["claude_ungrouped"] += est.get("conversations_ungrouped", 0)
            stats["claude_manifests"] += est.get("manifests_loaded", 0)
            stats["claude_stale_manifest_entries"] += est.get("manifest_stale_entries", 0)
            stats["claude_title_mismatches"] += est.get("manifest_title_mismatches", 0)
            stats["claude_uuid_conflicts"] += est.get("manifest_uuid_conflicts", 0)
            print(f"    converted: {est.get('conversations', 0)} conversations, "
                  f"{est.get('projects', 0)} projects, "
                  f"{est.get('project_memories', 0)} project memories")
            mans = est.get("manifests_loaded", 0)
            if mans:
                grp = est.get("conversations_grouped", 0)
                ungrp = est.get("conversations_ungrouped", 0)
                print(f"    manifests: {mans} loaded, "
                      f"{grp} grouped, {ungrp} ungrouped")
                if est.get("manifest_stale_entries", 0):
                    print(f"    [info] {est['manifest_stale_entries']} manifest "
                          f"entries reference conversations not in this export "
                          f"(deleted or pre-export)")
                if est.get("manifest_title_mismatches", 0):
                    print(f"    [info] {est['manifest_title_mismatches']} title "
                          f"mismatches between manifest and conversation "
                          f"(chats renamed since manifest)")
                if est.get("manifest_uuid_conflicts", 0):
                    print(f"    [warn] {est['manifest_uuid_conflicts']} UUID "
                          f"conflicts between manifests (please regenerate)")

    elapsed = time.time() - start

    # ---- Summary -------------------------------------------------------
    print()
    print("=" * 60)
    print(f"Conversion complete in {elapsed:.1f}s")
    print(f"  docx               : {stats['docx']}")
    print(f"  xlsx               : {stats['xlsx']}")
    print(f"  pdf                : {stats['pdf']}")
    print(f"  html               : {stats['html']}")
    if stats['rtf']:
        print(f"  rtf                : {stats['rtf']}")
    print(f"  chatgpt exports    : {stats['chatgpt']} "
          f"({stats['chatgpt_conversations']} conversations)")
    if stats['claude_exports'] or claude_roots:
        print(f"  claude exports     : {stats['claude_exports']} "
              f"({stats['claude_conversations']} conversations, "
              f"{stats['claude_projects']} projects, "
              f"{stats['claude_memories']} memories)")
    print(f"  markdown copied    : {stats['md']}")
    print(f"  txt wrapped        : {stats['txt']}")
    print(f"  media preserved    : {stats['media']}")
    print(f"  chatgpt aux files  : {stats['chatgpt_aux']}")
    print(f"  chatgpt content    : {stats['chatgpt_content']}")
    print(f"  sidecars written   : {stats['sidecar']}")
    print(f"  lock/hidden skipped: {stats['skipped_lock_or_hidden']}")
    print(f"  utility skipped    : {stats['skipped_utility']}")
    if stats['skipped_no_pypdf']:
        print(f"  pdf skipped (deps) : {stats['skipped_no_pypdf']}")
    print(f"  errors             : {stats['errors']}")

    # ---- Project rename pass --------------------------------------------
    # Apply human-readable names to project_<id> / gpt_<id> folders, using
    # project_names.tsv if it lives next to the orchestrator. This step is
    # idempotent: re-running on already-renamed folders is a no-op. It must
    # run BEFORE the metadata pass so keywords, the auto-index, and the
    # corpus index all reflect the final folder names.
    if not args.dry_run and HAVE_RENAMER and not args.no_rename:
        tsv_path = Path(args.rename_tsv) if args.rename_tsv else SCRIPT_DIR / "project_names.tsv"
        if tsv_path.is_file():
            print()
            print(f"Applying project name map from {tsv_path.name}...")
            try:
                mapping = rename_chatgpt_projects.load_tsv(tsv_path)
                if mapping:
                    rstats = rename_chatgpt_projects.apply_renames(
                        mapping, out_root, dry_run=False, verbose=False
                    )
                    print(f"  renamed: {rstats['renamed']}, "
                          f"already named: {rstats['already']}, "
                          f"not in archive: {rstats['skipped_missing']}")
                    if rstats["skipped_existing"]:
                        print(f"  WARNING: {rstats['skipped_existing']} renames "
                              f"skipped because target name already exists. "
                              f"Check for duplicate names in your TSV.")
                else:
                    print("  TSV loaded but contained no valid mappings.")
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] project rename failed: {e}", file=sys.stderr)
        # Silent skip if TSV doesn't exist -- not every user has set one up.

    # ---- Metadata pass --------------------------------------------------
    if not args.dry_run and not args.no_metadata:
        print()
        print("Indexing generated Markdown...")
        md_files = [f for f in sorted(out_root.rglob("*.md"))
                    if not f.name.endswith(".nlm.md")]
        # Build corpus document-frequency stats so keyword extraction uses
        # TF-IDF (distinctive terms) rather than raw frequency (generic
        # high-count words like "edge", "roll").
        doc_freq = None
        total_docs = 0
        if len(md_files) >= 5:
            print(f"  scanning {len(md_files)} files for TF-IDF corpus stats...")
            doc_freq, total_docs = add_metadata.build_corpus_doc_freq(md_files)
            print(f"  vocabulary: {len(doc_freq)} unique terms in {total_docs} files")
        if dictionary:
            print(f"  lexicon: {len(dictionary):,} terms from "
                  f"{len(lex_files)} file(s)")
        changed = 0
        meta_stats: Counter = Counter()
        unknown_files: list[Path] = []
        artifact_log: list = [] if args.report_artifacts else None
        for f in md_files:
            try:
                before = meta_stats["structure_unknown"]
                if add_metadata.process_file(f, n_keywords=args.keywords,
                                             write_index=True,
                                             doc_freq=doc_freq,
                                             total_docs=total_docs,
                                             subject_names=subject_names,
                                             stats=meta_stats,
                                             dictionary=dictionary,
                                             artifact_log=artifact_log):
                    changed += 1
                if meta_stats["structure_unknown"] > before:
                    unknown_files.append(f)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] metadata for {f.relative_to(out_root)}: {e}",
                      file=sys.stderr)
        print(f"  metadata updated   : {changed} of {len(md_files)} files")
        # Every `unknown` file is reported. They are candidates for an AI pass
        # to recover turns, or for the owner to find the source conversation.
        add_metadata.report_structure_stats(meta_stats, unknown_files, out_root)
        if args.report_artifacts and artifact_log is not None:
            add_metadata.write_artifact_report(args.report_artifacts,
                                               artifact_log, out_root)
            print(f"  rejected-keyword report: {args.report_artifacts}")
        stats.update(meta_stats)

    # ---- NotebookLM sidecars --------------------------------------------
    # NotebookLM treats YAML frontmatter as literal text, which clutters its
    # responses. We emit a frontmatter-stripped .nlm.md sibling next to each
    # canonical .md so you can upload the .nlm.md files to NotebookLM while
    # keeping the .md (with frontmatter) for Obsidian property search.
    # Sidecars are excluded from the metadata pass (they're not a primary
    # source) and from the corpus index (they're derivative).
    if not args.dry_run and not args.no_nlm:
        print()
        print("Generating NotebookLM sidecars (.nlm.md)...")
        # Re-glob to pick up files written this run; exclude existing
        # .nlm.md so we don't generate sidecars-of-sidecars.
        primary = [f for f in sorted(out_root.rglob("*.md"))
                   if not f.name.endswith(".nlm.md")]
        nlm_written = 0
        for f in primary:
            try:
                text = f.read_text(encoding="utf-8")
                _, body = add_metadata.parse_frontmatter(text)
                # Drop a leading auto-index block too; NotebookLM doesn't
                # need it (its body content already covers the same ground).
                body = add_metadata.INDEX_BLOCK_RE.sub("", body, count=1)
                body = body.lstrip("\n")
                sidecar = f.with_suffix(".nlm.md")
                # Only re-write if content has changed -- saves Drive sync churn.
                if sidecar.exists():
                    try:
                        if sidecar.read_text(encoding="utf-8") == body:
                            continue
                    except OSError:
                        pass
                sidecar.write_text(body, encoding="utf-8")
                nlm_written += 1
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] sidecar for {f.relative_to(out_root)}: {e}",
                      file=sys.stderr)
        print(f"  nlm sidecars       : {nlm_written} of {len(primary)} files updated")

    # ---- Corpus index --------------------------------------------------
    # A single JSON file listing every output .md and the media folders.
    # Future audits can read this in one shot rather than walking the tree.
    # NOTE: this is the CONTENT/keyword index. It is a different artifact
    # from the Claude-export PROJECT-GROUPING manifest
    # (<UUID>_manifest.json, handled in claude_to_markdown.py), which is
    # deliberately still called a "manifest" because that name is correct
    # there. Keep the two vocabularies separate.
    if not args.dry_run:
        try:
            md_files = [f for f in sorted(out_root.rglob("*.md"))
                        if not f.name.endswith(".nlm.md")]
            index_entries = []
            for f in md_files:
                if f.name.startswith("_pipeline_") and f.suffix == ".log":
                    continue
                try:
                    text = f.read_text(encoding="utf-8")
                    fm, _ = add_metadata.parse_frontmatter(text)
                except OSError:
                    fm = {}
                index_entries.append({
                    "path": str(f.relative_to(out_root)).replace("\\", "/"),
                    "size_bytes": f.stat().st_size,
                    "frontmatter": fm,
                })
            corpus_index = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "output_root": str(out_root),
                "file_count": len(index_entries),
                "stats": dict(stats),
                "files": index_entries,
            }
            # Corpus index. Renamed _manifest.json -> _index.json to end
            # the "manifest" overload: this content/keyword index is a
            # different artifact from the Claude-export PROJECT-GROUPING
            # manifest (<UUID>_manifest.json) handled in
            # claude_to_markdown.py. Legacy _manifest.json files from
            # prior runs mean the SAME index and remain valid until a
            # re-digest supersedes them; consumers treat both names as
            # equivalent. This index is metadata-only and written
            # PRE-PUSH, so it intentionally carries no Drive file IDs
            # (the Drive objects do not exist yet) -- this is by design,
            # not a gap to fix.
            index_path = out_root / "_index.json"
            with index_path.open("w", encoding="utf-8") as f:
                json.dump(corpus_index, f, indent=2, ensure_ascii=False)
            print()
            print(f"Corpus index written to {index_path}")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not write corpus index: {e}", file=sys.stderr)

    print("=" * 60)

    # Close the log file and tell the user where it landed.
    if log_handle is not None:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        try:
            log_handle.close()
        except Exception:  # noqa: BLE001
            pass
        if log_path is not None:
            print(f"Log written to: {log_path}")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
