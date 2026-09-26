#!/usr/bin/env python3
"""
drive_collisions.py

Find the `.xlsx`-versus-Google-Sheet collisions that make an rclone push fail,
and say which Sheets are safe to remove.

THE PROBLEM

Opening an `.xlsx` in Drive with "Open with Google Sheets" leaves a native
Sheet beside it. rclone then sees two objects it considers the same name in
the same folder, tries to update the Sheet from the local `.xlsx`, and stops:

    ERROR : ....xlsx: Failed to copy: can't update google document type
            without --drive-import-formats

Adding that flag is the trap. It does not fix the collision -- it converts the
local `.xlsx` into a Sheets update, silently discarding Excel-only features
that the real files use. It was tried once and rolled back for exactly that
reason, and this script exists so the rollback does not have to be repeated.

THE RULE THIS APPLIES

Nick's, and the script does not deviate from it: **delete the Sheet only when
the `.xlsx` is newer than or equal to the Sheet.** If the Sheet is newer,
someone edited it in Drive and those edits are not in the local file, so it
stays and the collision is reported as needing a human.

WHAT IT DOES AND DOES NOT DO

It reports. It never deletes, never renames, never writes to Drive. The output
is a review list carrying the Drive file IDs, so the deletions can be made
deliberately -- in the Drive web UI, or by a command you run yourself after
reading the list.

That is not timidity. The input is a heuristic match on filename, and the
thing being deleted is the only copy of any edit made in Sheets. A tool that
guessed and deleted would be wrong rarely and expensively.

SHEETS WHOSE TITLE ENDS IN `.xlsx`

A hand-made "Open with Google Sheets" conversion is titled without the
extension: `Character Sheet v3.1`. A Sheet titled `Character Sheet v3.1.xlsx`
almost certainly was not made by hand -- it is the shape rclone leaves behind
when it imports an `.xlsx` as a Google document, which is what
`--drive-import-formats` did during the run that was rolled back. These are
flagged separately, because the question "is this mine or is it debris?" has a
different answer for them and the distinction is testable rather than a guess.

INPUT

Either let it call rclone:

    python drive_collisions.py drive:RPG/_Design/Loom --report collisions.md

or feed it a listing you produced yourself, which needs no rclone here:

    rclone lsjson -R --drive-show-all-gdocs drive:RPG/_Design/Loom > listing.json
    python drive_collisions.py --json listing.json --report collisions.md

The second form exists because the first depends on rclone flags that vary by
version. If `--drive-show-all-gdocs` is rejected, drop it and re-run: the
listing is still usable, and the script says so rather than failing.

COMPARING AGAINST THE LOCAL FILE

`--local <path>` compares each Sheet against the modification time of the
local `.xlsx` rather than of its Drive copy. Prefer it where the local tree is
the authoritative one, which is the standing rule for this corpus: local is
authoritative, Drive is the mirror.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_log  # noqa: E402

SHEET_MIME = "application/vnd.google-apps.spreadsheet"

# Native Google types have no byte content to download, so rclone reports them
# with a size of -1. Useful as a cross-check when a listing lacks MimeType.
GOOGLE_DOC_SIZE = -1


def run_rclone(remote: str, exe: str = "rclone") -> list:
    """Ask rclone for a recursive JSON listing of `remote`."""
    base = [exe, "lsjson", "-R", "--drive-show-all-gdocs", remote]
    for cmd in (base, [c for c in base if c != "--drive-show-all-gdocs"]):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except OSError as e:
            print(f"ERROR: could not run rclone: {e}", file=sys.stderr)
            return []
        if proc.returncode == 0:
            if cmd is not base:
                print("  (rclone rejected --drive-show-all-gdocs; listed "
                      "without it)")
            try:
                return json.loads(proc.stdout or "[]")
            except json.JSONDecodeError as e:
                print(f"ERROR: rclone output was not JSON: {e}",
                      file=sys.stderr)
                return []
        last = (proc.stderr or "").strip()
    print(f"ERROR: rclone failed: {last}", file=sys.stderr)
    return []


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_sheet(entry: dict) -> bool:
    mime = entry.get("MimeType") or ""
    if mime == SHEET_MIME:
        return True
    # Some rclone versions report the export MIME type instead. A Google
    # native object still has no byte size, so that is the fallback signal.
    return (entry.get("Size") == GOOGLE_DOC_SIZE
            and "spreadsheet" in mime.lower())


def split_path(path: str) -> tuple[str, str]:
    """(parent, name) for a forward-slashed rclone path."""
    path = path.replace("\\", "/")
    if "/" not in path:
        return ("", path)
    parent, _, name = path.rpartition("/")
    return (parent, name)


def find_collisions(entries: list, local_root: Path | None) -> tuple[list, list]:
    """Returns (collisions, extension_titled_sheets)."""
    sheets: dict[tuple[str, str], dict] = {}
    xlsx: dict[tuple[str, str], dict] = {}
    ext_titled: list[dict] = []

    for e in entries:
        if not isinstance(e, dict) or e.get("IsDir"):
            continue
        path = e.get("Path") or ""
        parent, name = split_path(path)
        if is_sheet(e):
            # A Sheet named "X" collides with a blob named "X.xlsx"; a Sheet
            # named "X.xlsx" collides with one named "X.xlsx.xlsx" on the same
            # rule, but in practice it is debris from an import. Record both
            # readings rather than choosing.
            sheets[(parent, name)] = e
            if name.lower().endswith(".xlsx"):
                ext_titled.append(e)
        elif name.lower().endswith(".xlsx"):
            xlsx[(parent, name)] = e

    collisions = []
    for (parent, xname), xentry in sorted(xlsx.items()):
        stem = xname[: -len(".xlsx")]
        sheet = sheets.get((parent, stem)) or sheets.get((parent, xname))
        if sheet is None:
            continue

        sheet_time = parse_time(sheet.get("ModTime"))
        xlsx_time = parse_time(xentry.get("ModTime"))
        source = "Drive copy"
        if local_root is not None:
            candidate = local_root / parent / xname if parent else local_root / xname
            try:
                if candidate.is_file():
                    xlsx_time = datetime.fromtimestamp(
                        candidate.stat().st_mtime, tz=timezone.utc)
                    source = "local file"
                else:
                    source = "local file missing; used Drive copy"
            except OSError:
                source = "local file unreadable; used Drive copy"

        if sheet_time is None or xlsx_time is None:
            verdict = "unknown — a timestamp is missing"
        elif xlsx_time >= sheet_time:
            verdict = "SAFE TO DELETE the Sheet"
        else:
            verdict = "KEEP — the Sheet is newer; it may hold edits not in the .xlsx"

        collisions.append({
            "parent": parent or "(root)",
            "xlsx": xname,
            "sheet_name": sheet.get("Path", ""),
            "sheet_id": sheet.get("ID", ""),
            "sheet_time": sheet_time,
            "xlsx_time": xlsx_time,
            "time_source": source,
            "verdict": verdict,
        })
    return collisions, ext_titled


def fmt(dt: datetime | None) -> str:
    return dt.astimezone().isoformat(timespec="minutes") if dt else "unknown"


def report(collisions: list, ext_titled: list, out: Path | None) -> None:
    lines: list[str] = []
    say = lines.append

    say("# Drive `.xlsx` / Google Sheet collisions")
    say("")
    say(f"Generated {datetime.now().astimezone().isoformat(timespec='minutes')}.")
    say("")
    say("Nothing here has been changed. This is a review list.")
    say("")

    safe = [c for c in collisions if c["verdict"].startswith("SAFE")]
    keep = [c for c in collisions if c["verdict"].startswith("KEEP")]
    unknown = [c for c in collisions if c["verdict"].startswith("unknown")]

    say(f"- {len(collisions):,} collision(s) found")
    say(f"- {len(safe):,} where the `.xlsx` is newer or equal — the Sheet can go")
    say(f"- {len(keep):,} where the **Sheet is newer** — leave alone, it may "
        f"hold edits the local file does not have")
    say(f"- {len(unknown):,} undecidable from the timestamps available")
    say("")

    for title, group in (("Safe to delete", safe),
                         ("Keep — the Sheet is newer", keep),
                         ("Undecidable", unknown)):
        if not group:
            continue
        say(f"## {title}")
        say("")
        say("| Folder | .xlsx | Sheet modified | .xlsx modified | Compared against | Sheet file ID |")
        say("|---|---|---|---|---|---|")
        for c in group:
            say(f"| `{c['parent']}` | `{c['xlsx']}` | {fmt(c['sheet_time'])} | "
                f"{fmt(c['xlsx_time'])} | {c['time_source']} | `{c['sheet_id']}` |")
        say("")

    say("## Sheets whose title ends in `.xlsx`")
    say("")
    if ext_titled:
        say("A conversion made by hand is titled without the extension. These "
            "carry it, which is the shape an rclone import leaves behind — "
            "most likely debris from the run that briefly used "
            "`--drive-import-formats`. Worth checking before deleting, but "
            "they are unlikely to be anything you made deliberately.")
        say("")
        for e in ext_titled:
            say(f"- `{e.get('Path','')}` — ID `{e.get('ID','')}`, modified "
                f"{fmt(parse_time(e.get('ModTime')))}")
    else:
        say("None found.")
    say("")

    text = "\n".join(lines)
    print(text)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nReport written to {out}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report .xlsx / Google Sheet collisions on a Drive "
                    "remote. Never deletes anything.")
    ap.add_argument("remote", nargs="?", default=None,
                    help="rclone remote path, e.g. drive:RPG/_Design/Loom")
    ap.add_argument("--json", default=None,
                    help="Read an rclone lsjson listing from this file "
                         "instead of calling rclone")
    ap.add_argument("--local", default=None,
                    help="Local corpus root. Compares each Sheet against the "
                         "local .xlsx mtime rather than its Drive copy, which "
                         "is the right comparison when local is authoritative.")
    ap.add_argument("--rclone", default="rclone",
                    help="Path to rclone (default: rclone on PATH)")
    ap.add_argument("--report", default=None,
                    help="Write the review list to this Markdown file")
    ap.add_argument("--log", default=None,
                    help="Mirror this run's output to a log file.")
    args = ap.parse_args()

    if not args.remote and not args.json:
        print("ERROR: give a remote path, or --json with an rclone listing.",
              file=sys.stderr)
        return 2

    if args.json:
        try:
            entries = json.loads(Path(args.json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: could not read {args.json}: {e}", file=sys.stderr)
            return 2
    else:
        print(f"Listing {args.remote} ...")
        entries = run_rclone(args.remote, args.rclone)

    if not entries:
        print("Nothing listed. Check the remote path, or pass --json.")
        return 2

    local_root = Path(args.local).expanduser() if args.local else None
    if local_root is not None and not local_root.is_dir():
        print(f"ERROR: --local is not a directory: {local_root}",
              file=sys.stderr)
        return 2

    collisions, ext_titled = find_collisions(entries, local_root)
    report(collisions, ext_titled,
           Path(args.report) if args.report else None)
    return 1 if collisions else 0


if __name__ == "__main__":
    with run_log.tee_stdio(run_log.log_path_from_argv(sys.argv),
                           header="Drive collision report"):
        raise SystemExit(main())
