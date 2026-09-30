#!/usr/bin/env python3
"""
subset_inventory.py

Report what is available to select from a digested export archive, and which
corpora already select it.

This is the read side of `sync_subset.py`. That script mirrors named folders
out of a central digested archive into a corpus; this one tells you what the
names are, how much is behind each, and which of them nothing has claimed.

THE PROBLEM THIS SOLVES

An AI export is topic-blind: one bundle covering every subject you have ever
discussed, across years. After digestion it resolves into project folders, and
those folders are the selectable unit -- but nothing tells you what they are.
Writing a selection list means browsing a folder in a file manager and typing
names into a text file, and keeping one current after a fresh export means
doing it again and spotting what changed by eye.

The part that actually goes wrong is the silent one. A project you never
selected is not an error anywhere: it simply never reaches a corpus, and the
only symptom is a search that finds nothing and cannot tell you why. This
script makes that visible by listing what nothing claims.

WHAT IT DOES

Given a source tree whose immediate subfolders are the selectable units, and
any number of named selection lists, it reports:

  1. Every selectable folder, with file counts, total size, and the span of
     dates it covers.
  2. Which of the given selection lists name each folder.
  3. Folders no list names -- material sitting in the archive that no corpus
     will ever see.
  4. List entries naming a folder that is not in the source -- a typo, a
     renamed project, or a list written against an older export.

It reads and writes nothing but its own report. There is no selection, no
mirroring and no deletion here; those live in `sync_subset.py`, which is the
only script that moves anything.

DATES

Taken from the filename where the pipeline's convention supplies one
(`YYYY-MM-DD__slug.md`), and from the `date` frontmatter field otherwise. The
filename is preferred because it is free -- the alternative is opening every
file in an archive that may hold tens of thousands.

USAGE

    python subset_inventory.py SOURCE
    python subset_inventory.py SOURCE --list Loom=I:\\...\\_Tools\\subset_claude.txt
    python subset_inventory.py SOURCE --list Loom=... --list Theory=... --report inv.md

    SOURCE          a digested tree whose immediate subfolders are the
                    selectable units. For a Claude archive this is
                    .../2-Digested/conversations; for ChatGPT it is the
                    folder holding the project_* folders.
    --list NAME=PATH   a selection list, labelled. Repeatable.
    --report FILE   also write the report to this Markdown file
    --min-files N   only list folders holding at least N files (default 0)

EXIT CODES

    0  every folder is selected by at least one list, and every list entry
       was found
    1  completed, with unselected folders or unmatched list entries
    2  a usage or path error prevented the run
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import add_metadata  # noqa: E402

# The pipeline names conversation files `YYYY-MM-DD__slug.md`, sometimes with
# a time component. Anchored at the start so a date inside a slug is not
# mistaken for the document's own date.
FILENAME_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

# How much of a file to read when falling back to frontmatter. Frontmatter
# sits at the top; reading further is wasted on a large conversation.
FRONTMATTER_PEEK_BYTES = 2048


def parse_date(path: Path) -> date | None:
    """The document's date, from its filename or failing that its frontmatter."""
    m = FILENAME_DATE_RE.match(path.name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass  # 2026-13-45 and friends: fall through to the frontmatter
    if path.suffix.lower() != ".md":
        return None
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            head = f.read(FRONTMATTER_PEEK_BYTES)
    except OSError:
        return None
    fm, _ = add_metadata.parse_frontmatter(head)
    raw = str(fm.get("date", "") or "").strip()
    m = FILENAME_DATE_RE.match(raw)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


class FolderSummary:
    """What one selectable folder holds."""

    def __init__(self, path: Path):
        self.name = path.name
        self.files = 0
        self.md_files = 0
        self.bytes = 0
        self.first: date | None = None
        self.last: date | None = None
        self.selected_by: list[str] = []

        for f in path.rglob("*"):
            if not f.is_file():
                continue
            if add_metadata.is_utility_path(f, path):
                continue
            # `.nlm.md` files are derivative -- one per real document. Counting
            # them would double every total and mean nothing.
            if f.name.endswith(".nlm.md"):
                continue
            self.files += 1
            try:
                self.bytes += f.stat().st_size
            except OSError:
                pass
            if f.suffix.lower() == ".md":
                self.md_files += 1
                d = parse_date(f)
                if d:
                    if self.first is None or d < self.first:
                        self.first = d
                    if self.last is None or d > self.last:
                        self.last = d

    @property
    def span(self) -> str:
        if self.first is None:
            return "--"
        if self.first == self.last:
            return self.first.isoformat()
        return f"{self.first.isoformat()} .. {self.last.isoformat()}"

    @property
    def size(self) -> str:
        n = float(self.bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} GB"


def load_selection(path: Path) -> list[str]:
    """Folder names from a selection list. Blank lines and # comments ignored."""
    names = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def parse_list_arg(value: str) -> tuple[str, Path]:
    """Split a --list NAME=PATH argument. A bare path is labelled by filename."""
    if "=" in value:
        name, _, raw = value.partition("=")
        return name.strip(), Path(raw.strip())
    p = Path(value)
    return p.stem, p


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def write(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report what a digested export archive offers for "
                    "selection, and what nothing selects.")
    ap.add_argument("source",
                    help="Digested tree whose immediate subfolders are the "
                         "selectable units")
    ap.add_argument("--list", action="append", default=[], dest="lists",
                    metavar="NAME=PATH",
                    help="A selection list, labelled. Repeatable.")
    ap.add_argument("--report", default=None,
                    help="Also write the report to this Markdown file")
    ap.add_argument("--min-files", type=int, default=0,
                    help="Only list folders holding at least this many files")
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        print(f"ERROR: not a directory: {source}", file=sys.stderr)
        return 2

    selections: dict[str, list[str]] = {}
    for spec in args.lists:
        label, list_path = parse_list_arg(spec)
        if not list_path.is_file():
            print(f"ERROR: selection list not found: {list_path}",
                  file=sys.stderr)
            return 2
        selections[label] = load_selection(list_path)

    folders = sorted((d for d in source.iterdir()
                      if d.is_dir() and not d.name.startswith(".")
                      and d.name not in add_metadata.EXCLUDED_DIR_NAMES),
                     key=lambda d: d.name.lower())

    summaries = [FolderSummary(d) for d in folders]
    by_name = {s.name: s for s in summaries}
    for label, names in selections.items():
        for n in names:
            if n in by_name:
                by_name[n].selected_by.append(label)

    shown = [s for s in summaries if s.files >= args.min_files]
    unselected = [s for s in summaries if not s.selected_by]
    unmatched = {label: [n for n in names if n not in by_name]
                 for label, names in selections.items()}
    unmatched = {k: v for k, v in unmatched.items() if v}

    r = Report()
    r.say("# Selectable projects")
    r.say()
    r.say(f"Source: `{source}`")
    r.say()
    r.say(f"{len(summaries):,} selectable folder(s), "
          f"{sum(s.files for s in summaries):,} file(s) in total.")
    if args.min_files:
        r.say(f"Showing the {len(shown):,} holding at least "
              f"{args.min_files} file(s).")
    r.say()

    label_col = "Selected by" if selections else "—"
    r.say(f"| Folder | Files | Markdown | Size | Dates | {label_col} |")
    r.say("|---|---:|---:|---:|---|---|")
    for s in shown:
        claimed = ", ".join(s.selected_by) if s.selected_by else "**nothing**"
        r.say(f"| `{s.name}` | {s.files:,} | {s.md_files:,} | {s.size} | "
              f"{s.span} | {claimed} |")

    if selections:
        r.say()
        r.say("## Selected by nothing")
        r.say()
        if unselected:
            # The quiet failure this script exists for: material that reaches
            # no corpus, reported by no other tool, whose only symptom is a
            # search that finds nothing and cannot say why.
            r.say(f"**{len(unselected):,} folder(s) no list names.** This "
                  f"material is in the archive and will not reach any corpus.")
            r.say()
            for s in unselected:
                r.say(f"- `{s.name}` — {s.files:,} file(s), {s.span}")
        else:
            r.say("None. Every folder is selected by at least one list.")

        r.say()
        r.say("## List entries not found in the source")
        r.say()
        if unmatched:
            r.say("A typo, a project renamed since the list was written, or a "
                  "list written against an older export.")
            r.say()
            for label, names in unmatched.items():
                for n in names:
                    r.say(f"- **{label}**: `{n}`")
        else:
            r.say("None. Every list entry matched a folder.")
    else:
        r.say()
        r.say("No selection lists given, so nothing is reported about what "
              "is claimed. Pass `--list NAME=PATH` to see that.")

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        r.write(out)
        print()
        print(f"Report written to {out}")

    return 1 if (unselected and selections) or unmatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
