import ctypes
import os
import signal
import subprocess
import sys
import threading
import time

class WindowsJob:
    def __init__(self):
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
                        ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                        ('active',wintypes.DWORD),('affinity',ctypes.c_size_t),
                        ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n,ctypes.c_uint64) for n in ('read_ops','write_ops','other_ops','read','write','other')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                        ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateJobObjectW.restype = wintypes.HANDLE
        self.k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.k.CreateJobObjectW(None, None)
        info = Limits()
        info.basic.flags = 0x2000
        if not self.handle or not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
    def attach(self, proc):
        if not self.k.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
    def terminate(self):
        self.k.TerminateJobObject(self.handle, 1)
    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None

def parent_watch(fd):
    def watch():
        try:
            while os.read(fd, 1):
                pass
        finally:
            os.killpg(os.getpgrp(), signal.SIGKILL)
    threading.Thread(target=watch, daemon=True).start()

class OwnedProcess:
    def __init__(self, cmd, env, cwd, stop_file):
        from aobana.indexing.run_control import process_identity
        self.stop_file = stop_file
        self.lifetime = None
        self.job = WindowsJob() if os.name == 'nt' else None
        args = dict(cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE, encoding='utf-8', errors='replace')
        args['env'] = dict(env, AOBANA_RUN_CHILD='1')
        if self.job:
            args['creationflags'] = subprocess.CREATE_NO_WINDOW
            gate = "import sys; sys.stdin.read(1); "
        else:
            read, self.lifetime = os.pipe()
            args.update(start_new_session=True, pass_fds=(read,))
            gate = f"from aobana.indexing.process_tree import parent_watch; parent_watch({read}); "
        cmd = list(cmd)
        bootstrap = cmd[2]
        pos = bootstrap.index('runpy.run_module')
        cmd[2] = bootstrap[:pos] + gate + bootstrap[pos:]
        try:
            self.proc = subprocess.Popen(cmd, **args)
            self.identity = process_identity(self.proc.pid)
            if self.job:
                self.job.attach(self.proc)
                self.proc.stdin.write('1')
                self.proc.stdin.flush()
            else:
                os.close(read)
            self.proc.stdin.close()
        except BaseException:
            if hasattr(self, 'proc'):
                self.proc.kill()
                self.proc.wait()
            self.close()
            raise
        self.finished = threading.Event()
        self.forced = False
        threading.Thread(target=self.watch_stop, daemon=True).start()

    def watch_stop(self):
        since = None
        while not self.finished.wait(.1):
            if os.path.exists(self.stop_file):
                since = since or time.monotonic()
                if time.monotonic()-since >= 10:
                    self.forced = True
                    self.terminate()
                    return

    def terminate(self):
        from aobana.indexing.run_control import process_identity
        if self.proc.poll() is not None or self.identity is None or process_identity(self.proc.pid) != self.identity:
            return False
        if self.job:
            self.job.terminate()
        else:
            os.killpg(self.proc.pid, signal.SIGKILL)
        return True

    def close(self):
        if hasattr(self, 'finished'):
            self.finished.set()
        if self.job:
            self.job.close()
        if self.lifetime is not None:
            os.close(self.lifetime)
            self.lifetime = None

def cli_owner(module):
    if os.environ.get('AOBANA_RUN_CHILD') == '1':
        return
    from aobana import paths
    paths.start_companions()
    from aobana.server.library import _child_cmd
    stop = os.environ.get('AOBANA_STOP_FILE', '')
    tree = OwnedProcess(_child_cmd(module, sys.argv[1:]), dict(os.environ), paths.BASE_DIR, stop)
    try:
        for line in tree.proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        code = tree.proc.wait()
    except BaseException:
        tree.terminate()
        raise
    finally:
        tree.close()
    raise SystemExit(code)
