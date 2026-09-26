#!/usr/bin/env python3
"""
ocr_pdf.py

Recover text from scanned PDFs, without modifying them.

THE PROBLEM

A scanned PDF is a picture of a page. `pypdf` extracts nothing from it, so the
document reaches `2-Digested` with no body, no keywords, and no way for search
to find it. The pipeline already notices -- `likely_scanned: true` in the
frontmatter -- and until now that was the end of it.

WHY THIS DOES NOT WRITE TO `1-Raw`

The obvious approach, and the one a hand-rolled batch script reaches for, is
to run `ocrmypdf` over the raw tree and overwrite each file with its OCR'd
version. That is safe only when `1-Raw` holds copies. By definition it holds
incoming material, which for most corpora means the originals, and a pipeline
that rewrites the originals is one bad run away from losing them.

So nothing here modifies the source. `ocrmypdf` writes its text to a sidecar,
the text is cached under the corpus root, and the OCR'd PDF itself is
discarded. What the corpus gains is the text, which is the part search needs.

THE CACHE EARNS ITS PLACE

OCR is the slowest thing the pipeline can do -- seconds per page, against
milliseconds for everything else. Digestion is meant to be re-runnable, and a
re-run that re-OCRs a hundred books is a re-run nobody does.

The cache is keyed on the **content hash** of the source PDF, not its path or
its mtime. So a book that is renamed, or moved between corpora, or re-copied
from the archive, is still a cache hit. Editing the PDF is what invalidates
it, which is the only thing that should.

PARALLELISM

`ocrmypdf` invocations are independent, so they run several at a time. This is
the difference between an overnight job and a weekend one, and it is the main
thing a serial `for` loop over the tree gives up.

FAILURES ARE RECORDED, NOT SWALLOWED

A book that fails OCR is named in the log and counted in the summary. It is
easy to send stderr to nowhere and end up with a corpus that is quietly
missing whatever did not work, with nothing saying which files those were.

DEPENDENCY

`ocrmypdf` is an external program, not a Python package -- it is invoked as a
subprocess, so nothing is imported and nothing is installed by the pipeline.
It is found by the `OCRMYPDF_EXE` environment variable, then on `PATH`. When
it is absent, OCR is skipped with a message and everything else proceeds.

USAGE

    python ocr_pdf.py 1-Raw --cache _ocr-cache
    python ocr_pdf.py 1-Raw --cache _ocr-cache --jobs 8
    python ocr_pdf.py 1-Raw --cache _ocr-cache --dry-run

Normally it is not run directly: `process_folder.py --ocr` runs it as a
pre-pass before conversion.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# An optional dependency's import must never take the run down with it, and
# ImportError is not the only way one can fail. A pypdf whose native crypto
# backend is broken raises a pyo3 PanicException, which inherits from
# BaseException and sails straight past `except Exception`. Found the hard
# way, on a machine with exactly that install. KeyboardInterrupt is re-raised
# so the broad catch cannot swallow a Ctrl-C.
try:
    import pypdf
    HAVE_PYPDF = True
    _pypdf_error = ""
except KeyboardInterrupt:
    raise
except BaseException as _e:  # noqa: BLE001
    HAVE_PYPDF = False
    _pypdf_error = str(_e) or _e.__class__.__name__

CACHE_DIR_NAME = "_ocr-cache"

# Same heuristic the PDF converter uses to set `likely_scanned`: pages exist
# but almost no text came out of them. Kept identical deliberately -- two
# thresholds that drift apart would mean a file flagged as scanned that OCR
# never looked at.
CHARS_PER_PAGE_FLOOR = 20

# Pages sampled when deciding whether a PDF needs OCR. Reading every page of
# every book to find out is most of the cost of reading the book.
PROBE_PAGES = 10

# ocrmypdf's own exit codes. 6 means "already has text and --skip-text was
# given", which is a success for our purposes and not a failure to report.
EXIT_ALREADY_HAS_TEXT = 6


def find_ocrmypdf() -> str | None:
    """Locate ocrmypdf: the OCRMYPDF_EXE variable, then PATH."""
    env = os.environ.get("OCRMYPDF_EXE")
    if env:
        return env if Path(env).exists() else None
    return shutil.which("ocrmypdf")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_text_chars(path: Path) -> tuple[int, int]:
    """(characters found, pages sampled) for a quick scanned-or-not check."""
    if not HAVE_PYPDF:
        return (0, 0)
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                return (0, 0)
        pages = reader.pages[:PROBE_PAGES]
        chars = 0
        for page in pages:
            try:
                chars += len(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                pass
        return (chars, len(pages))
    except Exception:  # noqa: BLE001
        return (0, 0)


def looks_scanned(path: Path) -> bool:
    chars, pages = probe_text_chars(path)
    if pages == 0:
        return False
    return chars < CHARS_PER_PAGE_FLOOR * pages


def cache_file(cache_dir: Path, digest: str) -> Path:
    # Two-character prefix directory: a flat folder of ten thousand files is
    # slow to list on Windows and unpleasant to look at.
    return cache_dir / digest[:2] / f"{digest}.txt"


def cached_text(cache_dir: Path, src: Path) -> str | None:
    """The cached OCR text for `src`, or None if it has not been OCR'd."""
    try:
        target = cache_file(cache_dir, file_sha256(src))
    except OSError:
        return None
    if target.is_file():
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    return None


def cached_pages(cache_dir: Path, src: Path) -> dict[int, str] | None:
    """Cached OCR text split into pages, 1-based.

    ocrmypdf's sidecar separates pages with a form feed. Where it does not,
    the whole document comes back as page 1, which the converter handles by
    appending it once rather than per page.
    """
    text = cached_text(cache_dir, src)
    if text is None:
        return None
    parts = text.split("\f")
    return {i: p.strip() for i, p in enumerate(parts, start=1) if p.strip()}


def ocr_one(exe: str, src: Path, cache_dir: Path, lang: str | None,
            timeout: int) -> tuple[Path, str, str]:
    """OCR one PDF into the cache. Returns (src, status, detail).

    status is one of: cached, ocred, no-text, failed.
    """
    try:
        digest = file_sha256(src)
    except OSError as e:
        return (src, "failed", f"unreadable: {e}")

    target = cache_file(cache_dir, digest)
    if target.is_file():
        return (src, "cached", "")

    with tempfile.TemporaryDirectory(prefix="ocr_") as tmp:
        tmpdir = Path(tmp)
        sidecar = tmpdir / "text.txt"
        # The OCR'd PDF is written and thrown away. We want the text; keeping
        # a second copy of every book is not what this is for.
        out_pdf = tmpdir / "out.pdf"
        cmd = [exe, "--skip-text", "--sidecar", str(sidecar),
               "--output-type", "pdf"]
        if lang:
            cmd += ["-l", lang]
        cmd += [str(src), str(out_pdf)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return (src, "failed", f"timed out after {timeout}s")
        except OSError as e:
            return (src, "failed", f"could not run ocrmypdf: {e}")

        if proc.returncode not in (0, EXIT_ALREADY_HAS_TEXT):
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return (src, "failed",
                    detail[-1] if detail else f"exit {proc.returncode}")

        if not sidecar.is_file():
            return (src, "no-text", "ocrmypdf produced no sidecar")
        try:
            text = sidecar.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return (src, "failed", f"could not read sidecar: {e}")

    if not text.strip():
        # Recorded rather than cached: an empty result is usually a bad scan,
        # and caching it would mean never trying again after it is rescanned.
        return (src, "no-text", "OCR produced no text")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as e:
        return (src, "failed", f"could not write cache: {e}")
    return (src, "ocred", f"{len(text):,} chars")


def run_batch(pdfs: list[Path], cache_dir: Path, jobs: int = 4,
              lang: str | None = None, dry_run: bool = False,
              timeout: int = 3600, log_path: Path | None = None,
              verbose: bool = True) -> dict:
    """OCR every scanned PDF in `pdfs` into `cache_dir`. Returns a stats dict."""
    stats = {"considered": len(pdfs), "scanned": 0, "cached": 0, "ocred": 0,
             "no_text": 0, "failed": 0, "skipped_has_text": 0}

    exe = find_ocrmypdf()
    if exe is None:
        if verbose:
            print("  ocrmypdf not found (set OCRMYPDF_EXE or put it on PATH) "
                  "-- scanned PDFs will have no text.")
        stats["unavailable"] = True
        return stats
    if not HAVE_PYPDF:
        if verbose:
            print(f"  pypdf unavailable ({_pypdf_error}) -- cannot tell which "
                  f"PDFs need OCR.")
        stats["unavailable"] = True
        return stats

    needs: list[Path] = []
    for p in pdfs:
        if looks_scanned(p):
            needs.append(p)
        else:
            stats["skipped_has_text"] += 1
    stats["scanned"] = len(needs)

    if verbose:
        print(f"  {len(pdfs):,} PDF(s); {len(needs):,} look scanned, "
              f"{stats['skipped_has_text']:,} already carry text.")
    if not needs:
        return stats

    if dry_run:
        for p in needs:
            print(f"    would OCR {p.name}")
        return stats

    cache_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(ocr_one, exe, p, cache_dir, lang, timeout): p
                   for p in needs}
        done = 0
        for fut in as_completed(futures):
            src, status, detail = fut.result()
            done += 1
            key = {"cached": "cached", "ocred": "ocred",
                   "no-text": "no_text", "failed": "failed"}[status]
            stats[key] += 1
            if status == "failed":
                failures.append(f"{src}\t{detail}")
                print(f"  [warn] OCR failed: {src.name} -- {detail}",
                      file=sys.stderr)
            elif status == "no-text":
                failures.append(f"{src}\t(no text) {detail}")
            if verbose and done % 10 == 0:
                print(f"    {done:,}/{len(needs):,}")

    if log_path and failures:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "Files OCR could not produce text for.\n"
                "Tab-separated: path, reason.\n\n" + "\n".join(sorted(failures))
                + "\n", encoding="utf-8")
            print(f"  problems logged to {log_path}")
        except OSError as e:
            print(f"  [warn] could not write OCR log: {e}", file=sys.stderr)

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OCR the scanned PDFs under a tree into a text cache, "
                    "without modifying them.")
    ap.add_argument("root", help="Tree to scan for PDFs, e.g. 1-Raw")
    ap.add_argument("--cache", default=None,
                    help=f"Cache directory (default: {CACHE_DIR_NAME} beside "
                         f"the tree)")
    ap.add_argument("--jobs", type=int, default=4,
                    help="How many OCR processes to run at once (default 4)")
    ap.add_argument("--lang", default=None,
                    help="Tesseract language code passed through as -l")
    ap.add_argument("--timeout", type=int, default=3600,
                    help="Seconds before one file is given up on (default 3600)")
    ap.add_argument("--log", default=None, help="Write failures to this file")
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be OCR'd, change nothing")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    cache_dir = (Path(args.cache).expanduser() if args.cache
                 else root.parent / CACHE_DIR_NAME)
    pdfs = sorted(p for p in root.rglob("*.pdf") if p.is_file())
    if not pdfs:
        print(f"No PDFs under {root}.")
        return 0

    stats = run_batch(pdfs, cache_dir, jobs=args.jobs, lang=args.lang,
                      dry_run=args.dry_run, timeout=args.timeout,
                      log_path=Path(args.log) if args.log else None)
    print()
    for k in ("considered", "skipped_has_text", "scanned", "cached", "ocred",
              "no_text", "failed"):
        print(f"  {k:18}: {stats.get(k, 0):,}")
    if args.dry_run:
        print("(dry run -- nothing was written)")
    return 1 if stats.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
