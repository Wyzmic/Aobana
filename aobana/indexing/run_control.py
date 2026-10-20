import contextlib
import ctypes
import functools
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import tracemalloc
import uuid
from pathlib import Path

CURRENT = None
KEEP_RUNS = 3

class Stopped(Exception):
    pass

def check_stop():
    from aobana.utils import stop_requested
    if stop_requested():
        if CURRENT and CURRENT.phase != 'rollback':
            CURRENT.publish(phase='rollback', phase_done=0, phase_total=0)
        raise Stopped()

class WriterLease:
    def __init__(self, db):
        from aobana import paths
        self.path = paths.companion_writer_lock(db)
        self.aliases = paths.writer_lock_paths(db)
        self.fh = None

    def __enter__(self):
        if any(name != self.path and _lock_active(name) for name in self.aliases):
            raise RuntimeError('Another index writer owns this database.')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, 'a+b')
        try:
            if os.path.getsize(self.path) == 0:
                self.fh.write(b'0')
                self.fh.flush()
            self.fh.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise RuntimeError('Another index writer owns this database.') from None
        return self

    def __exit__(self, *args):
        self.fh.close()

def writer_active(db):
    from aobana import paths
    names = paths.writer_lock_paths(db)
    return any(_lock_active(name) for name in names)


def _lock_active(name):
    try:
        fh = open(name, 'rb')
    except OSError:
        return False
    try:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(fh.fileno(),msvcrt.LK_NBRLCK,1)
            except OSError:
                return True
            msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:
                fcntl.flock(fh,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except OSError:
                return True
        return False
    finally:
        fh.close()

def process_identity(pid):
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p,ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        values = [ctypes.c_ulonglong() for _ in range(4)]
        try:
            exit_code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) or exit_code.value != 259:
                return None
            if kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
                return str(values[0].value)
        finally:
            kernel.CloseHandle(handle)
    else:
        if sys.platform == 'darwin':
            class BSDInfo(ctypes.Structure):
                _fields_ = [('ids',ctypes.c_uint32*12),('comm',ctypes.c_char*16),
                            ('name',ctypes.c_char*32),('details',ctypes.c_uint32*6),
                            ('start_sec',ctypes.c_uint64),('start_usec',ctypes.c_uint64)]
            value = _darwin_info(pid,3,BSDInfo)
            return f'{value.start_sec}:{value.start_usec}' if value else None
        try:
            return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError:
            return None

def _darwin_info(pid,flavor,structure):
    try:
        lib = ctypes.CDLL('/usr/lib/libproc.dylib')
        lib.proc_pidinfo.argtypes = [ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int]
        value = structure()
        size = ctypes.sizeof(value)
        if lib.proc_pidinfo(pid,flavor,0,ctypes.byref(value),size) == size:
            return value
    except OSError:
        pass
    return None

def memory():
    if os.name == 'nt':
        class Counters(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [
                (n, ctypes.c_size_t) for n in ('peak_rss','rss','peak_paged','paged','peak_nonpaged',
                                              'nonpaged','pagefile','peak_pagefile','private')]
        c = Counters()
        c.cb = ctypes.sizeof(c)
        k = ctypes.WinDLL('kernel32')
        k.GetCurrentProcess.restype = ctypes.c_void_p
        p = ctypes.WinDLL('psapi')
        p.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if p.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return dict(rss=c.rss, private=c.private)
    else:
        if sys.platform == 'darwin':
            class TaskInfo(ctypes.Structure):
                _fields_ = [('size',ctypes.c_uint64),('rss',ctypes.c_uint64),
                            ('times',ctypes.c_uint64*4),('counts',ctypes.c_int32*12)]
            value = _darwin_info(os.getpid(),4,TaskInfo)
            return dict(rss=value.rss if value else None,private=None)
        try:
            values = Path('/proc/self/statm').read_text().split()
            return dict(rss=int(values[1])*os.sysconf('SC_PAGE_SIZE'), private=None)
        except OSError:
            pass
    return dict(rss=None, private=None)

class Run:
    def __init__(self, db):
        self.run_id = os.environ.get('AOBANA_RUN_ID') or uuid.uuid4().hex
        if not self.run_id.isalnum():
            raise ValueError('Invalid run identity.')
        self.db = db
        from aobana import paths
        self.root = Path(paths.companion('.index-runs', db)) / self.run_id
        self.phase = 'traversal'
        self.started = time.monotonic()
        self.phase_started = self.started
        self.done = self.total = self.prepared = self.committed = 0
        self.indexed = self.removed = self.unchanged = 0
        self.peak_spool = 0
        self.end = threading.Event()
        self.conn = None
        self.logs = []

    def publish(self, **kw):
        from aobana.utils import emit
        phase = kw.pop('phase', self.phase)
        if phase != self.phase:
            self.trace()
            if phase != 'rollback':
                self.save_history()
            self.phase_started = time.monotonic()
        self.phase = phase
        self.done = kw.pop('phase_done', self.done)
        self.total = kw.pop('phase_total', self.total)
        emit('heartbeat', '', quiet=True, run_id=self.run_id, phase=self.phase,
             phase_done=self.done, phase_total=self.total, prepared_done=self.prepared,
             committed_done=self.committed, elapsed=time.monotonic()-self.started,
             remaining=None, **{k:v for k,v in kw.items() if k != 'elapsed'})

    def save_history(self):
        if self.phase in ('rollback','traversal','preparation','writing'):
            return
        if self.total and self.done < self.total:
            return
        from aobana import paths
        path = Path(paths.companion(Path(self.db).name + '.phase-history.json', self.db))
        try:
            history = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            history[self.phase] = dict(seconds=time.monotonic()-self.phase_started,
                                       units=self.done, total=self.total)
            tmp = Path(str(path)+'.tmp')
            tmp.write_text(json.dumps(history),encoding='utf-8')
            os.replace(tmp,path)
        except (OSError, ValueError, TypeError):
            pass

    def trace(self):
        def size(path):
            try:
                return path.stat().st_size
            except OSError:
                return 0
        files = list(self.root.glob('*'))
        spool = sum(size(p) for p in files if p.suffix == '.spool')
        self.peak_spool = max(self.peak_spool, spool)
        temp = sum(size(p) for p in files if p.name.startswith(('sqlite','etilqs')))
        table_temp = sum(size(p) for p in self.root.glob('.*/*.db'))
        journal = sum(size(Path(str(self.db)+suffix)) for suffix in ('-journal','-wal','-shm'))
        row = dict(run_id=self.run_id, pid=os.getpid(), identity=process_identity(os.getpid()),
                   role='writer', phase=self.phase, elapsed=time.monotonic()-self.started,
                   phase_elapsed=time.monotonic()-self.phase_started, spool_bytes=spool,
                   peak_spool_bytes=self.peak_spool, sqlite_temp_bytes=temp, table_temp_bytes=table_temp,
                   sqlite_sidecar_bytes=journal, **memory())
        if tracemalloc.is_tracing():
            row['python_bytes'], row['python_peak'] = tracemalloc.get_traced_memory()
        with (self.root / 'metrics.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')

    def heartbeat(self):
        last = 0
        while not self.end.wait(.1):
            try:
                from aobana.utils import stop_requested
                if self.conn and stop_requested():
                    self.conn.interrupt()
                if time.monotonic()-last >= 1:
                    last = time.monotonic()
                    self.trace()
                    self.publish()
            except OSError:
                pass

class Connection(sqlite3.Connection):
    def commit(self):
        deadline = time.monotonic() + 300
        while True:
            check_stop()
            try:
                return super().commit()
            except sqlite3.OperationalError as error:
                if 'locked' not in str(error).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(.05)

def connection(db):
    conn = sqlite3.connect(db, timeout=0.25, factory=Connection)
    conn.execute('PRAGMA cache_size=-32768')
    conn.execute('PRAGMA temp_store=FILE')
    conn.execute('PRAGMA cache_spill=ON')
    from aobana.utils import stop_requested
    conn.set_progress_handler(lambda: int(stop_requested()), 2000)
    if CURRENT:
        CURRENT.conn = conn
        try:
            directory = str(CURRENT.root).replace("'", "''")
            conn.execute("PRAGMA temp_store_directory='" + directory + "'")
        except sqlite3.Error:
            pass
    return conn

def owned(db_getter):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kw):
            global CURRENT
            from aobana.utils import emit, stop_requested
            db = db_getter()
            with WriterLease(db):
                run = Run(db)
                CURRENT = run
                run.root.mkdir(parents=True, exist_ok=True)
                mine = []
                for old in run.root.parent.iterdir():
                    if old != run.root and old.is_dir() and not old.is_symlink() and (old/'owner.json').exists():
                        try:
                            owner = json.loads((old/'owner.json').read_text(encoding='utf-8'))
                            if owner.get('database') != str(Path(db).resolve()):
                                continue
                            mine.append(old)
                            for p in old.glob('*.spool'):
                                p.unlink(missing_ok=True)
                            for p in old.iterdir():
                                if (p.is_dir() and not p.is_symlink() and
                                        p.name.startswith(('.line_lengths-', '.ruby_lexicon-')) and
                                        p.resolve().is_relative_to(old.resolve())):
                                    shutil.rmtree(p)
                        except (OSError, ValueError):
                            pass
                excess = max(0, len(mine) - (KEEP_RUNS - 1))
                for old in sorted(mine, key=lambda p: (p/'owner.json').stat().st_mtime)[:excess]:
                    try:
                        if old.resolve().parent == run.root.parent.resolve():
                            shutil.rmtree(old)
                    except OSError:
                        pass
                (run.root/'owner.json').write_text(json.dumps(dict(run_id=run.run_id, pid=os.getpid(),
                    identity=process_identity(os.getpid()), database=str(Path(db).resolve()))), encoding='utf-8')
                prior = os.environ.get('AOBANA_SPOOL_DIR')
                os.environ['AOBANA_SPOOL_DIR'] = str(run.root)
                if os.environ.get('AOBANA_TRACE_PYTHON') == '1':
                    tracemalloc.start()
                thread = threading.Thread(target=run.heartbeat, daemon=True)
                thread.start()
                run.trace()
                try:
                    check_stop()
                    result = fn(*args, **kw)
                    check_stop()
                    run.save_history()
                    return result
                except (Stopped, sqlite3.OperationalError) as e:
                    if not isinstance(e, Stopped) and not stop_requested():
                        raise
                    run.end.set()
                    thread.join(2)
                    run.publish(phase='rollback', phase_done=0, phase_total=0)
                    if run.conn:
                        run.conn.set_progress_handler(None, 0)
                        for attempt in range(3):
                            try:
                                run.conn.rollback()
                                break
                            except sqlite3.OperationalError as error:
                                if 'interrupted' not in str(error):
                                    raise
                    emit('stopped', 'STOPPED')
                    emit('summary', 'Indexing stopped. Committed work is kept.', indexed=run.indexed,
                         unchanged=run.unchanged, removed=run.removed, failed=0)
                finally:
                    run.end.set()
                    thread.join(2)
                    run.trace()
                    for log in run.logs:
                        log.close()
                    if run.conn:
                        run.conn.close()
                    for p in run.root.glob('*.spool'):
                        p.unlink(missing_ok=True)
                    for p in run.root.iterdir():
                        if p.is_dir() and p.name.startswith(('.line_lengths-', '.ruby_lexicon-')):
                            shutil.rmtree(p)
                    if prior is None:
                        os.environ.pop('AOBANA_SPOOL_DIR', None)
                    else:
                        os.environ['AOBANA_SPOOL_DIR'] = prior
                    CURRENT = None
        return wrapper
    return decorate

def committed(indexed, unchanged, removed=0):
    if CURRENT:
        CURRENT.indexed, CURRENT.unchanged, CURRENT.removed = indexed, unchanged, removed
        CURRENT.committed = indexed
        CURRENT.publish()

def phase(name, done=0, total=0):
    check_stop()
    if CURRENT:
        CURRENT.publish(phase=name, phase_done=done, phase_total=total)

class StreamLog:
    def __init__(self, path, format_row):
        self.path, self.format_row = path, format_row
        self.fh = None
        self.count = self.lines = 0
        if CURRENT:
            CURRENT.logs.append(self)
    def extend(self, rows):
        for row in rows:
            if self.fh is None:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self.fh = open(self.path, 'w', encoding='utf-8')
            self.fh.write(self.format_row(row)+'\n')
            self.count += 1
    def close(self):
        if self.fh:
            self.fh.close()
    def __bool__(self):
        return False
