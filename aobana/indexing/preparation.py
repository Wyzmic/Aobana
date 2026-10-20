import multiprocessing
import os
import pickle
import tempfile
import time
import uuid
from pathlib import Path

class Rows:
    def __init__(self, path, count):
        self.path, self.count = path, count
    def __len__(self):
        return self.count
    def __bool__(self):
        return bool(self.count)
    def __iter__(self):
        with open(self.path, 'rb') as f:
            for _ in range(self.count):
                yield pickle.load(f)

def _spill(value, root, limit):
    if isinstance(value, tuple):
        return tuple(_spill(v, root, max(1, limit // max(1, len(value)))) for v in value)
    if isinstance(value, list) and value:
        if len(value) < 128 and sum(len(pickle.dumps(v, protocol=5)) for v in value) < limit:
            return value
        path = str(Path(root) / (uuid.uuid4().hex + '.spool'))
        with open(path, 'wb') as f:
            for row in value:
                pickle.dump(row, f, protocol=5)
        return Rows(path, len(value))
    return value

def _job(fn, item, root, limit):
    result = _spill(fn(item), root, limit)
    from aobana.indexing.run_control import memory
    import json
    with open(str(Path(root)/f'parser-{os.getpid()}.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(dict(role='parser',pid=os.getpid(),at=time.time(),**memory()))+'\n')
    return result

def dispose(value):
    if isinstance(value, Rows):
        Path(value.path).unlink(missing_ok=True)
    elif isinstance(value, (tuple, list)):
        for v in value:
            dispose(v)

def bounded_map(fn, items, workers, ordered=True, stop=None):
    stop = stop or (lambda: False)
    root = os.environ.get('AOBANA_SPOOL_DIR')
    own = None
    if root is None:
        own = tempfile.TemporaryDirectory(prefix='aobana-preparation-')
        root = own.name
    limit = min(1024*1024, 256*1024*1024 // max(1, workers*2))
    pool = None
    try:
        if workers > 1:
            try:
                pool = multiprocessing.get_context('spawn').Pool(workers)
            except (ImportError, OSError, NotImplementedError) as e:
                from aobana.utils import say
                say(f'PARALLEL_OFF {type(e).__name__}: {e}')
        if pool is None:
            for item in items:
                if stop():
                    return
                result = _job(fn, item, root, limit)
                _prepared()
                try:
                    yield result
                finally:
                    dispose(result)
            return
        iterator = iter(items)
        pending = []
        exhausted = False
        seen = set()
        while pending or not exhausted:
            while not exhausted and len(pending) < workers*2:
                try:
                    item = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                pending.append(pool.apply_async(_job, (fn, item, root, limit)))
            if stop():
                return
            for job in pending:
                if job.ready() and id(job) not in seen:
                    seen.add(id(job))
                    _prepared()
            index = 0 if ordered else next((i for i,j in enumerate(pending) if j.ready()), None)
            if index is None or (pending and not pending[index].ready()):
                if ordered and pending:
                    pending[0].wait(.05)
                else:
                    time.sleep(.05)
                continue
            if not pending:
                break
            job = pending.pop(index)
            seen.discard(id(job))
            result = job.get()
            try:
                yield result
            finally:
                dispose(result)
    finally:
        if pool:
            pool.terminate()
            pool.join()
        if own:
            own.cleanup()

def prepare_changed(prepare, jobs, workers, file_hash, stop=None):
    from concurrent.futures import ThreadPoolExecutor
    from aobana.indexing import run_control
    from aobana.utils import parallel_map

    def hashed(job):
        if stop and stop():
            return job, None, 'stopped'
        try:
            return job, file_hash(job[0]), None
        except run_control.Stopped:
            return job, None, 'stopped'
        except Exception as e:
            return job, None, f"{type(e).__name__}: {e}"

    known = [job for job in jobs if job[2] is not None]
    changed = [job for job in jobs if job[2] is None]
    pool = ThreadPoolExecutor(max(1, workers))
    try:
        for job, digest, error in pool.map(hashed, known):
            if error == 'stopped' or (stop and stop()):
                run_control.check_stop()
                return
            if error or digest == job[2]:
                _prepared()
                yield ('error', job[1], None, error) if error else ('same', job[1], digest, None)
            else:
                changed.append(job)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if changed:
        order = {id(job): i for i, job in enumerate(jobs)}
        changed.sort(key=lambda job: order[id(job)])
        yield from parallel_map(prepare, changed, workers if len(changed) > 1 else 1, stop=stop)


def _prepared():
    from aobana.indexing import run_control
    if run_control.CURRENT:
        run_control.CURRENT.prepared += 1
        run_control.CURRENT.publish()
