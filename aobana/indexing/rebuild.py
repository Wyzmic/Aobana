import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from aobana.utils import name_key, outdated_sources

SUFFIX = ".rebuild"
SIDECARS = ("", "-journal", "-wal", "-shm")
FLAG = "--rebuild"
NO_SWAP_FLAG = "--no-swap"


def main(run, db, argv, allow_removal):
    result = run(rebuild=True, allow_removal=allow_removal)
    if result == "refused":
        return run(outdated=True, allow_removal=allow_removal)
    if result == "rebuilt" and NO_SWAP_FLAG not in argv:
        swap(db)
    elif result != "rebuilt":
        discard(db)


def path(db):
    return str(db) + SUFFIX


def done_path(db):
    return path(db) + ".done"


def wanted(db, media) -> bool:
    if not os.path.isfile(db):
        return False
    try:
        with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sources'").fetchone():
                return False
            total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            return total > 0 and outdated_sources(conn, media) * 2 >= total
    except sqlite3.Error:
        return False


def drop_old(db):
    discard(db)
    for s in SIDECARS:
        for attempt in range(60):
            try:
                os.remove(str(db) + s)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 59:
                    raise
                time.sleep(0.5)


def discard(db):
    for p in [done_path(db)] + [path(db) + s for s in SIDECARS]:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def old_sources(db, column="relpath"):
    if not os.path.isfile(db):
        return {}
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sources'").fetchone():
            return {}
        return {name_key(r[0]): r[0] for r in conn.execute(f"SELECT {column} FROM sources")}


def _os_error_names():
    names, todo = set(), [OSError]
    while todo:
        cls = todo.pop()
        names.add(cls.__name__)
        todo.extend(cls.__subclasses__())
    return frozenset(names)


OS_ERRORS = _os_error_names()


def transient(message):
    return str(message).split(":", 1)[0].strip() in OS_ERRORS


def refused(old, failed, held):
    lost = [k for k in failed if k in old]
    if lost:
        return f"{len(lost)} indexed files could not be read"
    if held:
        return f"{len(held)} indexed files are missing"
    return None


def swap(db):
    for p in (path(db), str(db)):
        for s in ("-journal", "-wal", "-shm"):
            if os.path.exists(p + s):
                raise OSError(f"{p + s} is left over from an unfinished write; the old index is kept")
    for attempt in range(60):
        try:
            os.replace(path(db), db)
            os.remove(done_path(db))
            return
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(0.5)
