#!/usr/bin/env python3
"""
run_log.py

Mirror a script's console output to a log file.

WHY THIS IS SHARED

`process_folder.py` has always written a timestamped log of its run, by
replacing stdout with an object that forwards to both the console and a file.
Nothing else did, so the rest of a wrapper's output -- the stale check, the
tier stamping, the catalogue pass -- existed only until the console window
closed. That is the part of a run you most want to re-read: the orphan list,
the counts, the warnings.

Rather than copy the same fifteen lines into four scripts, the mechanism lives
here. The same consolidation the exclusion list went through, for the same
reason: two copies drift, and the drift is invisible until it matters.

USAGE

    from run_log import tee_stdio

    with tee_stdio(path):          # path may be None, which does nothing
        ...                        # everything printed lands in both places

The context manager restores the real streams on the way out, including when
the body raises, so a failing run still leaves a readable log.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class Tee:
    """Forward writes to several streams.

    Failures on any one stream are swallowed deliberately: a log file that
    fills a disk, or a console that has gone away, must not take down the run
    that was writing to it.
    """

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


def timestamped(dir_path: Path, prefix: str) -> Path:
    """`<dir>/<prefix>_YYYYmmdd_HHMMSS.log`."""
    return Path(dir_path) / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.log"


def log_path_from_argv(argv: list[str]) -> Path | None:
    """The value of `--log` in `argv`, read before argparse runs.

    Scanning argv by hand looks redundant when the same flag is declared on
    the parser, and it is not. The log has to be live before `parse_args` is
    called, because argparse prints its own errors and usage text and exits --
    the runs most worth having a log of are exactly the ones that fail at the
    front door.
    """
    if "--log" not in argv:
        return None
    i = argv.index("--log")
    if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
        return Path(argv[i + 1])
    return None


@contextmanager
def tee_stdio(log_path: Path | None, header: str = ""):
    """Mirror stdout and stderr into `log_path` for the duration of the block.

    A None path is a no-op, so a caller can pass its `--log` argument straight
    through without branching. A log that cannot be opened is reported once on
    the real stderr and then ignored -- losing the log is not a reason to lose
    the run.
    """
    if log_path is None:
        yield None
        return

    handle = None
    try:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("w", encoding="utf-8")
    except OSError as e:
        print(f"WARNING: could not open log file {log_path}: {e}",
              file=sys.__stderr__)
        yield None
        return

    if header:
        handle.write(f"{header}\n{datetime.now().isoformat(timespec='seconds')}\n\n")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = Tee(real_out, handle)
    sys.stderr = Tee(real_err, handle)
    try:
        yield log_path
    finally:
        sys.stdout, sys.stderr = real_out, real_err
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass
