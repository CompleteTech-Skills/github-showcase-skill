"""Cross-process locking for shared generator outputs."""
from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import NeedsInput


@contextmanager
def output_lock(path: Path | None):
    """Serialize a user's local generator writes to the same resolved output path."""
    if path is None:
        yield
        return
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(path.resolve())))).hexdigest()
    # Keep the lock shared by generators launched with different temporary directories.
    directory = Path.home() / ".showcase-sidecar-locks"
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / key).open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 90
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise NeedsInput("formatter", "another generator still holds the output lock")
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield  # closing the file releases the lock on both platforms
