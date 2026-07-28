"""Multi-thread segmented HTTP downloader with resume, retry and live progress.

Design:
- HEAD/Range probe for total size; split into N chunks (max 8 threads).
- Each chunk writes to `<file>.part` at its own offset (pre-allocated sparse file).
- Progress metadata saved to `<file>.meta.json` -> resume after interruption.
- Exponential-backoff retry per chunk; multiple candidate urls (CDN backups).
- Live progress line: percent / speed / ETA.
"""
import os
import json
import time
import threading

import requests

from .utils import format_size, format_eta

CHUNK_READ = 256 * 1024


class DownloadError(Exception):
    pass


class DownloadControl:
    """Pause / cancel control shared between the GUI and worker threads.

    - cancel_event: 设置后任务尽快停止并保留断点（用于「取消」与「暂停」）。
    - pause_event: 设置后任务挂起（暂停），清除后继续（断点续传）。
    """
    def __init__(self):
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    def _check(self):
        """Return 'cancel' / 'pause' / None. Blocks while paused."""
        if self.cancel_event.is_set():
            return "cancel"
        if self.pause_event.is_set():
            while self.pause_event.is_set() and not self.cancel_event.is_set():
                time.sleep(0.25)
            return "cancel" if self.cancel_event.is_set() else "resume"
        return None


class _RateLimiter:
    """Global bytes/sec throttle shared across download chunks (限速)."""
    def __init__(self, bps):
        self.bps = bps or 0
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.sent = 0

    def throttle(self, n):
        if self.bps <= 0:
            return
        with self.lock:
            self.sent += n
            elapsed = time.time() - self.t0
            delay = self.sent / self.bps - elapsed
            delay = max(0.0, min(delay, 1.0))
        if delay > 0:
            time.sleep(delay)


class _Progress:
    def __init__(self, total, done=0, label="", sink=None):
        self.total = total
        self.done = done
        self.label = label
        self.sink = sink
        self.lock = threading.Lock()
        self._t0 = time.time()
        self._d0 = done
        self._last_print = 0.0

    def add(self, n):
        with self.lock:
            self.done += n

    def print_line(self, force=False):
        now = time.time()
        if not force and now - self._last_print < 0.35:
            return
        self._last_print = now
        elapsed = max(now - self._t0, 1e-6)
        speed = (self.done - self._d0) / elapsed
        pct = self.done / self.total * 100 if self.total else 0
        eta = (self.total - self.done) / speed if speed > 0 and self.total else None
        bar_n = int(pct // 5)
        bar = "█" * bar_n + "░" * (20 - bar_n)
        line = (f"\r  {self.label} [{bar}] {pct:5.1f}% "
                f"{format_size(self.done)}/{format_size(self.total)} "
                f"{format_size(speed)}/s ETA {format_eta(eta)}   ")
        print(line, end="", flush=True)
        if self.sink is not None:
            try:
                self.sink.update(self.done, self.total, self.label,
                                 speed=speed, eta=eta)
            except Exception:
                pass


def _probe(session, urls, headers):
    """Return (url, total_size, accept_ranges)."""
    last_err = None
    for url in urls:
        try:
            r = session.get(url, headers={**headers, "Range": "bytes=0-0"},
                            timeout=15, stream=True)
            if r.status_code in (200, 206):
                cr = r.headers.get("Content-Range", "")
                if r.status_code == 206 and "/" in cr:
                    total = int(cr.rsplit("/", 1)[-1])
                    r.close()
                    return url, total, True
                total = int(r.headers.get("Content-Length", 0))
                r.close()
                return url, total, False
            last_err = DownloadError(f"HTTP {r.status_code}")
            r.close()
        except Exception as e:  # noqa
            last_err = e
    raise DownloadError(f"所有下载地址均不可用: {last_err}")


def download_file(session, urls, dest, threads=8, retries=3, label=None,
                  extra_headers=None, progress=None, control=None,
                  rate_limit=0):
    """Download urls[0..] to dest with resume support. Returns dest.

    progress: optional sink object with .update(done, total, label, speed, eta).
    control:  DownloadControl (暂停/取消).
    rate_limit: bytes/sec (限速), 0 = 不限速。
    """
    if isinstance(urls, str):
        urls = [urls]
    label = label or os.path.basename(dest)[:24]
    headers = {
        "User-Agent": session.headers.get("User-Agent", ""),
        "Referer": "https://www.bilibili.com/",
    }
    if extra_headers:
        headers.update(extra_headers)

    if os.path.exists(dest):
        print(f"  已存在，跳过: {os.path.basename(dest)}")
        return dest

    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    part = dest + ".part"
    meta_path = dest + ".meta.json"

    url, total, ranged = _probe(session, urls, headers)

    # ---- resume meta ----
    meta = None
    if os.path.exists(meta_path) and os.path.exists(part):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("total") != total:
                meta = None  # source changed
        except Exception:
            meta = None

    if not ranged or total <= 4 * 1024 * 1024:
        _download_single(session, urls, part, total, headers, retries, label,
                         sink=progress, control=control, rate_limit=rate_limit)
    else:
        n = max(1, min(threads, 8))
        if meta:
            chunks = meta["chunks"]
        else:
            size = total // n
            chunks = []
            for i in range(n):
                start = i * size
                end = total - 1 if i == n - 1 else (i + 1) * size - 1
                chunks.append({"start": start, "end": end, "done": 0})
            with open(part, "wb") as f:
                f.truncate(total)
        done0 = sum(c["done"] for c in chunks)
        if done0:
            print(f"  断点续传: 已完成 {format_size(done0)} / {format_size(total)}")
        prog = _Progress(total, done0, label, sink=progress)
        limiter = _RateLimiter(rate_limit)
        _download_chunks(session, urls, part, chunks, headers, retries, prog,
                         meta_path, control=control, limiter=limiter)
        prog.print_line(force=True)
        print()

    if os.path.exists(meta_path):
        os.remove(meta_path)
    os.replace(part, dest)
    return dest


def _download_single(session, urls, part, total, headers, retries, label,
                    sink=None, control=None, rate_limit=0):
    prog = _Progress(total or 0, 0, label, sink=sink)
    limiter = _RateLimiter(rate_limit)
    err = None
    for attempt in range(retries + 1):
        for url in urls:
            try:
                with session.get(url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(part, "wb") as f:
                        for blk in r.iter_content(CHUNK_READ):
                            if control and control._check() == "cancel":
                                return
                            f.write(blk)
                            prog.add(len(blk))
                            limiter.throttle(len(blk))
                            prog.print_line()
                prog.print_line(force=True)
                print()
                return
            except Exception as e:  # noqa
                err = e
        wait = 2 ** attempt
        print(f"\n  重试 {attempt + 1}/{retries} ({err})，{wait}s 后...")
        time.sleep(wait)
    raise DownloadError(f"下载失败: {err}")


def _download_chunks(session, urls, part, chunks, headers, retries, prog,
                     meta_path, control=None, limiter=None):
    limiter = limiter or _RateLimiter(0)
    stop = threading.Event()
    errors = []
    meta_lock = threading.Lock()

    def save_meta():
        with meta_lock:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"total": prog.total, "chunks": chunks}, f)

    def worker(idx):
        c = chunks[idx]
        pos = c["start"] + c["done"]
        if pos > c["end"]:
            return
        for attempt in range(retries + 1):
            if stop.is_set():
                return
            for url in urls:
                try:
                    hdrs = {**headers, "Range": f"bytes={pos}-{c['end']}"}
                    with session.get(url, headers=hdrs, stream=True, timeout=30) as r:
                        if r.status_code != 206:
                            raise DownloadError(f"HTTP {r.status_code} (expect 206)")
                        with open(part, "r+b") as f:
                            f.seek(pos)
                            for blk in r.iter_content(CHUNK_READ):
                                chk = control._check() if control else None
                                if chk == "cancel":
                                    save_meta()
                                    return
                                f.write(blk)
                                n = len(blk)
                                pos += n
                                c["done"] += n
                                prog.add(n)
                                limiter.throttle(n)
                                prog.print_line()
                    if pos > c["end"]:
                        save_meta()
                        return
                except Exception:  # noqa
                    save_meta()
            if stop.is_set():
                return
            time.sleep(min(2 ** attempt, 8))
        errors.append(DownloadError(f"分块 {idx} 多次重试后仍失败"))
        stop.set()

    ts = [threading.Thread(target=worker, args=(i,), daemon=True)
          for i in range(len(chunks))]
    for t in ts:
        t.start()
    try:
        for t in ts:
            while t.is_alive():
                t.join(0.5)
    except KeyboardInterrupt:
        stop.set()
        save_meta()
        print("\n  已暂停，进度已保存。重跑同一命令即可断点续传。")
        raise
    save_meta()
    if errors:
        raise errors[0]


def record_stream(session, url, dest, label="直播录制", referer="https://live.bilibili.com/"):
    """Record a live FLV stream until Ctrl+C. No total size / resume."""
    headers = {
        "User-Agent": session.headers.get("User-Agent", ""),
        "Referer": referer,
    }
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    done = 0
    t0 = time.time()
    print(f"  开始录制 -> {dest}  (Ctrl+C 停止)")
    try:
        with session.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for blk in r.iter_content(CHUNK_READ):
                    f.write(blk)
                    done += len(blk)
                    el = time.time() - t0
                    if int(el * 2) % 2 == 0:
                        print(f"\r  已录制 {format_size(done)} | "
                              f"{format_eta(el)} | {format_size(done / max(el, 1))}/s   ",
                              end="", flush=True)
    except KeyboardInterrupt:
        print(f"\n  录制结束，共 {format_size(done)}")
    return dest
